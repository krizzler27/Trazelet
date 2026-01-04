from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import ForeignKey, JSON, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from datetime import datetime, timezone
from tracelet.db.config import engine
from enum import Enum

Base = declarative_base()

class APIStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"

class APIs(Base):

    __tablename__ = 'apis'

    api_id: Mapped[int] = mapped_column(primary_key=True)
    api_url_path: Mapped[str] = mapped_column(index=True, nullable=False)
    framework: Mapped[str] = mapped_column(nullable=False)
    deprecated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('api_url_path', 'framework', name='_path_framework_uc'),
    )


class Metrics(Base):

    __tablename__ = 'metrics'
    
    metrics_id: Mapped[int] = mapped_column(primary_key=True)
    unique_id: Mapped[str] = mapped_column(index=True)
    api_url_id: Mapped[int] = mapped_column(ForeignKey("apis.api_id"), nullable=False)
    requested_time: Mapped[datetime] = mapped_column(nullable=False)
    responded_time: Mapped[datetime] = mapped_column(nullable=False)
    time_taken_secs: Mapped[float] = mapped_column(nullable=False)
    time_taken_ms: Mapped[float] = mapped_column(nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    response_status: Mapped[APIStatus] = mapped_column(SQLEnum(APIStatus), default=APIStatus.SUCCESS)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


def create_tables():
    engine.echo = True
    Base.metadata.create_all(bind=engine)
    engine.echo = False
    print("Tables created successfully!!!")

# create_tables()
