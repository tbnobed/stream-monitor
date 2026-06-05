from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Setting
from schemas import SettingOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULT_SETTINGS = {
    "srs_whep_base_url": ("http://cdn1.obedtv.live:2023", "SRS WHEP base URL"),
    "srs_api_base_url": ("http://cdn1.obedtv.live:1985/api/v1", "SRS HTTP API base URL"),
    "rtmp_ingest_base_url": ("rtmp://cdn1.obedtv.live:1935/live", "RTMP ingest base URL"),
    "guacamole_base_url": ("http://cdn3.obedtv.live:8088/guacamole", "Guacamole base URL"),
    "device_check_interval": ("15", "Device health check interval (seconds)"),
    "hls_check_interval": ("30", "HLS stream check interval (seconds)"),
    "debounce_count": ("2", "Consecutive checks before status change"),
    "max_concurrent_ffmpeg": ("4", "Max concurrent ffmpeg/ffprobe processes"),
    "ffprobe_enabled": ("true", "Enable ffprobe deep validation for HLS segments"),
    "segment_stall_threshold": ("2", "Polls before flagging stalled stream"),
    "blackdetect_duration": ("2.0", "ffmpeg blackdetect duration threshold (s)"),
    "blackdetect_threshold": ("0.10", "ffmpeg blackdetect pixel threshold"),
    "freezedetect_duration": ("2.0", "ffmpeg freezedetect duration (s)"),
    "silencedetect_noise": ("-50dB", "ffmpeg silencedetect noise threshold"),
    "silencedetect_duration": ("3.0", "ffmpeg silencedetect duration (s)"),
    "alerts_enabled": ("true", "Enable alerting"),
    "alert_on_warning": ("false", "Send alerts for WARNING status too"),
    "slack_webhook_url": ("", "Slack incoming webhook URL"),
    "discord_webhook_url": ("", "Discord webhook URL"),
    "generic_webhook_url": ("", "Generic webhook URL"),
}


def ensure_defaults(db: Session):
    """Seed default settings if not present."""
    for key, (value, description) in DEFAULT_SETTINGS.items():
        existing = db.query(Setting).filter(Setting.key == key).first()
        if not existing:
            db.add(Setting(key=key, value=value, description=description))
    db.commit()


@router.get("/", response_model=list[SettingOut])
def list_settings(db: Session = Depends(get_db)):
    ensure_defaults(db)
    return db.query(Setting).order_by(Setting.key).all()


@router.patch("/", response_model=list[SettingOut])
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    for item in body.settings:
        setting = db.query(Setting).filter(Setting.key == item.key).first()
        if setting:
            setting.value = item.value
        else:
            description = DEFAULT_SETTINGS.get(item.key, ("", ""))[1]
            db.add(Setting(key=item.key, value=item.value, description=description))
    db.commit()
    return db.query(Setting).order_by(Setting.key).all()
