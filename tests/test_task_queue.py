"""Archive task lifecycle regressions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from custom_components.si_grid_monitor.archive import ArchiveRecord, QuarterArchive
from custom_components.si_grid_monitor.task_queue import ArchiveTaskQueue


def record(start: datetime) -> ArchiveRecord:
    return ArchiveRecord(
        namespace="meter-a",
        start_utc=start,
        end_utc=start.replace(minute=15),
        import_kwh=1.0,
        export_kwh=0.0,
        signed_average_kw=4.0,
        import_demand_kw=4.0,
        coverage_seconds=900,
        gap_seconds=0,
        quality="reconstructed",
        provenance="live_reconstructed",
        source_id="sensor.grid",
        source_epoch=1,
        configuration_status="known",
        contractual_target_kw=4.6,
        safety_margin_kw=0.0,
        operational_target_kw=4.6,
        utilization_pct=100 * 4 / 4.6,
        exceeded=False,
        excess_kw=0.0,
    )


def test_reload_after_boundary_waits_for_quarter_and_checkpoint_before_close(tmp_path) -> None:
    """A reload cannot close SQLite ahead of just-scheduled boundary writes."""

    path = tmp_path / "archive.db"
    archive = QuarterArchive(path)
    archive.open()
    start = datetime(2026, 1, 1, tzinfo=UTC)

    # Home Assistant runs these operations in its executor. Model the same ordering:
    # both durable futures must complete before shutdown closes the connection.
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = (
            executor.submit(archive.upsert_quarter, record(start)),
            executor.submit(
                archive.save_checkpoint,
                "meter-a",
                {"schema": 1, "quarter_start_utc": start.isoformat()},
            ),
        )
        for operation in pending:
            operation.result(timeout=5)
    archive.close()

    reopened = QuarterArchive(path)
    reopened.open()
    assert len(reopened.list_quarters("meter-a", start, record(start).end_utc)) == 1
    assert reopened.load_checkpoint("meter-a") is not None
    reopened.close()


class _FinishedTask:
    """Small Task test double for callback/error-observation behavior."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.callback = None
        self.result_observed = False

    def add_done_callback(self, callback) -> None:
        self.callback = callback

    def cancelled(self) -> bool:
        return False

    def result(self) -> None:
        self.result_observed = True
        if self.error is not None:
            raise self.error

    def get_name(self) -> str:
        return "test archive task"


def test_task_queue_observes_failures_and_removes_completed_task(caplog) -> None:
    queue = ArchiveTaskQueue()
    task = _FinishedTask(RuntimeError("expected test failure"))

    queue.track(task)  # type: ignore[arg-type]
    assert task.callback is not None
    task.callback(task)

    assert task.result_observed
    assert queue._tasks == set()
    assert "Archive task failed: test archive task" in caplog.text
