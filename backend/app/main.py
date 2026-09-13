import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import engine, schema_is_current
from .errors import (database_exception_handler, http_exception_handler,
                     unhandled_exception_handler, validation_exception_handler)
from .routers import admin_extra, auth_routes, companies, dashboard, portal, students_admin

app = FastAPI(title="Placement Platform API", version="0.1.0")
logger = logging.getLogger("cohort.api")

# In the single-box setup Caddy serves the site and the API from the same
# origin, so CORS is permissive only to make local dev easy. Tighten later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exposes GET /metrics for Prometheus (internal network only — Caddy does not
# proxy it to the public site).
Instrumentator().instrument(app).expose(app)

app.include_router(auth_routes.router)
app.include_router(dashboard.router)
app.include_router(companies.router)
app.include_router(students_admin.router)
app.include_router(portal.router)
app.include_router(admin_extra.router)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(SQLAlchemyError, database_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.on_event("startup")
def verify_schema_before_serving_requests():
    app.state.schema_current = schema_is_current()
    if not app.state.schema_current:
        logger.error("Database schema is behind this application version; run scripts/migrate-rds.sh")


@app.middleware("http")
async def require_current_schema(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        current = getattr(app.state, "schema_current", None)
        # TestClient can intentionally run without ASGI lifespan events. The
        # first API request still gets the same migration guard in that case.
        if current is None:
            current = schema_is_current()
            app.state.schema_current = current
        if not current:
            return JSONResponse(status_code=503, content={"error": {
                "code": "database_upgrade_required",
                "message": "The service is being updated. Please try again shortly.",
            }})
    return await call_next(request)


@app.get("/api/health")
def health():
    """Liveness + DB reachability, for uptime checks and load balancers."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if not getattr(app.state, "schema_current", False):
            return JSONResponse(status_code=503, content={"status": "degraded", "db": "up", "schema": "upgrade_required"})
        return {"status": "ok", "db": "up", "schema": "current"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "down"})
