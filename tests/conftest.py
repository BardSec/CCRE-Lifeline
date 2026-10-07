import pytest
from flask import g
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db
from app.models import Tenant, User, UserRole
from app.services.seed import seed

ADMIN = "admin@district.edu"
EVALUATOR = "evaluator@district.edu"
VIEWER = "viewer@district.edu"


def _ensure_database(url: str) -> None:
    """Create the test database on first run (Postgres has no CREATE IF NOT EXISTS)."""
    target = make_url(url)
    engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    engine.dispose()


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    _ensure_database(TestConfig.SQLALCHEMY_DATABASE_URI)
    TestConfig.EVIDENCE_DIR = str(tmp_path_factory.mktemp("evidence"))
    app = create_app(TestConfig)

    @app.before_request
    def _forget_cached_user():
        # The db fixture keeps an app context pushed, and test-client requests
        # reuse it, so Flask-Login's per-request user cache on `g` would leak
        # between clients. In production every request gets a fresh context.
        g.pop("_login_user", None)

    with app.app_context():
        _db.drop_all()
        _db.create_all()
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(autouse=True)
def restore_config(app):
    """The app is session-scoped; undo any config a test changes."""
    snapshot = dict(app.config)
    yield
    app.config.clear()
    app.config.update(snapshot)


@pytest.fixture()
def db(app):
    with app.app_context():
        seed(app.config["SEED_TENANT_NAME"])
        yield _db
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture()
def client(app, db):
    return app.test_client()


@pytest.fixture()
def login(client, db):
    """Sign in through the dev login. Pass role= to set a non-admin's role."""
    def _login(email=ADMIN, role=None):
        resp = client.post("/login/dev", data={"email": email})
        assert resp.status_code == 302, resp.data
        user = db.session.query(User).filter_by(email=email).one()
        if role is not None:
            user.role = role
            db.session.commit()
        return user
    return _login


@pytest.fixture()
def other_tenant_user(db):
    """A user in a second organization, for isolation tests."""
    tenant = Tenant(name="Other District")
    db.session.add(tenant)
    db.session.flush()
    user = User(tenant_id=tenant.id, email="x@other.edu", name="Other", role=UserRole.admin)
    db.session.add(user)
    db.session.commit()
    return user


def login_as(client, user):
    """Put *user* in the session directly (bypasses tenant assignment at login)."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
