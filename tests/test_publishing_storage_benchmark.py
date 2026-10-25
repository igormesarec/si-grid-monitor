"""Reproducible storage benchmark for the optimized publishing profile.

This intentionally writes isolated SQLite tables and indexes so the assertion
is based on allocated pages, not callback counts alone.  InfluxDB is not an
available CI service; its line/series overhead is therefore a documented,
conservative per-publication estimate and remains a manual acceptance item.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from custom_components.si_grid_monitor.publishing import (
    STORAGE_BUDGET_BYTES_PER_YEAR,
    PublicationState,
    PublishingClass,
    PublishingController,
    PublishingSettings,
)


def _allocated_bytes(connection: sqlite3.Connection) -> int:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


def test_two_meter_optimized_profile_projects_below_one_gb(tmp_path: Path) -> None:
    database = sqlite3.connect(tmp_path / "publishing-benchmark.sqlite")
    database.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE state_attributes (
            attributes_id INTEGER PRIMARY KEY,
            shared_attrs TEXT NOT NULL UNIQUE
        );
        CREATE TABLE states (
            state_id INTEGER PRIMARY KEY,
            meter INTEGER NOT NULL,
            entity_key TEXT NOT NULL,
            state TEXT,
            attributes_id INTEGER NOT NULL,
            updated_ts REAL NOT NULL
        );
        CREATE INDEX ix_states_meter_time ON states(meter, updated_ts);
        CREATE INDEX ix_states_entity_time ON states(entity_key, updated_ts);
        CREATE TABLE quarter_archive (
            meter INTEGER NOT NULL,
            start_utc TEXT NOT NULL,
            import_kwh REAL NOT NULL,
            export_kwh REAL,
            target_kw REAL,
            quality TEXT NOT NULL,
            provenance TEXT NOT NULL,
            PRIMARY KEY (meter, start_utc)
        );
        """
    )
    settings = PublishingSettings.from_mapping({})
    controllers: list[PublishingController] = []
    mutable: list[dict[str, float | bool]] = []

    def write_state(meter: int, key: str, state: dict[str, float | bool]) -> None:
        attributes = json.dumps(
            {"source_mode": "signed_power", "measurement_kind": "live_power"},
            sort_keys=True,
        )
        database.execute(
            "INSERT OR IGNORE INTO state_attributes(shared_attrs) VALUES (?)",
            (attributes,),
        )
        attributes_id = database.execute(
            "SELECT attributes_id FROM state_attributes WHERE shared_attrs = ?",
            (attributes,),
        ).fetchone()[0]
        database.execute(
            "INSERT INTO states(meter, entity_key, state, attributes_id, updated_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (meter, key, str(state["value"]), attributes_id, state["timestamp"]),
        )

    for meter in range(2):
        controller = PublishingController(settings)
        controllers.append(controller)
        for index in range(48):
            state: dict[str, float | bool] = {"value": 0.0, "timestamp": 0.0}
            mutable.append(state)
            if index < 16:
                publishing_class = PublishingClass.MONITORING
            elif index < 24:
                publishing_class = PublishingClass.ACTIONABLE
            elif index < 27:
                publishing_class = PublishingClass.CRITICAL
            elif index < 36:
                publishing_class = PublishingClass.DIAGNOSTIC
            else:
                publishing_class = PublishingClass.CONFIGURATION
            key = f"entity_{index:02d}_kw"
            controller.register(
                key,
                publishing_class,
                lambda current=state: PublicationState(current["value"], True, {}),
                lambda meter=meter, key=key, current=state: write_state(meter, key, current),
            )

    start = datetime(2026, 10, 24, tzinfo=UTC)
    for second in range(24 * 60 * 60):
        now = start + timedelta(seconds=second)
        # Continuously varying household demand, overnight zeros, PV export,
        # load steps and one stale/recovery-like critical transition.
        hour = second / 3600
        signed_kw = 1.8 + 1.2 * math.sin(hour * math.pi / 6)
        if 1 <= hour < 4:
            signed_kw = 0.0
        if 10 <= hour < 15:
            signed_kw = -max(0.0, 2.5 * math.sin((hour - 10) * math.pi / 5))
        if second % 7200 < 120:
            signed_kw += 4.0
        for meter, controller in enumerate(controllers):
            offset = meter * 48
            for index in range(48):
                state = mutable[offset + index]
                state["timestamp"] = now.timestamp()
                if index < 16:
                    state["value"] = signed_kw + index * 0.003
                elif index < 24:
                    state["value"] = max(0.0, 3.0 - signed_kw) + index * 0.002
                elif index < 27:
                    state["value"] = bool(
                        (index == 24 and 18 * 3600 <= second < 18 * 3600 + 30)
                        or (index == 25 and 20 * 3600 <= second < 20 * 3600 + 60)
                    )
                elif index < 36:
                    state["value"] = float(second % 900)
                else:
                    state["value"] = float(index)
            controller.process(now)

    # The measured day is replayed into a representative seven-day allocation
    # with different timestamps. This measures SQLite row/index growth while
    # the controller's one-second behavior is exercised above for a full day.
    daily_rows = database.execute(
        "SELECT meter, entity_key, state, attributes_id, updated_ts FROM states"
    ).fetchall()
    for day in range(1, 7):
        shift = day * 86400
        database.executemany(
            "INSERT INTO states(meter, entity_key, state, attributes_id, updated_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            [(*row[:4], float(row[4]) + shift) for row in daily_rows],
        )
    for meter in range(2):
        for quarter in range(7 * 96):
            quarter_start = start + timedelta(minutes=15 * quarter)
            database.execute(
                "INSERT INTO quarter_archive VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    meter,
                    quarter_start.isoformat(),
                    0.25,
                    0.0,
                    4.2,
                    "measured_aligned",
                    "benchmark source epoch and tariff metadata",
                ),
            )
    database.commit()
    database.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    seven_day_sqlite_bytes = _allocated_bytes(database)
    seven_day_publications = int(database.execute("SELECT COUNT(*) FROM states").fetchone()[0])
    database.close()

    annual_sqlite = seven_day_sqlite_bytes / 7 * 365
    # Conservative line-protocol/series allowance because CI does not provide
    # a real InfluxDB daemon. The manual plan requires measuring this directly.
    annual_influx_estimate = seven_day_publications / 7 * 365 * 140
    annual_total = annual_sqlite + annual_influx_estimate

    assert all(controller.calculation_cycles == 86400 for controller in controllers)
    assert annual_total <= STORAGE_BUDGET_BYTES_PER_YEAR
