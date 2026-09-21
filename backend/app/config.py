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

    # Real login exists now, so this defaults OFF. Set env DEV_FALLBACK=true
    # for local demos only: unauthenticated requests then act as the demo admin.
    dev_fallback: bool = False


settings = Settings()
