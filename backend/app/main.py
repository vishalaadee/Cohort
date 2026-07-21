from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from .db import engine
from .routers import auth_routes, companies, dashboard, portal, students_admin

app = FastAPI(title="Placement Platform API", version="0.1.0")

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


@app.get("/api/health")
def health():
    """Liveness + DB reachability, for uptime checks and load balancers."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception:
        return {"status": "degraded", "db": "down"}
