export const BLOCK_COLORS = {
  1: "#8b1e3f",
  2: "#dc5a41",
  3: "#ef9f27",
  4: "#4d9c73",
  5: "#3377b8",
};

export function todayChartModel(quarters, width = 1152, height = 360) {
  const margin = {top: 24, right: 16, bottom: 34, left: 58};
  const innerWidth = width - margin.left - margin.right;
  const halfHeight = (height - margin.top - margin.bottom) / 2;
  const zeroY = margin.top + halfHeight;
  const numeric = [];
  for (const quarter of quarters) {
    const showMeasurement = quarter.measurement_valid || quarter.display_status === "live";
    if (showMeasurement && quarter.import_demand_kw != null) numeric.push(Math.abs(Number(quarter.import_demand_kw)));
    if (showMeasurement && quarter.export_average_kw != null) numeric.push(Math.abs(Number(quarter.export_average_kw)));
    if (quarter.contractual_target_kw != null) numeric.push(Math.abs(Number(quarter.contractual_target_kw)));
    if (quarter.projected_import_demand_kw != null) numeric.push(Math.abs(Number(quarter.projected_import_demand_kw)));
  }
  const domainKw = Math.max(1, ...numeric) * 1.1;
  const valueToY = value => zeroY - (Number(value) / domainKw) * halfHeight;
  const slot = innerWidth / Math.max(quarters.length, 1);
  const barWidth = Math.max(2, slot * 0.68);
  const items = quarters.map((quarter, index) => {
    const centerX = margin.left + slot * (index + 0.5);
    const showMeasurement = quarter.measurement_valid || quarter.display_status === "live";
    const importKw = !showMeasurement || quarter.import_demand_kw == null ? null : Number(quarter.import_demand_kw);
    const exportKw = !showMeasurement || quarter.export_average_kw == null ? null : -Math.abs(Number(quarter.export_average_kw));
    const targetKw = quarter.contractual_target_kw == null ? null : Number(quarter.contractual_target_kw);
    return {
      ...quarter,
      centerX,
      leftX: centerX - barWidth / 2,
      barWidth,
      importKw,
      exportKw,
      targetKw,
      importY: importKw == null ? null : valueToY(importKw),
      importHeight: importKw == null ? 0 : zeroY - valueToY(importKw),
      exportY: zeroY,
      exportHeight: exportKw == null ? 0 : valueToY(exportKw) - zeroY,
      targetY: targetKw == null ? null : valueToY(targetKw),
    };
  });
  const targetSegments = items
    .filter(item => item.targetY != null)
    .map(item => ({
      x1: item.centerX - slot / 2,
      x2: item.centerX + slot / 2,
      y: item.targetY,
      targetKw: item.targetKw,
    }));
  return {width, height, margin, zeroY, domainKw, valueToY, slot, items, targetSegments};
}

export function dayStatusLabel(quarter) {
  const labels = {
    live: "LIVE / IN PROGRESS",
    live_unavailable: "LIVE / UNAVAILABLE",
    upcoming: "UPCOMING",
    missing: "MISSING",
    simulation: "SIMULATION",
    completed: quarter.contractual_eligible ? "CONFIRMED" :
      quarter.contractual_status === "provisional_estimate" ? "PROVISIONAL" : "MEASURED / UNCONFIRMED",
  };
  return labels[quarter.display_status] || String(quarter.quality || "UNKNOWN").toUpperCase();
}

export function quarterNavigation(startUtc, delta, liveStartUtc) {
  const start = new Date(startUtc);
  start.setUTCMinutes(start.getUTCMinutes() + delta * 15);
  return start < new Date(liveStartUtc) ? start.toISOString() : null;
}

export function localQuarterLabel(startUtc) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Ljubljana",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZoneName: "shortOffset",
  }).format(new Date(startUtc));
}

export function ljubljanaTimeLabel(value) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Ljubljana",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZoneName: "shortOffset",
  }).format(new Date(value));
}

