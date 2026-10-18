"""Permanent, namespaced SQLite quarter archive for SI Grid Monitor."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .engine import EPSILON, LJUBLJANA, CompletedQuarter, DataQuality
from .tariffs.models import TariffClassification

SCHEMA_VERSION = 3
_QUALITY_RANK = {
    DataQuality.UNAVAILABLE.value: 0,
    DataQuality.INCOMPLETE.value: 1,
    DataQuality.RECONSTRUCTED.value: 2,
    DataQuality.COUNTER_DERIVED.value: 3,
    DataQuality.MEASURED_ALIGNED.value: 4,
}


class ConfigurationStatus(StrEnum):
    """How confidently a quarter can be tied to historical configuration."""

    KNOWN = "known"
    TARGET_UNKNOWN = "target_unknown"
    TARGET_MIXED = "target_mixed"
    SOURCE_UNKNOWN = "source_unknown"
    SOURCE_MIXED = "source_mixed"
    LEGACY_UNVERIFIED = "legacy_unverified"


@dataclass(frozen=True, slots=True)
class ConfigurationEpoch:
    """One source/sign/target configuration effective on the UTC timeline."""

    epoch: int
    source_id: str
    positive_means_import: bool
    effective_utc: datetime
    contractual_target_kw: float | None
    safety_margin_kw: float | None
    block_targets_kw: tuple[float | None, ...] = (None, None, None, None, None)


@dataclass(frozen=True, slots=True)
class ConfigurationResolution:
    """Configuration provenance resolved for one complete quarter."""

    status: ConfigurationStatus
    source_id: str | None = None
    positive_means_import: bool | None = None
    source_epoch: int | None = None
    contractual_target_kw: float | None = None
    safety_margin_kw: float | None = None
    block_targets_kw: tuple[float | None, ...] = (None, None, None, None, None)


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
    source_id: str | None
    source_epoch: int | None
    configuration_status: str
    contractual_target_kw: float | None
    safety_margin_kw: float | None
    operational_target_kw: float | None
    utilization_pct: float | None
    exceeded: bool | None
    excess_kw: float | None
    simulation: bool = False
    tariff_block: int | None = None
    tariff_rule_version: str | None = None
    tariff_calendar_year: int | None = None
    tariff_season: str | None = None
    tariff_day_type: str | None = None
    tariff_rule_status: str | None = None
    tariff_source_url: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveSummary:
    """Aggregate that preserves the individual-quarter maximum."""

    valid_count: int
    incomplete_count: int
    exceeded_count: int
    unknown_configuration_count: int
    import_kwh: float
    export_kwh: float
    partial_observed_import_kwh: float
    partial_observed_export_kwh: float
    maximum_import_demand_kw: float | None
    average_import_demand_kw: float | None
    minimum_signed_average_kw: float | None
    maximum_signed_average_kw: float | None


def archive_record_from_quarter(
    *,
    namespace: str,
    quarter: CompletedQuarter,
    configuration: ConfigurationResolution,
    provenance: str,
    tariff: TariffClassification | None = None,
) -> ArchiveRecord:
    """Build a record exclusively from immutable quarter/configuration inputs."""

    source_known = configuration.status in {
        ConfigurationStatus.KNOWN,
        ConfigurationStatus.TARGET_UNKNOWN,
        ConfigurationStatus.TARGET_MIXED,
    }
    tariff_target_known = tariff is None or tariff.block is not None
    target_known = configuration.status == ConfigurationStatus.KNOWN and tariff_target_known
    complete = source_known and quarter.quality not in {
        DataQuality.INCOMPLETE,
        DataQuality.UNAVAILABLE,
    }
    if tariff is None:
        selected_target = configuration.contractual_target_kw
    elif tariff.block is None:
        selected_target = None
    else:
        selected_target = configuration.block_targets_kw[tariff.block - 1]
    target = selected_target if target_known else None
    margin = configuration.safety_margin_kw if target_known else None
    utilization = (
        100.0 * quarter.import_demand_kw / target
        if complete and target is not None and target > 0
        else None
    )
    exceeded = (
        quarter.import_demand_kw > target + EPSILON if complete and target is not None else None
    )
    return ArchiveRecord(
        namespace=namespace,
        start_utc=quarter.start_utc,
        end_utc=quarter.end_utc,
        import_kwh=quarter.import_kwh,
        export_kwh=quarter.export_kwh,
        signed_average_kw=quarter.signed_average_kw,
        import_demand_kw=quarter.import_demand_kw,
        coverage_seconds=quarter.coverage_seconds,
        gap_seconds=quarter.gap_seconds,
        quality=quarter.quality.value,
        provenance=provenance,
        source_id=configuration.source_id if source_known else None,
        source_epoch=configuration.source_epoch,
        configuration_status=configuration.status.value,
        contractual_target_kw=target,
        safety_margin_kw=margin,
        operational_target_kw=(
            max(0.0, target - margin) if target is not None and margin is not None else None
        ),
        utilization_pct=utilization,
        exceeded=exceeded,
        excess_kw=(
            max(0.0, quarter.import_demand_kw - target)
            if exceeded is not None and target is not None
            else None
        ),
        simulation=False,
        tariff_block=tariff.block if tariff is not None else None,
        tariff_rule_version=tariff.rule_version if tariff is not None else None,
        tariff_calendar_year=tariff.calendar_year if tariff is not None else None,
        tariff_season=tariff.season.value if tariff is not None else None,
        tariff_day_type=tariff.day_type.value if tariff is not None else None,
        tariff_rule_status=tariff.rule_status.value if tariff is not None else None,
        tariff_source_url=tariff.source_url if tariff is not None else None,
    )


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
        """Compatibility wrapper for source-only callers."""

        return self.register_configuration_epoch(
            namespace=namespace,
            source_id=source_id,
            positive_means_import=positive_means_import,
            contractual_target_kw=None,
            safety_margin_kw=None,
            effective_utc=effective_utc,
        ).epoch

    def register_configuration_epoch(
        self,
        *,
        namespace: str,
        source_id: str,
        positive_means_import: bool,
        contractual_target_kw: float | None,
        safety_margin_kw: float | None,
        block_targets_kw: tuple[float | None, ...] | None = None,
        effective_utc: datetime,
    ) -> ConfigurationEpoch:
        """Return a stable epoch, creating one whenever semantics change."""

        effective = _utc_iso(effective_utc)
        targets = block_targets_kw or (contractual_target_kw,) * 5
        if len(targets) != 5:
            raise ValueError("five block targets are required")
        with self._lock, self._db:
            row = self._db.execute(
                """SELECT epoch, source_id, positive_means_import, effective_utc,
                          contractual_target_kw, safety_margin_kw,
                          target_b1_kw,target_b2_kw,target_b3_kw,target_b4_kw,target_b5_kw
                   FROM source_epochs WHERE namespace=? ORDER BY epoch DESC LIMIT 1""",
                (namespace,),
            ).fetchone()
            if (
                row
                and row["source_id"] == source_id
                and bool(row["positive_means_import"]) == bool(positive_means_import)
                and _same_optional_float(row["contractual_target_kw"], contractual_target_kw)
                and _same_optional_float(row["safety_margin_kw"], safety_margin_kw)
                and all(
                    _same_optional_float(row[f"target_b{index}_kw"], targets[index - 1])
                    for index in range(1, 6)
                )
            ):
                return _epoch_from_row(row)
            epoch = 1 if row is None else int(row["epoch"]) + 1
            self._db.execute(
                """INSERT INTO source_epochs
                   (namespace, epoch, source_id, positive_means_import, effective_utc,
                    contractual_target_kw, safety_margin_kw,
                    target_b1_kw,target_b2_kw,target_b3_kw,target_b4_kw,target_b5_kw)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    namespace,
                    epoch,
                    source_id,
                    int(positive_means_import),
                    effective,
                    contractual_target_kw,
                    safety_margin_kw,
                    *targets,
                ),
            )
            return ConfigurationEpoch(
                epoch=epoch,
                source_id=source_id,
                positive_means_import=positive_means_import,
                effective_utc=effective_utc.astimezone(UTC),
                contractual_target_kw=contractual_target_kw,
                safety_margin_kw=safety_margin_kw,
                block_targets_kw=targets,
            )

    def list_configuration_epochs(self, namespace: str) -> list[ConfigurationEpoch]:
        """Return all known configuration epochs in effective-time order."""

        with self._lock:
            rows = self._db.execute(
                """SELECT epoch, source_id, positive_means_import, effective_utc,
                          contractual_target_kw, safety_margin_kw,
                          target_b1_kw,target_b2_kw,target_b3_kw,target_b4_kw,target_b5_kw
                   FROM source_epochs WHERE namespace=? ORDER BY effective_utc, epoch""",
                (namespace,),
            ).fetchall()
        return [_epoch_from_row(row) for row in rows]

    def resolve_configuration(
        self, namespace: str, start_utc: datetime, end_utc: datetime
    ) -> ConfigurationResolution:
        """Resolve configuration only when its applicability is auditable."""

        start = start_utc.astimezone(UTC)
        end = end_utc.astimezone(UTC)
        epochs = self.list_configuration_epochs(namespace)
        active = [epoch for epoch in epochs if epoch.effective_utc <= start]
        if not active:
            return ConfigurationResolution(ConfigurationStatus.SOURCE_UNKNOWN)
        first = active[-1]
        changes = [epoch for epoch in epochs if start < epoch.effective_utc < end]
        if changes:
            candidates = [first, *changes]
            same_source = all(
                epoch.source_id == first.source_id
                and epoch.positive_means_import == first.positive_means_import
                for epoch in candidates
            )
            return ConfigurationResolution(
                ConfigurationStatus.TARGET_MIXED
                if same_source
                else ConfigurationStatus.SOURCE_MIXED,
                source_id=first.source_id if same_source else None,
                positive_means_import=(first.positive_means_import if same_source else None),
            )
        if first.contractual_target_kw is None or first.safety_margin_kw is None:
            status = ConfigurationStatus.TARGET_UNKNOWN
        else:
            status = ConfigurationStatus.KNOWN
        return ConfigurationResolution(
            status=status,
            source_id=first.source_id,
            positive_means_import=first.positive_means_import,
            source_epoch=first.epoch,
            contractual_target_kw=first.contractual_target_kw,
            safety_margin_kw=first.safety_margin_kw,
            block_targets_kw=first.block_targets_kw,
        )

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
                record.configuration_status,
                record.contractual_target_kw,
                record.safety_margin_kw,
                record.operational_target_kw,
                record.utilization_pct,
                None if record.exceeded is None else int(record.exceeded),
                record.excess_kw,
                int(record.simulation),
                record.tariff_block,
                record.tariff_rule_version,
                record.tariff_calendar_year,
                record.tariff_season,
                record.tariff_day_type,
                record.tariff_rule_status,
                record.tariff_source_url,
                _utc_iso(datetime.now(UTC)),
            )
            self._db.execute(
                """INSERT INTO quarters (
                    namespace,start_utc,end_utc,start_local,utc_offset_seconds,fold,
                    import_kwh,export_kwh,signed_average_kw,import_demand_kw,
                    coverage_seconds,gap_seconds,quality,provenance,source_id,
                    source_epoch,configuration_status,contractual_target_kw,safety_margin_kw,
                    operational_target_kw,utilization_pct,exceeded,excess_kw,
                    simulation,tariff_block,tariff_rule_version,tariff_calendar_year,
                    tariff_season,tariff_day_type,tariff_rule_status,tariff_source_url,created_utc)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    configuration_status=excluded.configuration_status,
                    contractual_target_kw=excluded.contractual_target_kw,
                    safety_margin_kw=excluded.safety_margin_kw,
                    operational_target_kw=excluded.operational_target_kw,
                    utilization_pct=excluded.utilization_pct,
                    exceeded=excluded.exceeded,excess_kw=excluded.excess_kw,
                    simulation=excluded.simulation,tariff_block=excluded.tariff_block,
                    tariff_rule_version=excluded.tariff_rule_version,
                    tariff_calendar_year=excluded.tariff_calendar_year,
                    tariff_season=excluded.tariff_season,
                    tariff_day_type=excluded.tariff_day_type,
                    tariff_rule_status=excluded.tariff_rule_status,
                    tariff_source_url=excluded.tariff_source_url""",
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

    def classify_existing_quarters(self, namespace: str, classifier: Any) -> int:
        """Fill missing calendar metadata without rewriting stored measurements/targets."""

        changed = 0
        with self._lock, self._db:
            rows = self._db.execute(
                """SELECT start_utc FROM quarters WHERE namespace=?
                   AND tariff_rule_version IS NULL""",
                (namespace,),
            ).fetchall()
            for row in rows:
                start = datetime.fromisoformat(str(row["start_utc"])).astimezone(UTC)
                tariff = classifier(start)
                self._db.execute(
                    """UPDATE quarters SET tariff_block=?,tariff_rule_version=?,
                       tariff_calendar_year=?,tariff_season=?,tariff_day_type=?,
                       tariff_rule_status=?,tariff_source_url=?
                       WHERE namespace=? AND start_utc=? AND tariff_rule_version IS NULL""",
                    (
                        tariff.block,
                        tariff.rule_version,
                        tariff.calendar_year,
                        tariff.season.value,
                        tariff.day_type.value,
                        tariff.rule_status.value,
                        tariff.source_url,
                        namespace,
                        row["start_utc"],
                    ),
                )
                if tariff.block is None:
                    # A V0.2 row may contain an exceedance against the former
                    # common target.  Once calendar classification is required,
                    # an unverified year cannot support a confirmed contractual
                    # exceedance.  Measurements and the original target remain.
                    self._db.execute(
                        """UPDATE quarters SET exceeded=NULL,excess_kw=NULL
                           WHERE namespace=? AND start_utc=?""",
                        (namespace, row["start_utc"]),
                    )
                changed += 1
        return changed

    def summarize(
        self,
        namespace: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        include_simulation: bool = False,
    ) -> ArchiveSummary:
        """Aggregate valid quarters without promoting partial observations."""

        simulation_clause = "" if include_simulation else "AND simulation=0"
        valid = """quality IN ('measured_aligned','counter_derived','reconstructed')
                   AND configuration_status IN ('known','target_unknown','target_mixed')"""
        with self._lock:
            row = self._db.execute(
                f"""SELECT
                    SUM(CASE WHEN {valid} THEN 1 ELSE 0 END) valid_count,
                    SUM(CASE WHEN quality IN ('incomplete','unavailable') THEN 1 ELSE 0 END)
                        incomplete_count,
                    SUM(CASE WHEN configuration_status NOT IN
                        ('known','target_unknown','target_mixed') THEN 1 ELSE 0 END)
                        unknown_configuration_count,
                    SUM(CASE WHEN {valid} AND configuration_status='known'
                        AND exceeded=1 AND simulation=0 THEN 1 ELSE 0 END)
                        exceeded_count,
                    COALESCE(SUM(CASE WHEN {valid} THEN import_kwh ELSE 0 END),0)
                        import_kwh,
                    COALESCE(SUM(CASE WHEN {valid} THEN export_kwh ELSE 0 END),0)
                        export_kwh,
                    COALESCE(SUM(CASE WHEN NOT ({valid}) THEN import_kwh ELSE 0 END),0)
                        partial_observed_import_kwh,
                    COALESCE(SUM(CASE WHEN NOT ({valid}) THEN export_kwh ELSE 0 END),0)
                        partial_observed_export_kwh,
                    MAX(CASE WHEN {valid} THEN import_demand_kw END)
                        maximum_import_demand_kw,
                    AVG(CASE WHEN {valid} THEN import_demand_kw END)
                        average_import_demand_kw,
                    MIN(CASE WHEN {valid} THEN signed_average_kw END)
                        minimum_signed_average_kw,
                    MAX(CASE WHEN {valid} THEN signed_average_kw END)
                        maximum_signed_average_kw
                   FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                   {simulation_clause}""",
                (namespace, _utc_iso(start_utc), _utc_iso(end_utc)),
            ).fetchone()
        return ArchiveSummary(
            valid_count=int(row["valid_count"] or 0),
            incomplete_count=int(row["incomplete_count"] or 0),
            exceeded_count=int(row["exceeded_count"] or 0),
            unknown_configuration_count=int(row["unknown_configuration_count"] or 0),
            import_kwh=float(row["import_kwh"]),
            export_kwh=float(row["export_kwh"]),
            partial_observed_import_kwh=float(row["partial_observed_import_kwh"]),
            partial_observed_export_kwh=float(row["partial_observed_export_kwh"]),
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
                      effective_utc TEXT NOT NULL,contractual_target_kw REAL,
                      safety_margin_kw REAL,target_b1_kw REAL,target_b2_kw REAL,
                      target_b3_kw REAL,target_b4_kw REAL,target_b5_kw REAL,
                      PRIMARY KEY(namespace,epoch));
                    CREATE TABLE quarters(
                      namespace TEXT NOT NULL,start_utc TEXT NOT NULL,end_utc TEXT NOT NULL,
                      start_local TEXT NOT NULL,utc_offset_seconds INTEGER NOT NULL,
                      fold INTEGER NOT NULL,import_kwh REAL NOT NULL,export_kwh REAL NOT NULL,
                      signed_average_kw REAL NOT NULL,import_demand_kw REAL NOT NULL,
                      coverage_seconds REAL NOT NULL,gap_seconds REAL NOT NULL,
                      quality TEXT NOT NULL,provenance TEXT NOT NULL,source_id TEXT,
                      source_epoch INTEGER,configuration_status TEXT NOT NULL,
                      contractual_target_kw REAL,safety_margin_kw REAL,
                      operational_target_kw REAL,
                      utilization_pct REAL,exceeded INTEGER,excess_kw REAL,
                      simulation INTEGER NOT NULL DEFAULT 0,tariff_block INTEGER,
                      tariff_rule_version TEXT,tariff_calendar_year INTEGER,
                      tariff_season TEXT,tariff_day_type TEXT,tariff_rule_status TEXT,
                      tariff_source_url TEXT,created_utc TEXT NOT NULL,
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
                    PRAGMA user_version=3;
                    """
                )
            return
        if version == 1:
            with self._db:
                self._db.executescript(
                    """
                    ALTER TABLE source_epochs ADD COLUMN contractual_target_kw REAL;
                    ALTER TABLE source_epochs ADD COLUMN safety_margin_kw REAL;
                    ALTER TABLE quarters RENAME TO quarters_v1;
                    CREATE TABLE quarters(
                      namespace TEXT NOT NULL,start_utc TEXT NOT NULL,end_utc TEXT NOT NULL,
                      start_local TEXT NOT NULL,utc_offset_seconds INTEGER NOT NULL,
                      fold INTEGER NOT NULL,import_kwh REAL NOT NULL,export_kwh REAL NOT NULL,
                      signed_average_kw REAL NOT NULL,import_demand_kw REAL NOT NULL,
                      coverage_seconds REAL NOT NULL,gap_seconds REAL NOT NULL,
                      quality TEXT NOT NULL,provenance TEXT NOT NULL,source_id TEXT,
                      source_epoch INTEGER,configuration_status TEXT NOT NULL,
                      contractual_target_kw REAL,safety_margin_kw REAL,
                      operational_target_kw REAL,utilization_pct REAL,exceeded INTEGER,
                      excess_kw REAL,simulation INTEGER NOT NULL DEFAULT 0,
                      tariff_block INTEGER,tariff_rule_version TEXT,created_utc TEXT NOT NULL,
                      PRIMARY KEY(namespace,start_utc));
                    INSERT INTO quarters(
                      namespace,start_utc,end_utc,start_local,utc_offset_seconds,fold,
                      import_kwh,export_kwh,signed_average_kw,import_demand_kw,
                      coverage_seconds,gap_seconds,quality,provenance,source_id,
                      source_epoch,configuration_status,contractual_target_kw,
                      safety_margin_kw,operational_target_kw,utilization_pct,exceeded,
                      excess_kw,simulation,tariff_block,tariff_rule_version,created_utc)
                    SELECT namespace,start_utc,end_utc,start_local,utc_offset_seconds,fold,
                      import_kwh,export_kwh,signed_average_kw,import_demand_kw,
                      coverage_seconds,gap_seconds,quality,provenance,source_id,
                      source_epoch,'legacy_unverified',contractual_target_kw,
                      safety_margin_kw,operational_target_kw,utilization_pct,exceeded,
                      excess_kw,simulation,tariff_block,tariff_rule_version,created_utc
                    FROM quarters_v1;
                    DROP TABLE quarters_v1;
                    CREATE INDEX idx_quarters_namespace_end
                      ON quarters(namespace,end_utc);
                    CREATE INDEX idx_quarters_namespace_demand
                      ON quarters(namespace,import_demand_kw DESC);
                    CREATE INDEX idx_quarters_namespace_block
                      ON quarters(namespace,tariff_block,start_utc);
                    CREATE INDEX idx_quarters_namespace_exceeded
                      ON quarters(namespace,exceeded,start_utc);
                    PRAGMA user_version=2;
                    """
                )
            version = 2
        if version == 2:
            with self._db:
                self._db.executescript(
                    """
                    ALTER TABLE source_epochs ADD COLUMN target_b1_kw REAL;
                    ALTER TABLE source_epochs ADD COLUMN target_b2_kw REAL;
                    ALTER TABLE source_epochs ADD COLUMN target_b3_kw REAL;
                    ALTER TABLE source_epochs ADD COLUMN target_b4_kw REAL;
                    ALTER TABLE source_epochs ADD COLUMN target_b5_kw REAL;
                    UPDATE source_epochs SET
                      target_b1_kw=contractual_target_kw,target_b2_kw=contractual_target_kw,
                      target_b3_kw=contractual_target_kw,target_b4_kw=contractual_target_kw,
                      target_b5_kw=contractual_target_kw;
                    ALTER TABLE quarters ADD COLUMN tariff_calendar_year INTEGER;
                    ALTER TABLE quarters ADD COLUMN tariff_season TEXT;
                    ALTER TABLE quarters ADD COLUMN tariff_day_type TEXT;
                    ALTER TABLE quarters ADD COLUMN tariff_rule_status TEXT;
                    ALTER TABLE quarters ADD COLUMN tariff_source_url TEXT;
                    PRAGMA user_version=3;
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


def _same_optional_float(value: object, expected: float | None) -> bool:
    return (value is None and expected is None) or (
        value is not None and expected is not None and float(value) == expected
    )


def _epoch_from_row(row: sqlite3.Row) -> ConfigurationEpoch:
    return ConfigurationEpoch(
        epoch=int(row["epoch"]),
        source_id=str(row["source_id"]),
        positive_means_import=bool(row["positive_means_import"]),
        effective_utc=datetime.fromisoformat(str(row["effective_utc"])).astimezone(UTC),
        contractual_target_kw=_optional_float(row["contractual_target_kw"]),
        safety_margin_kw=_optional_float(row["safety_margin_kw"]),
        block_targets_kw=tuple(
            _optional_float(row[f"target_b{index}_kw"]) for index in range(1, 6)
        ),
    )
