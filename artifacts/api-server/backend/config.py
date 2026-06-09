import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.environ.get("DATABASE_URL", "")
    port: int = int(os.environ.get("PORT", "8080"))

    srs_whep_base_url: str = "http://cdn1.obedtv.live:2023"
    srs_api_base_url: str = "http://cdn1.obedtv.live:1985/api/v1"
    rtmp_ingest_base_url: str = "rtmp://cdn1.obedtv.live:1935/live"
    guacamole_base_url: str = "http://cdn3.obedtv.live:8088/guacamole"

    device_check_interval: int = 15
    hls_check_interval: int = 30
    debounce_count: int = 2
    max_concurrent_ffmpeg: int = 4
    ffprobe_enabled: bool = True

    blackdetect_duration: float = 2.0
    blackdetect_threshold: float = 0.10
    freezedetect_noise: float = 0.003
    freezedetect_duration: float = 2.0
    silencedetect_noise: str = "-50dB"
    silencedetect_duration: float = 3.0
    segment_stall_threshold: int = 2

    # Grace period (seconds) before a sustained BLACK screen escalates a device
    # to DOWN. Some channels load a black slate for a minute or two before the
    # show actually starts, which would otherwise alert immediately. A black
    # screen is also a frozen one, so the freeze verdict is suppressed for the
    # same window. Configurable via the BLACK_GRACE_SECONDS env var (.env).
    black_grace_seconds: float = float(os.environ.get("BLACK_GRACE_SECONDS", "300"))

    slack_webhook_url: str = ""
    discord_webhook_url: str = ""
    generic_webhook_url: str = ""
    alert_on_warning: bool = False
    alerts_enabled: bool = True

    # --- Email alerts (SendGrid) ---
    # Email is enabled only when both the API key and a verified sender address
    # are set. Recipients are configured in-app (Settings -> alert_email_recipients).
    sendgrid_api_key: str = os.environ.get("SENDGRID_API_KEY", "")
    alert_from_email: str = os.environ.get("ALERT_FROM_EMAIL", "")
    alert_from_name: str = os.environ.get("ALERT_FROM_NAME", "OTT Stream Monitor")

    # --- Authentication ---
    session_secret: str = os.environ.get("SESSION_SECRET", "")
    # Set true only when served over HTTPS (e.g. behind a TLS terminator). The
    # self-hosted LAN deploy runs over plain HTTP, so this defaults to false.
    session_cookie_secure: bool = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

    # Authentik / OIDC SSO (optional). When all three are set, SSO is enabled.
    oidc_client_id: str = os.environ.get("OIDC_CLIENT_ID", "")
    oidc_client_secret: str = os.environ.get("OIDC_CLIENT_SECRET", "")
    # Full OIDC discovery document URL, e.g.
    # https://authentik.example.com/application/o/<slug>/.well-known/openid-configuration
    oidc_discovery_url: str = os.environ.get("OIDC_DISCOVERY_URL", "")
    # Optional fixed callback URL (recommended behind a reverse proxy), e.g.
    # http://noc.example.com/api/auth/sso/callback
    oidc_redirect_uri: str = os.environ.get("OIDC_REDIRECT_URI", "")
    oidc_display_name: str = os.environ.get("OIDC_DISPLAY_NAME", "SSO")

    # First-run admin bootstrap (only used when there are zero users).
    initial_admin_username: str = os.environ.get("INITIAL_ADMIN_USERNAME", "admin")
    # Empty by default so first-boot bootstrap generates a random one-time
    # password instead of a guessable "admin". Set this env var to choose your own.
    initial_admin_password: str = os.environ.get("INITIAL_ADMIN_PASSWORD", "")

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_client_id and self.oidc_client_secret and self.oidc_discovery_url)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