export function ljubljanaDate(value = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Ljubljana",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function calendarDateLabel(dateString, locale = "en") {
  const language = String(locale).toLowerCase().startsWith("sl") ? "sl-SI" : "en-GB";
  return new Intl.DateTimeFormat(language, {
    timeZone: "Europe/Ljubljana",
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(`${dateString}T12:00:00Z`));
}

export function selectTimelineHour(timeline, startUtc) {
  if (!timeline) return null;
  const scrollLeft = timeline.scrollLeft;
  let selected = null;
  for (const button of timeline.querySelectorAll("[data-hour]")) {
    const active = button.dataset.hour === startUtc;
    button.classList.toggle("selected", active);
    button.setAttribute("aria-pressed", String(active));
    if (active) selected = button;
  }
  timeline.scrollLeft = scrollLeft;
  return selected;
}

export function captureChartScrollState(root, previous = {}) {
  const positions = {...previous};
  let focused = null;
  if (!root) return {positions, focused};
  for (const element of root.querySelectorAll("[data-chart-scroll]")) {
    const key = element.dataset.chartScroll;
    if (key) positions[key] = element.scrollLeft;
    if (root.activeElement === element) focused = key;
  }
  return {positions, focused};
}

export function restoreChartScrollState(root, positions = {}, focused = null) {
  if (!root) return;
  for (const element of root.querySelectorAll("[data-chart-scroll]")) {
    const key = element.dataset.chartScroll;
    if (key && positions[key] != null) element.scrollLeft = positions[key];
    if (key === focused) element.focus({preventScroll: true});
  }
}

export function chartViewStateForRender(
  root,
  previous = {power: 0, energy: 0},
  {reset = false, previousDataKey = null, nextDataKey = null} = {},
) {
  if (reset || (previousDataKey && nextDataKey && previousDataKey !== nextDataKey)) {
    return {positions: {power: 0, energy: 0}, focused: null};
  }
  return captureChartScrollState(root, previous);
}

export function historyErrorMessage(operation, error) {
  const code = error?.code || "unknown_error";
  const messages = {
    archive_unavailable: "Historical archive is temporarily unavailable.",
    quarter_query_failed: "Could not retrieve the selected quarter.",
    day_query_failed: "Could not load the selected day's measurements.",
    invalid_date: "The selected historical date is invalid.",
    entry_not_found: "The selected SI Grid Monitor meter is no longer available.",
  };
  return messages[code] || (operation === "day"
    ? "Could not load the selected day's measurements."
    : "Could not retrieve the selected quarter.");
}

function sampleTime(sample) {
  return new Date(sample.timestamp).getTime();
}

function importPower(sample) {
  return Math.max(0, Number(sample.signed_kw));
}

const ENERGY_RECONCILIATION_TOLERANCE_KWH = 0.001;

function timeWeightedImportAverage(trace, end, windowMs, staleMs) {
  const start = end - windowMs;
  let energyKwMs = 0;
  let coverageMs = 0;
  for (let cursor = 0; cursor < trace.length; cursor += 1) {
    const sampleStart = sampleTime(trace[cursor]);
    if (sampleStart >= end) break;
    const nextStart = cursor + 1 < trace.length ? sampleTime(trace[cursor + 1]) : end;
    const segmentStart = Math.max(start, sampleStart);
    const segmentEnd = Math.min(end, nextStart, sampleStart + staleMs);
    if (segmentEnd > segmentStart) {
      const duration = segmentEnd - segmentStart;
      energyKwMs += importPower(trace[cursor]) * duration;
      coverageMs += duration;
    }
  }
  return {
    import_kw: coverageMs > 0 ? energyKwMs / coverageMs : null,
    coverage_seconds: coverageMs / 1000,
    complete: windowMs - coverageMs <= 1,
  };
}

export function smoothedImportSeries(
  trace, windowSeconds = 120, staleAfterSeconds = 60, anchorUtc = null,
) {
  if (!trace.length) return [];
  const windowMs = Math.max(1, Number(windowSeconds)) * 1000;
  const staleMs = Math.max(1, Number(staleAfterSeconds)) * 1000;
  const sorted = [...trace].sort((left, right) => sampleTime(left) - sampleTime(right));
  const ends = sorted.map(sample => sampleTime(sample));
  const anchor = anchorUtc ? new Date(anchorUtc).getTime() : NaN;
  if (Number.isFinite(anchor) && anchor >= ends.at(-1) && !ends.includes(anchor)) ends.push(anchor);
  return ends.map(end => ({
    timestamp: new Date(end).toISOString(),
    ...timeWeightedImportAverage(sorted, end, windowMs, staleMs),
  }));
}

function powerSegments(trace, nowUtc, staleAfterSeconds, valueForSample) {
  const now = new Date(nowUtc).getTime();
  const staleMs = Math.max(1, Number(staleAfterSeconds)) * 1000;
  const sorted = [...trace].sort((left, right) => sampleTime(left) - sampleTime(right));
  const segments = [];
  let previousEnd = null;
  for (let index = 0; index < sorted.length; index += 1) {
    const sample = sorted[index];
    const start = sampleTime(sample);
    if (start > now) break;
    const next = index + 1 < sorted.length ? sampleTime(sorted[index + 1]) : now;
    const end = Math.min(now, next, start + staleMs);
    const point = {timestamp: new Date(start).toISOString(), kw: valueForSample(sample)};
    if (previousEnd == null || start - previousEnd > 1) segments.push([point]);
    else segments.at(-1).push(point);
    if (end > start) {
      segments.at(-1).push({timestamp: new Date(end).toISOString(), kw: point.kw});
    }
    previousEnd = end;
  }
  return segments;
}

function splitTimedPoints(points, staleAfterSeconds) {
  const staleMs = Math.max(1, Number(staleAfterSeconds)) * 1000;
  const segments = [];
  for (const point of points) {
    if (!segments.length || sampleTime(point) - sampleTime(segments.at(-1).at(-1)) > staleMs) {
      segments.push([point]);
    } else {
      segments.at(-1).push(point);
    }
  }
  return segments;
}

export function livePowerChartModel({
  trace,
  nowUtc,
  quarterEndUtc,
  contractualTargetKw = null,
  contractualSafetyTargetKw = null,
  operationalTargetKw = null,
  simulationTargetKw = null,
  windowSeconds = 120,
  staleAfterSeconds = 60,
  futureImportPowerKw = null,
  futureAnchorUtc = null,
  forecastQuality = "unavailable",
  forecastReason = null,
}) {
  const actualImportSegments = powerSegments(
    trace, nowUtc, staleAfterSeconds, sample => importPower(sample),
  );
  const actualExportSegments = powerSegments(trace, nowUtc, staleAfterSeconds, sample => {
    const signed = Number(sample.signed_kw);
    return signed < 0 ? signed : 0;
  });
  const smoothedImport = smoothedImportSeries(
    trace, windowSeconds, staleAfterSeconds, nowUtc,
  )
    .filter(sample => sample.complete)
    .map(sample => ({timestamp: sample.timestamp, kw: sample.import_kw}));
  const smoothedImportSegments = splitTimedPoints(smoothedImport, staleAfterSeconds);
  const anchor = futureAnchorUtc ? new Date(futureAnchorUtc).getTime() : NaN;
  const quarterEnd = new Date(quarterEndUtc).getTime();
  const futureForecast = (
    futureImportPowerKw != null
    && forecastQuality !== "unavailable"
    && Number.isFinite(anchor)
    && anchor <= quarterEnd
  ) ? [
      {timestamp: new Date(anchor).toISOString(), kw: Number(futureImportPowerKw)},
      {timestamp: new Date(quarterEnd).toISOString(), kw: Number(futureImportPowerKw)},
    ] : [];
  const smoothedAtAnchor = Number.isFinite(anchor) && smoothedImport.some(
    point => sampleTime(point) === anchor
      && Math.abs(point.kw - Number(futureImportPowerKw)) <= 1e-9,
  );
  const detachedForecastAnchor = futureForecast.length && !smoothedAtAnchor
    ? futureForecast[0] : null;
  const magnitudes = [
    Number(contractualTargetKw) || 0,
    Number(contractualSafetyTargetKw) || 0,
    Number(operationalTargetKw) || 0,
    Number(simulationTargetKw) || 0,
  ];
  for (const point of [
    ...actualImportSegments.flat(),
    ...actualExportSegments.flat(),
    ...smoothedImport,
    ...futureForecast,
  ]) {
    magnitudes.push(Math.abs(point.kw));
  }
  const gridLimitKw = Math.max(1, Math.ceil(Math.max(...magnitudes)));
  const gridValues = Array.from(
    {length: gridLimitKw * 2 + 1},
    (_, index) => index - gridLimitKw,
  );
  return {
    actualImportSegments,
    actualExportSegments,
    smoothedImportSegments,
    futureForecast,
    detachedForecastAnchor,
    forecastQuality,
    forecastReason,
    gridLimitKw,
    gridValues,
  };
}

export function quarterEnergyModel({
  trace,
  quarterStartUtc,
  quarterEndUtc,
  nowUtc,
  importKwh,
  contractualTargetKw,
  contractualSafetyTargetKw,
  operationalTargetKw,
  simulationTargetKw = null,
  simulationEnabled = false,
  forecastSmoothedKw,
  staleAfterSeconds = 60,
}) {
  const start = new Date(quarterStartUtc).getTime();
  const end = new Date(quarterEndUtc).getTime();
  const now = Math.min(end, Math.max(start, new Date(nowUtc).getTime()));
  const samples = trace
    .filter(sample => sampleTime(sample) <= now)
    .sort((left, right) => sampleTime(left) - sampleTime(right));
  const staleMs = Math.max(1, Number(staleAfterSeconds)) * 1000;
  let reconstructedKwh = 0;
  let cursorTime = start;
  let hasGap = false;
  const reconstructed = [{timestamp: new Date(start).toISOString(), kwh: 0}];
  for (let index = 0; index < samples.length; index += 1) {
    const segmentStart = Math.max(start, sampleTime(samples[index]));
    const segmentEnd = Math.min(
      now,
      index + 1 < samples.length ? sampleTime(samples[index + 1]) : now,
      sampleTime(samples[index]) + staleMs,
    );
    if (segmentStart - cursorTime > 1) hasGap = true;
    if (segmentEnd > segmentStart) {
      reconstructedKwh += importPower(samples[index]) * (segmentEnd - segmentStart) / 3600000;
      reconstructed.push({timestamp: new Date(segmentEnd).toISOString(), kwh: reconstructedKwh});
      cursorTime = segmentEnd;
    }
  }
  if (now - cursorTime > 1) hasGap = true;
  const usedKwh = Math.max(0, Number(importKwh) || 0);
  const reconciliationErrorKwh = Math.abs(reconstructedKwh - usedKwh);
  const trajectoryAvailable = !hasGap
    && reconciliationErrorKwh <= ENERGY_RECONCILIATION_TOLERANCE_KWH;
  const actual = trajectoryAvailable
    ? reconstructed.map((point, index) => index === reconstructed.length - 1
      ? {...point, timestamp: new Date(now).toISOString(), kwh: usedKwh}
      : point)
    : [];
  const currentPoint = {timestamp: new Date(now).toISOString(), kwh: usedKwh};
  const trajectoryReason = trajectoryAvailable
    ? null
    : hasGap
      ? "Detailed trajectory unavailable because measurement coverage has gaps."
      : `Detailed trajectory differs from the authoritative total by ${reconciliationErrorKwh.toFixed(4)} kWh.`;
  const projectedFinalKwh = forecastSmoothedKw == null
    ? null : Math.max(0, Number(forecastSmoothedKw)) * 0.25;
  const projectionConsistent = projectedFinalKwh != null
    && projectedFinalKwh + ENERGY_RECONCILIATION_TOLERANCE_KWH >= usedKwh;
  const displayedProjectedFinalKwh = projectionConsistent
    ? Math.max(usedKwh, projectedFinalKwh) : projectedFinalKwh;
  return {
    actual,
    currentPoint,
    projection: !projectionConsistent ? [] : [
      currentPoint,
      {timestamp: new Date(end).toISOString(), kwh: displayedProjectedFinalKwh},
    ],
    usedKwh,
    projectedFinalKwh: projectionConsistent ? displayedProjectedFinalKwh : null,
    diagnosticProjectedFinalKwh: projectedFinalKwh,
    contractualLimitKwh: contractualTargetKw == null
      ? null : Math.max(0, Number(contractualTargetKw)) * 0.25,
    contractualSafetyTargetKwh: contractualSafetyTargetKw == null
      ? null : Math.max(0, Number(contractualSafetyTargetKw)) * 0.25,
    operationalTargetKwh: operationalTargetKw == null
      ? null : Math.max(0, Number(operationalTargetKw)) * 0.25,
    simulationTargetKwh: simulationEnabled && simulationTargetKw != null
      ? Math.max(0, Number(simulationTargetKw)) * 0.25 : null,
    trajectoryAvailable,
    trajectoryReason,
    hasGap,
    reconciliationErrorKwh,
    projectionConsistent,
    projectionReason: forecastSmoothedKw == null
      ? "Smoothed final-demand forecast is unavailable."
      : projectionConsistent
        ? null
        : "Projected final energy is below energy already imported.",
  };
}

export class RequestGate {
  constructor() {
    this.generation = 0;
    this.entryId = null;
  }

  switchEntry(entryId) {
    this.entryId = entryId;
    this.generation += 1;
    return this.token();
  }

  invalidate() {
    this.generation += 1;
    return this.token();
  }

  token() {
    return {entryId: this.entryId, generation: this.generation};
  }

  accepts(token) {
    return token.entryId === this.entryId && token.generation === this.generation;
  }
}
