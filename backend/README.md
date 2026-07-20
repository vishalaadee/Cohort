# Backend

See [docs/BACKEND.md](../docs/BACKEND.md) for architecture, RLS mechanics,
auth flows, and how to add endpoints.

## Quick run (local dev)

```bash
pip install -r requirements.txt
DATABASE_URL="postgresql+psycopg://app_user:pw@localhost:5432/placement" \
JWT_SECRET="dev-secret" DEV_FALLBACK=true \
python -m uvicorn app.main:app --reload
```
