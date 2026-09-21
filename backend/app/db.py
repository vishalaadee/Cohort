from contextlib import contextmanager

from sqlalchemy import create_engine, text

from .config import settings

# pool_pre_ping avoids handing out a dead connection after a DB restart.
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

# Every public API route is held behind this guard at startup. Keeping this
# explicit prevents a partially upgraded database from generating a cascade of
# misleading 500s. Apply the tracked migrations instead of adding columns by
# hand when it reports false.
REQUIRED_SCHEMA_OBJECTS = (
    "public.attribute_defs",
    "public.resumes",
    "public.edit_requests",
    "public.questions",
    "public.company_notes",
    "public.notifications",
)


def schema_is_current() -> bool:
    try:
        with engine.connect() as conn:
            for object_name in REQUIRED_SCHEMA_OBJECTS:
                if conn.execute(text("SELECT to_regclass(:name)"), {"name": object_name}).scalar() is None:
                    return False
            required_columns = conn.execute(text("""
                SELECT count(*)
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'colleges'
                  AND column_name = 'placement_policy'
            """)).scalar()
            return required_columns == 1
    except Exception:
        return False


@contextmanager
def tenant_connection(claims):
    """Open ONE transaction, stamp the tenant context onto it with SET LOCAL,
    and hand back a connection. Because it's SET LOCAL the values live only for
    this transaction — they cannot leak onto the next request that reuses this
    pooled connection. Every RLS policy in schema.sql reads these GUCs."""
    with engine.begin() as conn:  # BEGIN ... COMMIT/ROLLBACK around the block
        conn.execute(
            text("SELECT set_config('app.role', :v, true)"),
            {"v": claims.role or ""},
        )
        conn.execute(
            text("SELECT set_config('app.college_id', :v, true)"),
            {"v": "" if claims.college_id is None else str(claims.college_id)},
        )
        conn.execute(
            text("SELECT set_config('app.branch_id', :v, true)"),
            {"v": "" if claims.branch_id is None else str(claims.branch_id)},
        )
        conn.execute(
            text("SELECT set_config('app.user_id', :v, true)"),
            {"v": "" if claims.user_id is None else str(claims.user_id)},
        )
        yield conn
