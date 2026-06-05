from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class DeviceBase(BaseModel):
    name: str
    platform: str = "other"
    srs_stream_key: str
    srs_app: str = "live"
    enabled: bool = True
    guacamole_url: Optional[str] = None
    notes: Optional[str] = None


class DeviceInput(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    srs_stream_key: Optional[str] = None
    srs_app: Optional[str] = None
    enabled: Optional[bool] = None
    guacamole_url: Optional[str] = None
    notes: Optional[str] = None


class DeviceOut(DeviceBase):
    id: int
    current_status: str
    last_checked_at: Optional[datetime] = None
    failure_reason: Optional[str] = None

    class Config:
        from_attributes = True


class HlsStreamBase(BaseModel):
    name: str
    master_url: str
    enabled: bool = True
    expected_renditions: Optional[int] = None
    is_encrypted: bool = False
    notes: Optional[str] = None


class HlsStreamInput(HlsStreamBase):
    pass


class HlsStreamUpdate(BaseModel):
    name: Optional[str] = None
    master_url: Optional[str] = None
    enabled: Optional[bool] = None
    expected_renditions: Optional[int] = None
    is_encrypted: Optional[bool] = None
    notes: Optional[str] = None


class HlsStreamOut(HlsStreamBase):
    id: int
    current_status: str
    last_checked_at: Optional[datetime] = None
    failure_reason: Optional[str] = None

    class Config:
        from_attributes = True


class CheckResultOut(BaseModel):
    id: int
    device_id: Optional[int] = None
    hls_stream_id: Optional[int] = None
    timestamp: datetime
    status: str
    detail: Optional[dict] = None
    frame_thumbnail_path: Optional[str] = None

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: int
    device_id: Optional[int] = None
    hls_stream_id: Optional[int] = None
    device_name: Optional[str] = None
    hls_stream_name: Optional[str] = None
    item_type: Optional[str] = None
    started_at: datetime
    resolved_at: Optional[datetime] = None
    status: str
    reason: str
    acknowledged_by: Optional[str] = None

    class Config:
        from_attributes = True


class AcknowledgeInput(BaseModel):
    acknowledged_by: str


class SettingOut(BaseModel):
    key: str
    value: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class SettingItem(BaseModel):
    key: str
    value: str


class SettingsUpdate(BaseModel):
    settings: list[SettingItem]


class ItemStats(BaseModel):
    uptime_pct: float
    total_incidents: int
    mttr_seconds: Optional[float] = None
    window: str


class DashboardSummary(BaseModel):
    total_devices: int
    total_hls_streams: int
    devices_down: int
    devices_warning: int
    devices_healthy: int
    devices_unknown: int
    hls_down: int
    hls_warning: int
    hls_healthy: int
    hls_unknown: int
    open_incidents: int
