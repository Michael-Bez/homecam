import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy import (

    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    select,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class Event(Base):

    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    ts = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    kind = Column(String, nullable=False)   # 'motion' (PIR) | 'manual' (dashboard snapshot)
    snapshot = Column(Text)                 # relative path under SNAPSHOT_DIR
    s3_uploaded = Column(Boolean, default=False)


class Config(Base):


    """Key-value store for mode and schedule. Seeded on first start."""

    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


def get_engine():
    url = os.environ["DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


def wait_for_db(engine, retries: int = 15, delay: float = 2.0) -> None:
    
    """
    Block until Postgres accepts a connection.

    compose starts the db container before app, but Postgres needs a few
    seconds to initialise inside the container.   pool_pre_ping alone is not
    enough on the very first startup.
    """
    for attempt in range(1, retries + 1):
        try:
            with engine.connect():
                return
        except Exception as exc:
            log.warning("DB not ready (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(delay)
    raise RuntimeError("Could not connect to database after %d attempts" % retries)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
    _seed_config(engine)
    log.info("DB schema ready")


def _seed_config(engine) -> None:
    """Insert default config rows only if the table is empty."""
    with Session(engine) as session:
        if session.scalar(select(func.count()).select_from(Config)) > 0:
            return
        session.add_all(
            [
                Config(key="current_mode", value="Stealth"),
                Config(key="schedule_start", value="22:00"),
                Config(key="schedule_end", value="06:00"),
                Config(key="timezone", value="Africa/Johannesburg"),
            ]
        )
        session.commit()
        log.info("Config table seeded with defaults")
