import json
import os


def _load_from_secrets_manager() -> None:
    """If AWS_SECRET_NAME is set, pull ONE JSON secret from AWS Secrets
    Manager and export its keys as env vars (existing env always wins).
    One consolidated secret = $0.40/month — the whole app's config for
    less than a chai. Falls back silently to .env when unavailable, so
    local dev never needs AWS."""
    name = os.getenv("AWS_SECRET_NAME")
    if not name:
        return
    try:
        import boto3
        client = boto3.client("secretsmanager",
                              region_name=os.getenv("AWS_REGION", "ap-south-1"))
        blob = client.get_secret_value(SecretId=name)["SecretString"]
        for k, v in json.loads(blob).items():
            os.environ.setdefault(k.upper(), str(v))
        print(f"[config] loaded {name} from Secrets Manager")
    except Exception as exc:  # noqa: BLE001 — any failure => env fallback
        print(f"[config] Secrets Manager unavailable ({exc}); using env/.env")


_load_from_secrets_manager()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app_user:app_user@db:5432/placement"
    jwt_secret: str = "dev-secret-change-me"
    jwt_alg: str = "HS256"
    jwt_expiry_hours: int = 8

    # "Sign in with Google" client ID (Google Cloud Console -> OAuth client).
    # When unset, the Google button is hidden and only password login works.
    google_client_id: str | None = None

    # Trust X-Forwarded-For from the reverse proxy in front of this app.
    # Caddy terminates TLS and proxies to uvicorn, so without this every
    # request appears to come from Caddy's address and per-IP rate limiting
    # collapses into a single shared bucket. Leave at 1 for the standard
    # single-Caddy deployment; raise it only if you add another trusted hop.
    trusted_proxy_hops: int = 1


settings = Settings()


# ---------------------------------------------------------------------------
# Fail fast on a signing key that cannot protect anything.
#
# Why this is not paranoia: docker-compose passes `JWT_SECRET: ${JWT_SECRET}`.
# If .env has no JWT_SECRET line, or the value is blank, the container starts
# with JWT_SECRET set to the EMPTY STRING. pydantic-settings treats "" as a
# real value, so the `dev-secret-change-me` default above does NOT apply, and
# PyJWT will happily sign and verify HS256 with a zero-byte key — it emits a
# warning, not an error. The app boots, /api/health returns "ok", and every
# token on the platform is forgeable by anyone. Verified behaviour, not theory.
#
# Refusing to start is the only safe response: a broken deploy is recoverable,
# a silently unauthenticated one is not.
# ---------------------------------------------------------------------------
_WEAK_SECRETS = {"", "dev-secret-change-me", "changeme", "secret", "test"}


def _validate_jwt_secret() -> None:
    secret = (settings.jwt_secret or "").strip()
    if secret in _WEAK_SECRETS or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing, blank, or too short (need >= 32 chars). "
            "Tokens signed with a weak or empty key can be forged by anyone. "
            "Generate one with:  openssl rand -hex 32   "
            "then set JWT_SECRET in .env and recreate the backend container. "
            "Refusing to start."
        )


if os.getenv("ALLOW_WEAK_JWT_SECRET") != "1":
    _validate_jwt_secret()
