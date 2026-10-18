"""Permanent, namespaced SQLite quarter archive for SI Grid Monitor."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .engine import LJUBLJANA, DataQuality

SCHEMA_VERSION = 1
_QUALITY_RANK = {
    DataQuality.UNAVAILABLE.value: 0,
    DataQuality.INCOMPLETE.value: 1,
    DataQuality.RECONSTRUCTED.value: 2,
    DataQuality.COUNTER_DERIVED.value: 3,
    DataQuality.MEASURED_ALIGNED.value: 4,
}


@dataclass(frozen=True, slots=True)
class ArchiveRecord:
    """One completed fixed quarter with its as-of configuration."""

    namespace: str
    start_utc: datetime
    end_utc: datetime
    import_kwh: float
    export_kwh: float
    signed_average_kw: float
    import_demand_kw: float
    coverage_seconds: float
    gap_seconds: float
    quality: str
    provenance: str
    source_id: str
    source_epoch: int
    contractual_target_kw: float | None
    safety_margin_kw: float
    operational_target_kw: float | None
    utilization_pct: float | None
    exceeded: bool | None
    excess_kw: float | None
    simulation: bool = False
    tariff_block: int | None = None
    tariff_rule_version: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveSummary:
    """Aggregate that preserves the individual-quarter maximum."""

    valid_count: int
    incomplete_count: int
    exceeded_count: int
    import_kwh: float
    export_kwh: float
    maximum_import_demand_kw: float | None
    average_import_demand_kw: float | None
    minimum_signed_average_kw: float | None
    maximum_signed_average_kw: float | None


class QuarterArchive:
    """Thread-safe synchronous SQLite API; HA callers use an executor."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    def open(self) -> None:
        """Open and migrate the archive without deleting existing data."""

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            self._connection = connection
            self._migrate()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @property
    def schema_version(self) -> int:
        with self._lock:
            row = self._db.execute("PRAGMA user_version").fetchone()
            return int(row[0])

    def register_source_epoch(
        self,
        *,
        namespace: str,
        source_id: str,
        positive_means_import: bool,
        effective_utc: datetime,
    ) -> int:
        """Return a stable epoch, creating one when source semantics change."""

        effective = _utc_iso(effective_utc)
        with self._lock, self._db:
            row = self._db.execute(
                """SELECT epoch, source_id, positive_means_import
                   FROM source_epochs WHERE namespace=? ORDER BY epoch DESC LIMIT 1""",
                (namespace,),
            ).fetchone()
            if (
                row
                and row["source_id"] == source_id
                and bool(row["positive_means_import"]) == bool(positive_means_import)
            ):
                return int(row["epoch"])
            epoch = 1 if row is None else int(row["epoch"]) + 1
            self._db.execute(
                """INSERT INTO source_epochs
                   (namespace, epoch, source_id, positive_means_import, effective_utc)
                   VALUES (?, ?, ?, ?, ?)""",
                (namespace, epoch, source_id, int(positive_means_import), effective),
            )
            return epoch

    def upsert_quarter(self, record: ArchiveRecord) -> bool:
        """Insert exactly once; replace only with equal-or-better provenance quality."""

        start = _utc_iso(record.start_utc)
        with self._lock, self._db:
            existing = self._db.execute(
                "SELECT quality, provenance FROM quarters WHERE namespace=? AND start_utc=?",
                (record.namespace, start),
            ).fetchone()
            if existing and _QUALITY_RANK.get(record.quality, -1) < _QUALITY_RANK.get(
                str(existing["quality"]), -1
            ):
                return False
            if (
                existing
                and _QUALITY_RANK.get(record.quality, -1)
                == _QUALITY_RANK.get(str(existing["quality"]), -1)
                and str(existing["provenance"]).startswith("live")
                and record.provenance.startswith("recorder")
            ):
                return False
            local = record.start_utc.astimezone(LJUBLJANA)
            values = (
                record.namespace,
                start,
                _utc_iso(record.end_utc),
                local.isoformat(),
                int(local.utcoffset().total_seconds()),
                int(local.fold),
                record.import_kwh,
                record.export_kwh,
                record.signed_average_kw,
                record.import_demand_kw,
                record.coverage_seconds,
                record.gap_seconds,
                record.quality,
                record.provenance,
                record.source_id,
                record.source_epoch,
                record.contractual_target_kw,
                record.safety_margin_kw,
                record.operational_target_kw,
                record.utilization_pct,
                None if record.exceeded is None else int(record.exceeded),
                record.excess_kw,
                int(record.simulation),
                record.tariff_block,
                record.tariff_rule_version,
                _utc_iso(datetime.now(UTC)),
            )
            self._db.execute(
                """INSERT INTO quarters (
                    namespace,start_utc,end_utc,start_local,utc_offset_seconds,fold,
                    import_kwh,export_kwh,signed_average_kw,import_demand_kw,
                    coverage_seconds,gap_seconds,quality,provenance,source_id,
                    source_epoch,contractual_target_kw,safety_margin_kw,
                    operational_target_kw,utilization_pct,exceeded,excess_kw,
                    simulation,tariff_block,tariff_rule_version,created_utc)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(namespace,start_utc) DO UPDATE SET
                    end_utc=excluded.end_utc,start_local=excluded.start_local,
                    utc_offset_seconds=excluded.utc_offset_seconds,fold=excluded.fold,
                    import_kwh=excluded.import_kwh,export_kwh=excluded.export_kwh,
                    signed_average_kw=excluded.signed_average_kw,
                    import_demand_kw=excluded.import_demand_kw,
                    coverage_seconds=excluded.coverage_seconds,
                    gap_seconds=excluded.gap_seconds,quality=excluded.quality,
                    provenance=excluded.provenance,source_id=excluded.source_id,
                    source_epoch=excluded.source_epoch,
                    contractual_target_kw=excluded.contractual_target_kw,
                    safety_margin_kw=excluded.safety_margin_kw,
                    operational_target_kw=excluded.operational_target_kw,
                    utilization_pct=excluded.utilization_pct,
                    exceeded=excluded.exceeded,excess_kw=excluded.excess_kw,
                    simulation=excluded.simulation,tariff_block=excluded.tariff_block,
                    tariff_rule_version=excluded.tariff_rule_version""",
                values,
            )
            return existing is None

    def save_checkpoint(self, namespace: str, payload: dict[str, Any]) -> None:
        """Atomically replace a bounded-frequency current-quarter checkpoint."""

        with self._lock, self._db:
            self._db.execute(
                """INSERT INTO checkpoints(namespace,payload_json,updated_utc)
                   VALUES(?,?,?) ON CONFLICT(namespace) DO UPDATE SET
                   payload_json=excluded.payload_json,updated_utc=excluded.updated_utc""",
                (namespace, json.dumps(payload, sort_keys=True), _utc_iso(datetime.now(UTC))),
            )

    def load_checkpoint(self, namespace: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT payload_json FROM checkpoints WHERE namespace=?", (namespace,)
            ).fetchone()
            return None if row is None else json.loads(str(row["payload_json"]))

    def list_quarters(
        self, namespace: str, start_utc: datetime, end_utc: datetime
    ) -> list[sqlite3.Row]:
        with self._lock:
            return list(
                self._db.execute(
                    """SELECT * FROM quarters WHERE namespace=? AND start_utc>=?
                       AND start_utc<? ORDER BY start_utc""",
                    (namespace, _utc_iso(start_utc), _utc_iso(end_utc)),
                ).fetchall()
            )

    def latest_quarter_end(self, namespace: str) -> datetime | None:
        """Return the newest archived end on the UTC timeline."""

        with self._lock:
            row = self._db.execute(
                "SELECT MAX(end_utc) latest FROM quarters WHERE namespace=?",
                (namespace,),
            ).fetchone()
        value = row["latest"]
        return None if value is None else datetime.fromisoformat(str(value)).astimezone(UTC)

    def summarize(
        self,
        namespace: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        include_simulation: bool = False,
    ) -> ArchiveSummary:
        """Aggregate without averaging away maximum quarter demand."""

        simulation_clause = "" if include_simulation else "AND simulation=0"
        with self._lock:
            row = self._db.execute(
                f"""SELECT
                    SUM(CASE WHEN quality IN ('measured_aligned','counter_derived',
                        'reconstructed') THEN 1 ELSE 0 END) valid_count,
                    SUM(CASE WHEN quality IN ('incomplete','unavailable') THEN 1 ELSE 0 END)
                        incomplete_count,
                    SUM(CASE WHEN exceeded=1 AND simulation=0 THEN 1 ELSE 0 END)
                        exceeded_count,
                    COALESCE(SUM(import_kwh),0) import_kwh,
                    COALESCE(SUM(export_kwh),0) export_kwh,
                    MAX(import_demand_kw) maximum_import_demand_kw,
                    AVG(import_demand_kw) average_import_demand_kw,
                    MIN(signed_average_kw) minimum_signed_average_kw,
                    MAX(signed_average_kw) maximum_signed_average_kw
                   FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                   {simulation_clause}""",
                (namespace, _utc_iso(start_utc), _utc_iso(end_utc)),
            ).fetchone()
        return ArchiveSummary(
            valid_count=int(row["valid_count"] or 0),
            incomplete_count=int(row["incomplete_count"] or 0),
            exceeded_count=int(row["exceeded_count"] or 0),
            import_kwh=float(row["import_kwh"]),
            export_kwh=float(row["export_kwh"]),
            maximum_import_demand_kw=_optional_float(row["maximum_import_demand_kw"]),
            average_import_demand_kw=_optional_float(row["average_import_demand_kw"]),
            minimum_signed_average_kw=_optional_float(row["minimum_signed_average_kw"]),
            maximum_signed_average_kw=_optional_float(row["maximum_signed_average_kw"]),
        )

    def _migrate(self) -> None:
        version = self.schema_version
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"archive schema {version} is newer than supported")
        if version == 0:
            with self._db:
                self._db.executescript(
                    """
                    CREATE TABLE source_epochs(
                      namespace TEXT NOT NULL, epoch INTEGER NOT NULL,
                      source_id TEXT NOT NULL, positive_means_import INTEGER NOT NULL,
                      effective_utc TEXT NOT NULL,
                      PRIMARY KEY(namespace,epoch));
                    CREATE TABLE quarters(
                      namespace TEXT NOT NULL,start_utc TEXT NOT NULL,end_utc TEXT NOT NULL,
                      start_local TEXT NOT NULL,utc_offset_seconds INTEGER NOT NULL,
                      fold INTEGER NOT NULL,import_kwh REAL NOT NULL,export_kwh REAL NOT NULL,
                      signed_average_kw REAL NOT NULL,import_demand_kw REAL NOT NULL,
                      coverage_seconds REAL NOT NULL,gap_seconds REAL NOT NULL,
                      quality TEXT NOT NULL,provenance TEXT NOT NULL,source_id TEXT NOT NULL,
                      source_epoch INTEGER NOT NULL,contractual_target_kw REAL,
                      safety_margin_kw REAL NOT NULL,operational_target_kw REAL,
                      utilization_pct REAL,exceeded INTEGER,excess_kw REAL,
                      simulation INTEGER NOT NULL DEFAULT 0,tariff_block INTEGER,
                      tariff_rule_version TEXT,created_utc TEXT NOT NULL,
                      PRIMARY KEY(namespace,start_utc));
                    CREATE INDEX idx_quarters_namespace_end
                      ON quarters(namespace,end_utc);
                    CREATE INDEX idx_quarters_namespace_demand
                      ON quarters(namespace,import_demand_kw DESC);
                    CREATE INDEX idx_quarters_namespace_block
                      ON quarters(namespace,tariff_block,start_utc);
                    CREATE INDEX idx_quarters_namespace_exceeded
                      ON quarters(namespace,exceeded,start_utc);
                    CREATE TABLE checkpoints(
                      namespace TEXT PRIMARY KEY,payload_json TEXT NOT NULL,
                      updated_utc TEXT NOT NULL);
                    PRAGMA user_version=1;
                    """
                )

    @property
    def _db(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("archive is not open")
        return self._connection


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("archive timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)
