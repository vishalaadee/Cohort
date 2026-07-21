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
