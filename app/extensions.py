from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
oauth = OAuth()
# In-memory storage: limits are per Gunicorn worker. Good enough to slow down
# scripted abuse of the login routes; switch to Redis if that changes.
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
