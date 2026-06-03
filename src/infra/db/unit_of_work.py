from collections.abc import Generator
from contextlib import contextmanager
from typing import NamedTuple

from sqlalchemy.orm import Session, sessionmaker

from infra.db.scan_repository import ScanRepository


class UoWContext(NamedTuple):
    session: Session
    scans: ScanRepository


@contextmanager
def unit_of_work(
    session_factory: sessionmaker[Session],
) -> Generator[UoWContext, None, None]:
    session = session_factory()
    try:
        yield UoWContext(session=session, scans=ScanRepository(session))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def commit(ctx: UoWContext) -> None:
    ctx.session.commit()
