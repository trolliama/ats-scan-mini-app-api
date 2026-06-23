from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from infra.db.models import Base

_MEMORY_SQLITE_PATH = Path(":memory:")


def ensure_db_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(path: Path) -> Engine:
    if path == _MEMORY_SQLITE_PATH:
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    ensure_db_directory(path)
    return create_engine(f"sqlite:///{path}")


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
