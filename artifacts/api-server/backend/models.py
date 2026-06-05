from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False, default="other")
    srs_stream_key = Column(String(255), nullable=False)
    srs_app = Column(String(100), nullable=False, default="live")
    enabled = Column(Boolean, nullable=False, default=True)
    webrtc_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    current_status = Column(String(20), nullable=False, default="UNKNOWN")
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    consecutive_status_count = Column(Integer, nullable=False, default=0)
    pending_status = Column(String(20), nullable=True)
    ip_address = Column(String(64), nullable=True)
    remote_config = Column(JSON, nullable=True)

    check_results = relationship("CheckResult", back_populates="device", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="device", cascade="all, delete-orphan")


class HlsStream(Base):
    __tablename__ = "hls_streams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    master_url = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    expected_renditions = Column(Integer, nullable=True)
    is_encrypted = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    current_status = Column(String(20), nullable=False, default="UNKNOWN")
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    consecutive_status_count = Column(Integer, nullable=False, default=0)
    pending_status = Column(String(20), nullable=True)
    last_media_sequence = Column(Integer, nullable=True)
    stall_check_count = Column(Integer, nullable=False, default=0)

    check_results = relationship("CheckResult", back_populates="hls_stream", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="hls_stream", cascade="all, delete-orphan")


class CheckResult(Base):
    __tablename__ = "check_results"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    hls_stream_id = Column(Integer, ForeignKey("hls_streams.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False)
    detail = Column(JSON, nullable=True)
    frame_thumbnail_path = Column(Text, nullable=True)

    device = relationship("Device", back_populates="check_results")
    hls_stream = relationship("HlsStream", back_populates="check_results")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    hls_stream_id = Column(Integer, ForeignKey("hls_streams.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="open")
    reason = Column(Text, nullable=False)
    acknowledged_by = Column(String(255), nullable=True)

    device = relationship("Device", back_populates="incidents")
    hls_stream = relationship("HlsStream", back_populates="incidents")


class GuacamoleSession(Base):
    __tablename__ = "guacamole_sessions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    # Null for SSO-only accounts that never set a local password.
    password_hash = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default="operator")  # admin | operator
    auth_provider = Column(String(20), nullable=False, default="local")  # local | oidc
    oidc_subject = Column(String(255), nullable=True, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
