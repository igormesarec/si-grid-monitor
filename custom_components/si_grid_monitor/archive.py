"""Permanent, namespaced SQLite quarter archive for SI Grid Monitor."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .contracted_power import (
    ContractedPowerPeriod,
    ContractedPowerSchedule,
    contracted_power_schedule_from_json,
)
from .engine import EPSILON, LJUBLJANA, CompletedQuarter, DataQuality
from .tariffs.calendar import SlovenianTariffCalendar
from .tariffs.models import RuleStatus, TariffClassification

SCHEMA_VERSION = 5
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
    allow_provisional_tariff: bool | None = None
    contracted_power_periods: tuple[ContractedPowerPeriod, ...] | None = None


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
    allow_provisional_tariff: bool | None = None
    contracted_power_periods: tuple[ContractedPowerPeriod, ...] | None = None


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
    tariff_policy: str | None = None
    contractual_status: str = "confirmed"
    contractual_status_reason: str | None = None
    confirmed_exceeded: bool | None = None
    target_effective_from: str | None = None
    target_effective_to: str | None = None
    target_provenance: str | None = None
    target_recorded_on: str | None = None


@dataclass(frozen=True, slots=True)
class ArchivedQuarterSnapshot:
    """Latest completed-quarter values restored for entity presentation."""

    start_utc: datetime
    end_utc: datetime
    import_demand_kw: float
    signed_average_kw: float
    quality: str
    provenance: str


@dataclass(frozen=True, slots=True)
class ArchiveSummary:
    """Aggregate that preserves the individual-quarter maximum."""

    valid_count: int
    incomplete_count: int
    exceeded_count: int
    provisional_exceeded_count: int
    unknown_configuration_count: int
    import_kwh: float
    export_kwh: float
    partial_observed_import_kwh: float
    partial_observed_export_kwh: float
    maximum_import_demand_kw: float | None
    average_import_demand_kw: float | None
    minimum_signed_average_kw: float | None
    maximum_signed_average_kw: float | None


@dataclass(frozen=True, slots=True)
class ArchiveRowValidity:
    """Shared archive/dashboard interpretation of one immutable quarter row."""

    included: bool
    measured_valid: bool
    incomplete: bool
    unknown_configuration: bool
    contractual_eligible: bool
    confirmed_exceeded: bool
    provisional_exceeded: bool


_VALID_MEASUREMENT_QUALITIES = {
    DataQuality.MEASURED_ALIGNED.value,
    DataQuality.COUNTER_DERIVED.value,
    DataQuality.RECONSTRUCTED.value,
}
_MEASURABLE_CONFIGURATION_STATUSES = {
    ConfigurationStatus.KNOWN.value,
    ConfigurationStatus.TARGET_UNKNOWN.value,
    ConfigurationStatus.TARGET_MIXED.value,
}


def archive_row_validity(
    row: Mapping[str, Any], *, include_simulation: bool = False
) -> ArchiveRowValidity:
    """Classify a row without changing its original target or tariff provenance."""

    simulation = bool(row["simulation"])
    included = include_simulation or not simulation
    quality = str(row["quality"])
    configuration_status = str(row["configuration_status"])
    measured_valid = (
        included
        and quality in _VALID_MEASUREMENT_QUALITIES
        and configuration_status in _MEASURABLE_CONFIGURATION_STATUSES
    )
    contractual_eligible = (
        measured_valid
        and not simulation
        and configuration_status == ConfigurationStatus.KNOWN.value
        and row["contractual_target_kw"] is not None
        and row["contractual_status"] == "confirmed"
    )
    return ArchiveRowValidity(
        included=included,
        measured_valid=measured_valid,
        incomplete=included
        and quality in {DataQuality.INCOMPLETE.value, DataQuality.UNAVAILABLE.value},
        unknown_configuration=included
        and configuration_status not in _MEASURABLE_CONFIGURATION_STATUSES,
        contractual_eligible=contractual_eligible,
        confirmed_exceeded=contractual_eligible and row["confirmed_exceeded"] == 1,
        provisional_exceeded=(
            measured_valid
            and not simulation
            and row["contractual_status"] == "provisional_estimate"
            and row["exceeded"] == 1
        ),
    )


def summarize_archive_rows(
    rows: list[Mapping[str, Any]], *, include_simulation: bool = False
) -> ArchiveSummary:
    """Aggregate rows using the same auditable validity rules everywhere."""

    classified = [
        (row, archive_row_validity(row, include_simulation=include_simulation)) for row in rows
    ]
    included = [(row, validity) for row, validity in classified if validity.included]
    valid = [row for row, validity in included if validity.measured_valid]
    partial = [row for row, validity in included if not validity.measured_valid]
    demands = [float(row["import_demand_kw"]) for row in valid]
    signed = [float(row["signed_average_kw"]) for row in valid]
    return ArchiveSummary(
        valid_count=len(valid),
        incomplete_count=sum(validity.incomplete for _, validity in included),
        exceeded_count=sum(validity.confirmed_exceeded for _, validity in included),
        provisional_exceeded_count=sum(validity.provisional_exceeded for _, validity in included),
        unknown_configuration_count=sum(validity.unknown_configuration for _, validity in included),
        import_kwh=sum(float(row["import_kwh"]) for row in valid),
        export_kwh=sum(float(row["export_kwh"]) for row in valid),
        partial_observed_import_kwh=sum(float(row["import_kwh"]) for row in partial),
        partial_observed_export_kwh=sum(float(row["export_kwh"]) for row in partial),
        maximum_import_demand_kw=max(demands, default=None),
        average_import_demand_kw=sum(demands) / len(demands) if demands else None,
        minimum_signed_average_kw=min(signed, default=None),
        maximum_signed_average_kw=max(signed, default=None),
    )


def tariff_for_configuration(
    timestamp: datetime, configuration: ConfigurationResolution
) -> TariffClassification:
    """Classify using the immutable policy resolved for the quarter."""

    return SlovenianTariffCalendar(
        allow_provisional=configuration.allow_provisional_tariff is True
    ).classify(timestamp)


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
    complete = source_known and quarter.quality not in {
        DataQuality.INCOMPLETE,
        DataQuality.UNAVAILABLE,
    }
    target_period: ContractedPowerPeriod | None = None
    if tariff is None:
        selected_target = configuration.contractual_target_kw
    elif configuration.contracted_power_periods is not None:
        schedule = ContractedPowerSchedule(configuration.contracted_power_periods)
        target_period = schedule.period_for(tariff.local_datetime.date())
        selected_target = schedule.target_for(tariff)
    elif tariff.block is None:
        selected_target = None
    else:
        selected_target = configuration.block_targets_kw[tariff.block - 1]
    target_known = (
        configuration.status == ConfigurationStatus.KNOWN
        and tariff_target_known
        and selected_target is not None
    )
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
    if (
        tariff is not None
        and configuration.contracted_power_periods is not None
        and target_period is None
    ):
        contractual_status = "target_assignment_unavailable"
        contractual_reason = "no confirmed contracted-power assignment covers the quarter date"
    elif configuration.status != ConfigurationStatus.KNOWN:
        contractual_status = "unknown_configuration"
        contractual_reason = "historical target or source configuration is not auditable"
    elif not complete:
        contractual_status = "incomplete_measurement"
        contractual_reason = "quarter measurement coverage is incomplete"
    elif tariff is None:
        contractual_status = "legacy_unversioned"
        contractual_reason = "no versioned tariff classification was supplied"
    elif tariff.rule_status == RuleStatus.OFFICIAL:
        contractual_status = "confirmed"
        contractual_reason = None
    elif tariff.rule_status == RuleStatus.PROVISIONAL:
        contractual_status = "provisional_estimate"
        contractual_reason = "tariff rule is provisional and not legally confirmed"
    else:
        contractual_status = "unavailable_rule"
        contractual_reason = "no enabled verified tariff rule is available"
    if configuration.status in {
        ConfigurationStatus.TARGET_MIXED,
        ConfigurationStatus.SOURCE_MIXED,
    }:
        tariff_policy = "mixed_within_quarter"
    elif configuration.allow_provisional_tariff is None:
        tariff_policy = "legacy_policy_unknown"
    else:
        tariff_policy = (
            "allow_provisional" if configuration.allow_provisional_tariff else "official_only"
        )
    confirmed_exceeded = (
        exceeded if contractual_status == "confirmed" and exceeded is not None else None
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
        tariff_policy=tariff_policy,
        contractual_status=contractual_status,
        contractual_status_reason=contractual_reason,
        confirmed_exceeded=confirmed_exceeded,
        target_effective_from=(
            target_period.effective_from.isoformat() if target_period is not None else None
        ),
        target_effective_to=(
            target_period.effective_to.isoformat() if target_period is not None else None
        ),
        target_provenance=(target_period.provenance if target_period is not None else None),
        target_recorded_on=(
            target_period.recorded_on.isoformat()
            if target_period is not None and target_period.recorded_on is not None
            else None
        ),
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
        allow_provisional_tariff: bool | None = None,
        contracted_power_schedule: ContractedPowerSchedule | None = None,
        effective_utc: datetime,
    ) -> ConfigurationEpoch:
        """Return a stable epoch, creating one whenever semantics change."""

        effective = _utc_iso(effective_utc)
        targets = block_targets_kw or (contractual_target_kw,) * 5
        if len(targets) != 5:
            raise ValueError("five block targets are required")
        periods_json = (
            None if contracted_power_schedule is None else contracted_power_schedule.to_json()
        )
        with self._lock, self._db:
            row = self._db.execute(
                """SELECT epoch, source_id, positive_means_import, effective_utc,
                          contractual_target_kw, safety_margin_kw,
                          target_b1_kw,target_b2_kw,target_b3_kw,target_b4_kw,target_b5_kw,
                          allow_provisional_tariff,contracted_power_periods_json
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
                and _same_optional_bool(row["allow_provisional_tariff"], allow_provisional_tariff)
                and row["contracted_power_periods_json"] == periods_json
            ):
                return _epoch_from_row(row)
            epoch = 1 if row is None else int(row["epoch"]) + 1
            self._db.execute(
                """INSERT INTO source_epochs
                   (namespace, epoch, source_id, positive_means_import, effective_utc,
                    contractual_target_kw, safety_margin_kw,
                    target_b1_kw,target_b2_kw,target_b3_kw,target_b4_kw,target_b5_kw,
                    allow_provisional_tariff,contracted_power_periods_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    namespace,
                    epoch,
                    source_id,
                    int(positive_means_import),
                    effective,
                    contractual_target_kw,
                    safety_margin_kw,
                    *targets,
                    (None if allow_provisional_tariff is None else int(allow_provisional_tariff)),
                    periods_json,
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
                allow_provisional_tariff=allow_provisional_tariff,
                contracted_power_periods=(
                    None if contracted_power_schedule is None else contracted_power_schedule.periods
                ),
            )

    def list_configuration_epochs(self, namespace: str) -> list[ConfigurationEpoch]:
        """Return all known configuration epochs in effective-time order."""

        with self._lock:
            rows = self._db.execute(
                """SELECT epoch, source_id, positive_means_import, effective_utc,
                          contractual_target_kw, safety_margin_kw,
                          target_b1_kw,target_b2_kw,target_b3_kw,target_b4_kw,target_b5_kw,
                          allow_provisional_tariff,contracted_power_periods_json
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
        schedule = (
            None
            if first.contracted_power_periods is None
            else ContractedPowerSchedule(first.contracted_power_periods)
        )
        period = schedule.period_for(start.astimezone(LJUBLJANA).date()) if schedule else None
        if schedule is not None:
            target_known = first.safety_margin_kw is not None and period is not None
        else:
            target_known = (
                first.contractual_target_kw is not None
                and first.safety_margin_kw is not None
                and all(target is not None for target in first.block_targets_kw)
            )
        if not target_known:
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
            allow_provisional_tariff=first.allow_provisional_tariff,
            contracted_power_periods=first.contracted_power_periods,
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
                record.tariff_policy,
                record.contractual_status,
                record.contractual_status_reason,
                (
                    int(record.exceeded)
                    if record.confirmed_exceeded is None
                    and record.contractual_status == "confirmed"
                    and record.exceeded is not None
                    else (
                        None
                        if record.confirmed_exceeded is None
                        else int(record.confirmed_exceeded)
                    )
                ),
                record.target_effective_from,
                record.target_effective_to,
                record.target_provenance,
                record.target_recorded_on,
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
                    tariff_season,tariff_day_type,tariff_rule_status,tariff_source_url,
                    tariff_policy,contractual_status,contractual_status_reason,
                    confirmed_exceeded,target_effective_from,target_effective_to,
                    target_provenance,target_recorded_on,created_utc)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           ?,?,?,?,?,?,?,?,?)
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
                    tariff_source_url=excluded.tariff_source_url,
                    tariff_policy=excluded.tariff_policy,
                    contractual_status=excluded.contractual_status,
                    contractual_status_reason=excluded.contractual_status_reason,
                    confirmed_exceeded=excluded.confirmed_exceeded,
                    target_effective_from=excluded.target_effective_from,
                    target_effective_to=excluded.target_effective_to,
                    target_provenance=excluded.target_provenance,
                    target_recorded_on=excluded.target_recorded_on""",
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

    def aggregate_period(
        self,
        namespace: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        tariff_block: int | None = None,
    ) -> sqlite3.Row:
        """Aggregate immutable quarters with the shared archive-validity rules.

        This is deliberately SQL-backed so multi-year summaries do not load the
        complete archive into Home Assistant memory. Missing-quarter counts are
        added by the calendar-aware analysis layer because absent rows cannot be
        classified by SQLite alone.
        """

        measured = """simulation=0
            AND quality IN ('measured_aligned','counter_derived','reconstructed')
            AND configuration_status IN ('known','target_unknown','target_mixed')"""
        eligible = f"""({measured}) AND configuration_status='known'
            AND contractual_target_kw IS NOT NULL AND contractual_status='confirmed'"""
        where_block = "" if tariff_block is None else " AND tariff_block=?"
        params: tuple[Any, ...] = (
            namespace,
            _utc_iso(start_utc),
            _utc_iso(end_utc),
            *((tariff_block,) if tariff_block is not None else ()),
        )
        with self._lock:
            return self._db.execute(
                f"""SELECT
                    SUM(CASE WHEN simulation=0 THEN 1 ELSE 0 END) archived_count,
                    SUM(CASE WHEN {measured} THEN 1 ELSE 0 END) valid_count,
                    SUM(CASE WHEN {eligible} THEN 1 ELSE 0 END) contractual_eligible_count,
                    SUM(CASE WHEN simulation=0 AND quality IN ('incomplete','unavailable')
                        THEN 1 ELSE 0 END) incomplete_count,
                    SUM(CASE WHEN simulation=0 AND configuration_status NOT IN
                        ('known','target_unknown','target_mixed') THEN 1 ELSE 0 END)
                        unknown_configuration_count,
                    SUM(CASE WHEN {measured} AND NOT ({eligible}) THEN 1 ELSE 0 END)
                        valid_without_confirmed_target_count,
                    SUM(CASE WHEN {eligible} AND confirmed_exceeded=1 THEN 1 ELSE 0 END)
                        exceeded_count,
                    SUM(CASE WHEN {measured} AND contractual_status='provisional_estimate'
                        AND exceeded=1 THEN 1 ELSE 0 END) provisional_exceeded_count,
                    SUM(CASE WHEN simulation=1 THEN 1 ELSE 0 END) simulation_count,
                    SUM(CASE WHEN {measured} THEN import_kwh ELSE 0 END) import_kwh,
                    SUM(CASE WHEN {measured} THEN export_kwh ELSE 0 END) export_kwh,
                    SUM(CASE WHEN simulation=0 AND NOT ({measured}) THEN import_kwh ELSE 0 END)
                        partial_observed_import_kwh,
                    SUM(CASE WHEN simulation=0 AND NOT ({measured}) THEN export_kwh ELSE 0 END)
                        partial_observed_export_kwh,
                    MAX(CASE WHEN {measured} THEN import_demand_kw END)
                        maximum_import_demand_kw,
                    AVG(CASE WHEN {measured} THEN import_demand_kw END)
                        average_import_demand_kw,
                    MIN(CASE WHEN {measured} THEN signed_average_kw END)
                        minimum_signed_average_kw,
                    MAX(CASE WHEN {measured} THEN signed_average_kw END)
                        maximum_signed_average_kw,
                    MAX(CASE WHEN {eligible} AND confirmed_exceeded=1 THEN excess_kw END)
                        maximum_excess_kw,
                    GROUP_CONCAT(DISTINCT CASE WHEN simulation=0
                        AND contractual_target_kw IS NOT NULL
                        THEN contractual_target_kw END) targets_kw
                  FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                  {where_block}""",
                params,
            ).fetchone()

    def aggregate_period_bins(
        self,
        namespace: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        resolution: str,
        tariff_block: int | None = None,
    ) -> list[sqlite3.Row]:
        """Return bounded chart bins while preserving the true quarter maximum."""

        group_expression = {
            "quarter": "start_utc",
            "hour": ("substr(start_local,1,13) || '|' || utc_offset_seconds || '|' || fold"),
            "day": "substr(start_local,1,10)",
            "month": "substr(start_local,1,7)",
        }.get(resolution)
        if group_expression is None:
            raise ValueError("unsupported archive-bin resolution")
        measured = """simulation=0
            AND quality IN ('measured_aligned','counter_derived','reconstructed')
            AND configuration_status IN ('known','target_unknown','target_mixed')"""
        eligible = f"""({measured}) AND configuration_status='known'
            AND contractual_target_kw IS NOT NULL AND contractual_status='confirmed'"""
        where_block = "" if tariff_block is None else " AND tariff_block=?"
        params: tuple[Any, ...] = (
            namespace,
            _utc_iso(start_utc),
            _utc_iso(end_utc),
            *((tariff_block,) if tariff_block is not None else ()),
        )
        with self._lock:
            return list(
                self._db.execute(
                    f"""SELECT {group_expression} bin_key,MIN(start_utc) start_utc,
                        MAX(end_utc) end_utc,
                        SUM(CASE WHEN simulation=0 THEN 1 ELSE 0 END) archived_count,
                        SUM(CASE WHEN {measured} THEN 1 ELSE 0 END) valid_count,
                        SUM(CASE WHEN {eligible} THEN 1 ELSE 0 END)
                            contractual_eligible_count,
                        SUM(CASE WHEN simulation=0 AND quality IN
                            ('incomplete','unavailable') THEN 1 ELSE 0 END) incomplete_count,
                        SUM(CASE WHEN {measured} THEN import_kwh ELSE 0 END) import_kwh,
                        SUM(CASE WHEN {measured} THEN export_kwh ELSE 0 END) export_kwh,
                        SUM(CASE WHEN simulation=0 AND NOT ({measured})
                            THEN import_kwh ELSE 0 END) partial_observed_import_kwh,
                        SUM(CASE WHEN simulation=0 AND NOT ({measured})
                            THEN export_kwh ELSE 0 END) partial_observed_export_kwh,
                        MAX(CASE WHEN {measured} THEN import_demand_kw END)
                            maximum_import_demand_kw,
                        AVG(CASE WHEN {measured} THEN import_demand_kw END)
                            average_import_demand_kw,
                        MIN(CASE WHEN {measured} THEN signed_average_kw END)
                            minimum_signed_average_kw,
                        MAX(CASE WHEN {measured} THEN signed_average_kw END)
                            maximum_signed_average_kw,
                        SUM(CASE WHEN {eligible} AND confirmed_exceeded=1 THEN 1 ELSE 0 END)
                            exceeded_count,
                        MAX(CASE WHEN {eligible} AND confirmed_exceeded=1 THEN excess_kw END)
                            maximum_excess_kw,
                        GROUP_CONCAT(DISTINCT CASE WHEN simulation=0
                            AND contractual_target_kw IS NOT NULL
                            THEN contractual_target_kw END) targets_kw
                      FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                      {where_block} GROUP BY {group_expression} ORDER BY MIN(start_utc)""",
                    params,
                ).fetchall()
            )

    def highest_demand_quarters(
        self,
        namespace: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        tariff_block: int | None = None,
        limit: int = 10,
    ) -> list[sqlite3.Row]:
        """Return a bounded list of genuine measured quarter peaks."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        where_block = "" if tariff_block is None else " AND tariff_block=?"
        params: tuple[Any, ...] = (
            namespace,
            _utc_iso(start_utc),
            _utc_iso(end_utc),
            *((tariff_block,) if tariff_block is not None else ()),
            limit,
        )
        with self._lock:
            return list(
                self._db.execute(
                    f"""SELECT * FROM quarters WHERE namespace=? AND start_utc>=?
                       AND start_utc<? AND simulation=0
                       AND quality IN ('measured_aligned','counter_derived','reconstructed')
                       AND configuration_status IN ('known','target_unknown','target_mixed')
                       {where_block}
                       ORDER BY import_demand_kw DESC,start_utc DESC LIMIT ?""",
                    params,
                ).fetchall()
            )

    def aggregate_exceedances(
        self,
        namespace: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        tariff_block: int | None = None,
    ) -> dict[str, Any]:
        """Summarize only confirmed, contract-eligible exceeded quarters."""

        where_block = "" if tariff_block is None else " AND tariff_block=?"
        params: tuple[Any, ...] = (
            namespace,
            _utc_iso(start_utc),
            _utc_iso(end_utc),
            *((tariff_block,) if tariff_block is not None else ()),
        )
        eligible = """simulation=0 AND configuration_status='known'
            AND quality IN ('measured_aligned','counter_derived','reconstructed')
            AND contractual_target_kw IS NOT NULL AND contractual_status='confirmed'"""
        with self._lock:
            summary = self._db.execute(
                f"""SELECT COUNT(*) exceedance_count,
                    MAX(import_demand_kw) maximum_import_demand_kw,
                    MAX(excess_kw) maximum_excess_kw,
                    AVG(excess_kw) average_excess_kw,
                    MAX(CASE WHEN contractual_target_kw>0
                        THEN 100.0*excess_kw/contractual_target_kw END)
                        maximum_excess_percentage
                  FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                    AND {eligible} AND confirmed_exceeded=1 {where_block}""",
                params,
            ).fetchone()
            greatest = self._db.execute(
                f"""SELECT start_utc,end_utc,tariff_block,excess_kw
                  FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                    AND {eligible} AND confirmed_exceeded=1 {where_block}
                  ORDER BY excess_kw DESC,start_utc ASC LIMIT 1""",
                params,
            ).fetchone()
            affected = self._db.execute(
                f"""SELECT tariff_block,COUNT(*) count
                  FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                    AND {eligible} AND confirmed_exceeded=1 {where_block}
                  GROUP BY tariff_block ORDER BY count DESC,tariff_block ASC LIMIT 1""",
                params,
            ).fetchone()
        return {
            **{key: summary[key] for key in summary.keys()},  # noqa: SIM118
            "greatest_exceedance": (
                None if greatest is None else {key: greatest[key] for key in greatest.keys()}  # noqa: SIM118
            ),
            "most_affected_block": None if affected is None else affected["tariff_block"],
        }

    def list_exceedances(
        self,
        namespace: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        tariff_block: int | None = None,
        sort_by: str = "date",
        direction: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[sqlite3.Row]]:
        """Return one safely sorted page of confirmed exceeded quarters."""

        sort_columns = {
            "date": "start_utc",
            "demand": "import_demand_kw",
            "excess_kw": "excess_kw",
            "excess_percentage": "(excess_kw/contractual_target_kw)",
        }
        if sort_by not in sort_columns:
            raise ValueError("unsupported exceedance sort field")
        if direction not in {"asc", "desc"}:
            raise ValueError("unsupported exceedance sort direction")
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid exceedance pagination")
        where_block = "" if tariff_block is None else " AND tariff_block=?"
        base_params: tuple[Any, ...] = (
            namespace,
            _utc_iso(start_utc),
            _utc_iso(end_utc),
            *((tariff_block,) if tariff_block is not None else ()),
        )
        eligible = """simulation=0 AND configuration_status='known'
            AND quality IN ('measured_aligned','counter_derived','reconstructed')
            AND contractual_target_kw IS NOT NULL AND contractual_status='confirmed'
            AND confirmed_exceeded=1"""
        with self._lock:
            total = int(
                self._db.execute(
                    f"""SELECT COUNT(*) count FROM quarters WHERE namespace=?
                       AND start_utc>=? AND start_utc<? AND {eligible} {where_block}""",
                    base_params,
                ).fetchone()["count"]
            )
            rows = list(
                self._db.execute(
                    f"""SELECT *,
                       CASE WHEN contractual_target_kw>0
                         THEN 100.0*excess_kw/contractual_target_kw END excess_percentage,
                       MAX(0,excess_kw)*0.25 excess_energy_kwh
                       FROM quarters WHERE namespace=? AND start_utc>=? AND start_utc<?
                       AND {eligible} {where_block}
                       ORDER BY {sort_columns[sort_by]} {direction.upper()},start_utc DESC
                       LIMIT ? OFFSET ?""",
                    (*base_params, limit, offset),
                ).fetchall()
            )
        return total, rows

    def latest_quarter_end(self, namespace: str) -> datetime | None:
        """Return the newest archived end on the UTC timeline."""

        with self._lock:
            row = self._db.execute(
                "SELECT MAX(end_utc) latest FROM quarters WHERE namespace=?",
                (namespace,),
            ).fetchone()
        value = row["latest"]
        return None if value is None else datetime.fromisoformat(str(value)).astimezone(UTC)

    def load_latest_quarter(self, namespace: str) -> ArchivedQuarterSnapshot | None:
        """Restore the latest completed-quarter display values after restart."""

        with self._lock:
            row = self._db.execute(
                """SELECT start_utc,end_utc,import_demand_kw,signed_average_kw,
                          quality,provenance
                   FROM quarters WHERE namespace=? ORDER BY start_utc DESC LIMIT 1""",
                (namespace,),
            ).fetchone()
        if row is None:
            return None
        return ArchivedQuarterSnapshot(
            start_utc=datetime.fromisoformat(str(row["start_utc"])).astimezone(UTC),
            end_utc=datetime.fromisoformat(str(row["end_utc"])).astimezone(UTC),
            import_demand_kw=float(row["import_demand_kw"]),
            signed_average_kw=float(row["signed_average_kw"]),
            quality=str(row["quality"]),
            provenance=str(row["provenance"]),
        )

    def classify_existing_quarters(self, namespace: str, classifier: Any) -> int:
        """Add versioned derived metadata while preserving original result fields."""

        changed = 0
        with self._lock, self._db:
            rows = self._db.execute(
                """SELECT start_utc,configuration_status,quality,exceeded
                   FROM quarters WHERE namespace=?
                   AND tariff_rule_version IS NULL""",
                (namespace,),
            ).fetchall()
            for row in rows:
                start = datetime.fromisoformat(str(row["start_utc"])).astimezone(UTC)
                tariff = classifier(start)
                confirmed = (
                    tariff.rule_status == RuleStatus.OFFICIAL
                    and row["configuration_status"] == ConfigurationStatus.KNOWN.value
                    and row["quality"]
                    not in {DataQuality.INCOMPLETE.value, DataQuality.UNAVAILABLE.value}
                )
                self._db.execute(
                    """UPDATE quarters SET tariff_block=?,tariff_rule_version=?,
                       tariff_calendar_year=?,tariff_season=?,tariff_day_type=?,
                       tariff_rule_status=?,tariff_source_url=?,
                       tariff_policy='legacy_policy_unknown',contractual_status=?,
                       contractual_status_reason=?,confirmed_exceeded=?
                       WHERE namespace=? AND start_utc=? AND tariff_rule_version IS NULL""",
                    (
                        tariff.block,
                        tariff.rule_version,
                        tariff.calendar_year,
                        tariff.season.value,
                        tariff.day_type.value,
                        tariff.rule_status.value,
                        tariff.source_url,
                        "confirmed" if confirmed else "legacy_policy_unknown",
                        (
                            None
                            if confirmed
                            else "original quarter did not record tariff-policy provenance"
                        ),
                        row["exceeded"] if confirmed else None,
                        namespace,
                        row["start_utc"],
                    ),
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

        with self._lock:
            rows = list(
                self._db.execute(
                    """SELECT * FROM quarters WHERE namespace=? AND start_utc>=?
                       AND start_utc<? ORDER BY start_utc""",
                    (namespace, _utc_iso(start_utc), _utc_iso(end_utc)),
                ).fetchall()
            )
        return summarize_archive_rows(rows, include_simulation=include_simulation)

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
                      allow_provisional_tariff INTEGER,
                      contracted_power_periods_json TEXT,
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
                      tariff_source_url TEXT,tariff_policy TEXT,
                      contractual_status TEXT NOT NULL,
                      contractual_status_reason TEXT,confirmed_exceeded INTEGER,
                      target_effective_from TEXT,target_effective_to TEXT,
                      target_provenance TEXT,target_recorded_on TEXT,
                      created_utc TEXT NOT NULL,
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
                    PRAGMA user_version=5;
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
            version = 3
        if version == 3:
            with self._db:
                self._db.executescript(
                    """
                    ALTER TABLE source_epochs ADD COLUMN allow_provisional_tariff INTEGER;
                    ALTER TABLE quarters ADD COLUMN tariff_policy TEXT;
                    ALTER TABLE quarters ADD COLUMN contractual_status TEXT
                      NOT NULL DEFAULT 'legacy_policy_unknown';
                    ALTER TABLE quarters ADD COLUMN contractual_status_reason TEXT;
                    ALTER TABLE quarters ADD COLUMN confirmed_exceeded INTEGER;
                    UPDATE quarters SET contractual_status = CASE
                      WHEN configuration_status='legacy_unverified' THEN 'legacy_unverified'
                      WHEN tariff_rule_status='official'
                        AND quality NOT IN ('incomplete','unavailable')
                        AND configuration_status='known' THEN 'confirmed'
                      WHEN tariff_rule_status='provisional' THEN 'provisional_estimate'
                      WHEN tariff_rule_status IN ('unverified','out_of_range')
                        THEN 'unavailable_rule'
                      ELSE 'legacy_policy_unknown' END;
                    UPDATE quarters SET confirmed_exceeded=exceeded
                      WHERE contractual_status='confirmed';
                    UPDATE quarters SET tariff_policy='legacy_policy_unknown';
                    PRAGMA user_version=4;
                    """
                )
            version = 4
        if version == 4:
            with self._db:
                self._db.executescript(
                    """
                    ALTER TABLE source_epochs
                      ADD COLUMN contracted_power_periods_json TEXT;
                    UPDATE source_epochs SET contracted_power_periods_json='[]';
                    ALTER TABLE quarters ADD COLUMN target_effective_from TEXT;
                    ALTER TABLE quarters ADD COLUMN target_effective_to TEXT;
                    ALTER TABLE quarters ADD COLUMN target_provenance TEXT;
                    ALTER TABLE quarters ADD COLUMN target_recorded_on TEXT;
                    PRAGMA user_version=5;
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


def _same_optional_bool(value: object, expected: bool | None) -> bool:
    return (value is None and expected is None) or (
        value is not None and expected is not None and bool(value) == expected
    )


def _epoch_from_row(row: sqlite3.Row) -> ConfigurationEpoch:
    periods_json = row["contracted_power_periods_json"]
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
        allow_provisional_tariff=(
            None
            if row["allow_provisional_tariff"] is None
            else bool(row["allow_provisional_tariff"])
        ),
        contracted_power_periods=(
            None
            if periods_json is None
            else contracted_power_schedule_from_json(str(periods_json)).periods
        ),
    )
