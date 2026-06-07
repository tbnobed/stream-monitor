from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Any
from datetime import datetime


class LogoRegion(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)


class DeviceBase(BaseModel):
    name: str
    platform: str = "other"
    srs_stream_key: str
    srs_app: str = "live"
    enabled: bool = True
    webrtc_url: Optional[str] = None
    notes: Optional[str] = None
    ip_address: Optional[str] = None
    logo_check_enabled: bool = False
    logo_region: Optional[LogoRegion] = None
    logo_match_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class DeviceInput(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    srs_stream_key: Optional[str] = None
    srs_app: Optional[str] = None
    enabled: Optional[bool] = None
    webrtc_url: Optional[str] = None
    notes: Optional[str] = None
    ip_address: Optional[str] = None
    logo_check_enabled: Optional[bool] = None
    logo_region: Optional[LogoRegion] = None
    logo_match_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class DeviceOut(DeviceBase):
    id: int
    current_status: str
    last_checked_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    # Derived remote-control metadata (never exposes raw credentials).
    remote_protocol: Optional[str] = None
    remote_capable: bool = False
    remote_requires_pairing: bool = False
    remote_paired: bool = False
    # True once a logo reference template has been captured (template not exposed).
    logo_reference_set: bool = False

    class Config:
        from_attributes = True


class LogoReferenceRequest(BaseModel):
    region: LogoRegion
    save: bool = False
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class LogoReferenceResult(BaseModel):
    captured: bool
    message: Optional[str] = None
    snapshot: Optional[str] = None  # data URL (JPEG) of the full frame
    crop: Optional[str] = None      # data URL (PNG) of the cropped region
    width: Optional[int] = None
    height: Optional[int] = None
    saved: bool = False
    # Live NCC of the current region crop vs the already-saved reference template
    # (-1..1), so the operator can see how strongly this region matches before
    # trusting the threshold. None when no reference is saved yet.
    match_score: Optional[float] = None
    # The region actually stored after the server auto-tightened the operator's
    # drawn box onto the logo (normalized fractions). Present when saved.
    region: Optional[LogoRegion] = None
    # True when auto-tighten moved/shrank the operator's box onto the logo.
    tightened: bool = False


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


class GuacamoleSessionBase(BaseModel):
    name: str
    url: str
    notes: Optional[str] = None
    enabled: bool = True


class GuacamoleSessionInput(GuacamoleSessionBase):
    pass


class GuacamoleSessionUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None


class GuacamoleSessionOut(GuacamoleSessionBase):
    id: int

    class Config:
        from_attributes = True


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


class RemoteKeyInput(BaseModel):
    key: str


class RemoteLaunchInput(BaseModel):
    app_id: str


class RemotePairFinishInput(BaseModel):
    pin: Optional[str] = None


class RemoteAppOut(BaseModel):
    id: str
    name: str


class RemoteStatusOut(BaseModel):
    protocol: Optional[str] = None
    capable: bool = False
    reachable: bool = False
    paired: bool = False
    requires_pairing: bool = False
    detail: Optional[str] = None


class RemoteCapabilitiesOut(BaseModel):
    protocol: Optional[str] = None
    capable: bool = False
    requires_pairing: bool = False
    supports_app_launch: bool = False
    keys: list[str] = []
    apps: list[RemoteAppOut] = []


class RemoteActionResult(BaseModel):
    ok: bool
    detail: Optional[str] = None


class RemotePairBeginOut(BaseModel):
    ok: bool
    requires_pin: bool
    message: str


class MobileTokenOut(BaseModel):
    token: str
    ttl_seconds: int


class MobileRemoteSession(BaseModel):
    device_id: int
    device_name: str
    platform: Optional[str] = None
    protocol: Optional[str] = None
    capable: bool = False
    reachable: bool = False
    paired: bool = False
    requires_pairing: bool = False
    keys: list[str] = []
    detail: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    auth_provider: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: str = "operator"


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class LoginInput(BaseModel):
    username: str
    password: str


class AuthConfig(BaseModel):
    sso_enabled: bool
    sso_label: str


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
