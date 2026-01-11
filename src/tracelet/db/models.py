from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy import Enum as SQLEnum
from datetime import datetime, timezone
from enum import Enum
from tracelet.utils.logger_config import logger

Base = declarative_base()

class EndpointStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"

class Endpoints(Base):

    __tablename__ = 'tracelet_endpoints'

    endpoint_id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(nullable=False)
    method: Mapped[str] = mapped_column(nullable=False)
    framework: Mapped[str] = mapped_column(nullable=False)
    deprecated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('path', 'method', 'framework', name='_path_method_framework_uc'),
        Index('idx_path_method_fw', 'path', 'method', 'framework'),
    )


class Metrics(Base):

    __tablename__ = 'tracelet_metrics'
    
    metrics_id: Mapped[int] = mapped_column(primary_key=True)
    unique_id: Mapped[str] = mapped_column(index=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("tracelet_endpoints.endpoint_id"), nullable=False)
    request_time: Mapped[datetime] = mapped_column(nullable=False)
    response_time: Mapped[datetime] = mapped_column(nullable=False)
    latency_ms: Mapped[float] = mapped_column(nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    response_status: Mapped[EndpointStatus] = mapped_column(SQLEnum(EndpointStatus), default=EndpointStatus.SUCCESS)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_metrics_endpoint_created_at', 'endpoint_id', 'created_at'),
    )

class Buckets(Base):
    __tablename__ = 'tracelet_latency_buckets'

    bucket_id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("tracelet_endpoints.endpoint_id"), nullable=False)
    le: Mapped[float] = mapped_column(nullable=False)
    count: Mapped[int] = mapped_column(default=0)
    captured_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint('endpoint_id', 'le', 'captured_at', name='_endpoint_bucket_snapshot_uc'),
        Index('idx_le_captured', 'le', 'captured_at'),
        Index('idx_buckets_endpoint_captured_at', 'endpoint_id', 'captured_at'),
        Index('idx_buckets_captured_at', 'captured_at'),
    )

def create_tables(force_creation=False):
    from tracelet import settings

    # Check if init() was called
    if not hasattr(settings, 'engine'):
        raise RuntimeError(
            "Tracelet not initialized. Please call tracelet.init() before creating tables."
        )

    engine = settings.engine
    if not settings.tables_created or force_creation:
        if settings.enabled:
            prev_echo = getattr(engine, 'echo', False)
            try:
                engine.echo = True
                Base.metadata.create_all(bind=engine)
                settings.tables_created = True
                logger.info("Tables created successfully!!!")
            except Exception as e:
                logger.error("Failed to create tables: %s", e)
                raise RuntimeError(f"Failed to create tables: {e}")
            finally:
                engine.echo = prev_echo