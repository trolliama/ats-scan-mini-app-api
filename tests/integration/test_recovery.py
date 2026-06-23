import asyncio
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from core.services.scan_service import recover_incomplete_scans
from infra.db.unit_of_work import UoWContext, commit, unit_of_work
from tests.factories import ATSScanResultFactory, ScanCreateFactory


@pytest.fixture
def uow(db_session_factory: sessionmaker[Session]) -> UoWContext:
    with unit_of_work(db_session_factory) as ctx:
        yield ctx


class TestRecoverIncompleteScans:
    def test_returns_pending_and_processing_scan_ids(
        self, db_session_factory: sessionmaker[Session], uow: UoWContext
    ) -> None:
        """recover_incomplete_scans returns ids for pending and processing scans only."""
        pending, processing, completed, failed = ScanCreateFactory.build_batch(4)

        for scan in (pending, processing, completed, failed):
            uow.scans.insert_pending(scan)

        uow.scans.mark_processing(str(processing.scan_id))
        uow.scans.mark_completed(
            str(completed.scan_id),
            ATSScanResultFactory.build(),
        )
        uow.scans.mark_failed(str(failed.scan_id), "error")
        commit(uow)

        scan_ids = recover_incomplete_scans(db_session_factory)

        assert set(scan_ids) == {str(pending.scan_id), str(processing.scan_id)}

    def test_returns_empty_list_when_no_incomplete_scans(
        self, db_session_factory: sessionmaker[Session]
    ) -> None:
        """recover_incomplete_scans returns an empty list when all scans are terminal."""
        scan_ids = recover_incomplete_scans(db_session_factory)

        assert scan_ids == []


class TestLifespanRecovery:
    def test_enqueues_process_scan_for_incomplete_scans_on_startup(
        self, db_session_factory: sessionmaker[Session]
    ) -> None:
        """Lifespan startup enqueues process_scan for each incomplete scan."""
        scan_ids = ["scan-a", "scan-b"]
        mock_engine = MagicMock()

        with (
            patch("infra.http.app.create_db_engine", return_value=mock_engine),
            patch("infra.http.app.get_session_factory", return_value=db_session_factory),
            patch("infra.http.app.init_db"),
            patch("infra.http.app.recover_incomplete_scans", return_value=scan_ids),
            patch("infra.http.app.process_scan") as mock_process,
            patch("infra.http.app.asyncio.create_task") as mock_create_task,
        ):
            from infra.http.app import get_app, lifespan

            app = get_app()

            async def _run_lifespan() -> None:
                async with lifespan(app):
                    await asyncio.sleep(0)

            asyncio.run(_run_lifespan())

        assert mock_create_task.call_count == len(scan_ids)
        thread_calls = [
            call.args[0] for call in mock_create_task.call_args_list
        ]
        for coro in thread_calls:
            asyncio.run(coro)
        assert mock_process.call_count == len(scan_ids)
        assert {call.args[0] for call in mock_process.call_args_list} == set(scan_ids)
        mock_engine.dispose.assert_called_once()

    def test_does_not_enqueue_when_no_incomplete_scans(
        self, db_session_factory: sessionmaker[Session]
    ) -> None:
        """Lifespan startup skips enqueue when there are no incomplete scans."""
        mock_engine = MagicMock()

        with (
            patch("infra.http.app.create_db_engine", return_value=mock_engine),
            patch("infra.http.app.get_session_factory", return_value=db_session_factory),
            patch("infra.http.app.init_db"),
            patch("infra.http.app.recover_incomplete_scans", return_value=[]),
            patch("infra.http.app.process_scan") as mock_process,
            patch("infra.http.app.asyncio.create_task") as mock_create_task,
        ):
            from infra.http.app import get_app, lifespan

            app = get_app()

            async def _run_lifespan() -> None:
                async with lifespan(app):
                    await asyncio.sleep(0)

            asyncio.run(_run_lifespan())

        mock_create_task.assert_not_called()
        mock_process.assert_not_called()
        mock_engine.dispose.assert_called_once()
