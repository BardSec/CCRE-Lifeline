from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth.router import router as auth_router
from app.config import get_settings
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers.admin import router as admin_router
from app.routers.dashboard import router as dashboard_router
from app.routers.evaluations import router as eval_router
from app.routers.evidence import router as evidence_router
from app.routers.tasks import router as tasks_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()

# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


# ── App factory ────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="K12 Cybersecurity Rubric Evaluation Platform",
    version="1.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── Global template context ────────────────────────────────────────────────────
templates = Jinja2Templates(directory="app/templates")

@app.middleware("http")
async def inject_globals(request: Request, call_next):
    request.state.now = datetime.utcnow()
    response = await call_next(request)
    return response

# Inject `now` into every template automatically
_orig_TemplateResponse = Jinja2Templates.TemplateResponse

def _patched_TemplateResponse(self, name, context, *args, **kwargs):
    if "request" in context and not "now" in context:
        context["now"] = datetime.utcnow()
    return _orig_TemplateResponse(self, name, context, *args, **kwargs)

Jinja2Templates.TemplateResponse = _patched_TemplateResponse

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(eval_router)
app.include_router(evidence_router)
app.include_router(tasks_router)
app.include_router(admin_router)


# ── Catch-all redirect to login ────────────────────────────────────────────────
@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return RedirectResponse(url="/login")
