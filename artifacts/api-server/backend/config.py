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

    slack_webhook_url: str = ""
    discord_webhook_url: str = ""
    generic_webhook_url: str = ""
    alert_on_warning: bool = False
    alerts_enabled: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
