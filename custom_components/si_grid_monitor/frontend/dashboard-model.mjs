export const BLOCK_COLORS = {
  1: "#8b1e3f",
  2: "#dc5a41",
  3: "#ef9f27",
  4: "#4d9c73",
  5: "#3377b8",
};

export const CHART_SERIES = Object.freeze({
  import: {color: "#dc2626", dash: null},
  export: {color: "#16a34a", dash: null},
  smooth: {color: "#38bdf8", dash: null},
  future: {color: "#0284c7", dash: "7 4"},
  energyActual: {color: "#dc2626", dash: null},
  energyProjection: {color: "#8b5cf6", dash: "7 4"},
  contract: {color: "#f59e0b", dash: "7 4"},
  contractSafety: {color: "#ea580c", dash: "2 3"},
  simulation: {color: "#8b5cf6", dash: "12 4"},
  operational: {color: "#0891b2", dash: "10 3 2 3"},
});

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

function powerSegments(trace, nowUtc, staleAfterSeconds, valueForSample, omitZero = false) {
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
    const value = valueForSample(sample);
    if (omitZero && Math.abs(value) <= 1e-12) {
      previousEnd = null;
      continue;
    }
    const point = {timestamp: new Date(start).toISOString(), kw: value};
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
  }, true);
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
  const values = [0];
  const referenceValues = [
    contractualTargetKw, contractualSafetyTargetKw, operationalTargetKw, simulationTargetKw,
  ].filter(value => value != null).map(Number);
  values.push(...referenceValues);
  for (const point of [
    ...actualImportSegments.flat(),
    ...actualExportSegments.flat(),
    ...smoothedImport,
    ...futureForecast,
  ]) {
    values.push(Number(point.kw));
  }
  const measuredExport = actualExportSegments.flat().some(point => point.kw < 0);
  const rawMin = measuredExport ? Math.min(...values) : 0;
  const rawMax = Math.max(...values, 0);
  const span = Math.max(0.1, rawMax - rawMin);
  const approximateStep = span <= 1 ? 0.2 : span <= 12 ? 1 : span <= 30 ? 2 : 5;
  const domainMinKw = measuredExport
    ? Math.floor((rawMin - Math.max(0.1, Math.abs(rawMin) * 0.1)) / approximateStep) * approximateStep
    : 0;
  const domainMaxKw = Math.max(
    approximateStep,
    Math.ceil((rawMax + Math.max(0.1, rawMax * 0.1)) / approximateStep) * approximateStep,
  );
  const gridValues = [];
  for (let value = domainMinKw; value <= domainMaxKw + approximateStep / 2; value += approximateStep) {
    gridValues.push(Number(value.toFixed(6)));
  }
  return {
    actualImportSegments,
    actualExportSegments,
    smoothedImportSegments,
    futureForecast,
    detachedForecastAnchor,
    forecastQuality,
    forecastReason,
    domainMinKw,
    domainMaxKw,
    gridStepKw: approximateStep,
    hasExport: measuredExport,
    gridValues,
  };
}

function coveredImportSegments(samples, start, now, staleMs) {
  const covered = [];
  for (let index = 0; index < samples.length; index += 1) {
    const sampleStart = Math.max(start, sampleTime(samples[index]));
    const nextStart = index + 1 < samples.length ? sampleTime(samples[index + 1]) : now;
    const segmentEnd = Math.min(now, nextStart, sampleTime(samples[index]) + staleMs);
    if (segmentEnd > sampleStart) {
      covered.push({start: sampleStart, end: segmentEnd, kw: importPower(samples[index])});
    }
  }
  return covered;
}

export function energyAxisScale(values) {
  const maximum = Math.max(0.01, ...values.filter(value => value != null).map(Number));
  const padded = maximum * 1.1;
  const rough = padded / 5;
  const exponent = 10 ** Math.floor(Math.log10(Math.max(rough, 0.001)));
  const normalized = rough / exponent;
  const factor = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const stepKwh = factor * exponent;
  const maxKwh = Math.max(stepKwh, Math.ceil(padded / stepKwh) * stepKwh);
  const ticks = [];
  for (let value = 0; value <= maxKwh + stepKwh / 2; value += stepKwh) {
    ticks.push(Number(value.toFixed(9)));
  }
  return {maxKwh, stepKwh, ticks};
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
  const covered = coveredImportSegments(samples, start, now, staleMs);
  for (const segment of covered) {
    const segmentStart = segment.start;
    const segmentEnd = segment.end;
    if (segmentStart - cursorTime > 1) hasGap = true;
    if (segmentEnd > segmentStart) {
      reconstructedKwh += segment.kw * (segmentEnd - segmentStart) / 3600000;
      reconstructed.push({timestamp: new Date(segmentEnd).toISOString(), kwh: reconstructedKwh});
      cursorTime = segmentEnd;
    }
  }
  if (now - cursorTime > 1) hasGap = true;
  const usedKwh = Math.max(0, Number(importKwh) || 0);
  const reconciliationErrorKwh = Math.abs(reconstructedKwh - usedKwh);
  const trajectoryAvailable = !hasGap
    && reconciliationErrorKwh <= ENERGY_RECONCILIATION_TOLERANCE_KWH;
  let actual = trajectoryAvailable
    ? reconstructed.map((point, index) => index === reconstructed.length - 1
      ? {...point, timestamp: new Date(now).toISOString(), kwh: usedKwh}
      : point)
    : [];
  let trajectoryMode = trajectoryAvailable ? "full" : "point_only";
  if (!trajectoryAvailable && covered.length && Math.abs(covered.at(-1).end - now) <= 1) {
    let suffixStart = covered.length - 1;
    while (suffixStart > 0 && Math.abs(covered[suffixStart - 1].end - covered[suffixStart].start) <= 1) {
      suffixStart -= 1;
    }
    const suffix = covered.slice(suffixStart);
    const suffixEnergyKwh = suffix.reduce(
      (sum, segment) => sum + segment.kw * (segment.end - segment.start) / 3600000, 0,
    );
    const baselineKwh = usedKwh - suffixEnergyKwh;
    if (baselineKwh >= -ENERGY_RECONCILIATION_TOLERANCE_KWH) {
      let cumulative = Math.max(0, baselineKwh);
      actual = [{timestamp: new Date(suffix[0].start).toISOString(), kwh: cumulative}];
      for (const segment of suffix) {
        cumulative += segment.kw * (segment.end - segment.start) / 3600000;
        actual.push({timestamp: new Date(segment.end).toISOString(), kwh: cumulative});
      }
      actual[actual.length - 1] = {timestamp: new Date(now).toISOString(), kwh: usedKwh};
      trajectoryMode = "partial";
    }
  }
  const currentPoint = {timestamp: new Date(now).toISOString(), kwh: usedKwh};
  const trajectoryReason = trajectoryMode === "full"
    ? "Full trajectory: complete coverage reconciles with the authoritative total."
    : trajectoryMode === "partial"
      ? "Partial supported trajectory: the continuous recent segment is anchored backward from the authoritative current total; earlier gaps remain undisclosed."
      : hasGap
        ? "Point only: no continuous supported measurement segment reaches the authoritative current point."
        : `Point only: detailed trajectory differs from the authoritative total by ${reconciliationErrorKwh.toFixed(4)} kWh.`;
  const projectedFinalKwh = forecastSmoothedKw == null
    ? null : Math.max(0, Number(forecastSmoothedKw)) * 0.25;
  const projectionConsistent = projectedFinalKwh != null
    && projectedFinalKwh + ENERGY_RECONCILIATION_TOLERANCE_KWH >= usedKwh;
  const displayedProjectedFinalKwh = projectionConsistent
    ? Math.max(usedKwh, projectedFinalKwh) : projectedFinalKwh;
  return {
    actual,
    actualSegments: actual.length ? [actual] : [],
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
    trajectoryMode,
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

export function defaultTodayQuarter(quarters, selectedDate, todayDate) {
  if (!quarters?.length) return null;
  if (selectedDate === todayDate) {
    return (quarters.find(item => ["live", "live_unavailable"].includes(item.display_status))
      || [...quarters].reverse().find(item => ["completed", "simulation"].includes(item.display_status))
      || quarters[0]).start_utc;
  }
  return ([...quarters].reverse().find(item => ["completed", "simulation", "missing"].includes(item.display_status))
    || quarters[0]).start_utc;
}

export function moveTodayQuarter(quarters, selectedStartUtc, delta) {
  const index = quarters.findIndex(item => item.start_utc === selectedStartUtc);
  if (index < 0) return null;
  const next = index + delta;
  return next >= 0 && next < quarters.length ? quarters[next].start_utc : null;
}

export function todayQuarterAction(quarter) {
  if (!quarter) return "none";
  if (["completed", "simulation"].includes(quarter.display_status)) return "archive";
  if (["live", "live_unavailable"].includes(quarter.display_status)) return "live";
  if (quarter.display_status === "upcoming") return "upcoming";
  return "missing";
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

export function periodRequest(state) {
  const request = {
    period_type: state.periodType,
    anchor: state.periodAnchor || state.selectedDate,
  };
  if (state.periodType === "custom") {
    request.custom_start = state.customStart;
    request.custom_end = state.customEnd;
  }
  if (state.periodBlock != null && state.periodBlock !== "all") {
    request.tariff_block = Number(state.periodBlock);
  }
  return request;
}

export function exceedanceRequest(state) {
  return {
    ...periodRequest(state),
    sort_by: state.exceedanceSort || "date",
    direction: state.exceedanceDirection || "desc",
    page: Number(state.exceedancePage || 1),
    page_size: Number(state.exceedancePageSize || 25),
  };
}

export function blockChartModel(blocks) {
  const rows = [1, 2, 3, 4, 5].map(block => (
    blocks.find(item => Number(item.block) === block) || {
      block, active: false, import_kwh: 0, maximum_import_demand_kw: null,
      average_import_demand_kw: null, exceeded_count: 0,
    }
  ));
  const energyMaximum = Math.max(1, Math.ceil(Math.max(...rows.map(item => Number(item.import_kwh || 0)))));
  const demandMaximum = Math.max(1, Math.ceil(Math.max(...rows.flatMap(item => [
    Number(item.maximum_import_demand_kw || 0), Number(item.average_import_demand_kw || 0),
    ...(item.targets_kw || []).map(Number),
  ]))));
  const exceedanceMaximum = Math.max(1, ...rows.map(item => Number(item.exceeded_count || 0)));
  const ticks = (maximum, integer = false) => {
    const step = maximum <= 10 ? 1 : maximum <= 25 ? 2 : Math.ceil(maximum / 5 / 5) * 5;
    const rounded = Math.ceil(maximum / step) * step;
    return {
      maximum: rounded,
      step,
      ticks: Array.from({length: Math.floor(rounded / step) + 1}, (_, index) => index * step)
        .filter(value => !integer || Number.isInteger(value)),
    };
  };
  return {
    rows,
    energyMaximum: ticks(energyMaximum).maximum,
    demandMaximum: ticks(demandMaximum).maximum,
    exceedanceMaximum,
    energyScale: ticks(energyMaximum),
    demandScale: ticks(demandMaximum),
    exceedanceScale: ticks(Math.ceil(exceedanceMaximum), true),
  };
}

export function historyQuarterChartModel(rows, {preserveOrder = false} = {}) {
  const normalized = rows.map(row => {
    const numericDemand = Number(row.import_demand_kw);
    const measurementState = row.archive_present === false || row.status === "missing"
      ? "missing"
      : row.measured_valid && Number.isFinite(numericDemand)
        ? numericDemand === 0 ? "valid_zero" : "valid"
        : Number(row.coverage_seconds || 0) > 0 || row.quality === "incomplete"
          ? "partial"
          : "unavailable";
    const demandKw = ["valid", "valid_zero"].includes(measurementState)
      ? numericDemand : null;
    const measuredPeakKw = demandKw != null
      && row.measured_peak_kw != null
      && Number.isFinite(Number(row.measured_peak_kw))
      ? Number(row.measured_peak_kw) : null;
    return {...row, measurementState, demandKw, measuredPeakKw};
  });
  if (!preserveOrder) normalized.sort((left, right) =>
    new Date(right.start_utc).getTime() - new Date(left.start_utc).getTime());
  const values = normalized.flatMap(row => [
    row.demandKw,
    row.measuredPeakKw,
    row.contractual_target_kw,
  ]).filter(value => value != null && Number.isFinite(Number(value))).map(Number);
  const rawMaximum = Math.max(1, ...values);
  const step = rawMaximum <= 10 ? 1 : rawMaximum <= 25 ? 2 : Math.ceil(rawMaximum / 5 / 5) * 5;
  const maximum = Math.ceil(rawMaximum / step) * step;
  return {
    maximum,
    step,
    ticks: Array.from({length: Math.floor(maximum / step) + 1}, (_, index) => index * step),
    rows: normalized.map(row => ({
      ...row,
      demandPct: row.demandKw == null ? null : 100 * row.demandKw / maximum,
      peakPct: row.measuredPeakKw == null ? null : 100 * row.measuredPeakKw / maximum,
      targetPct: row.contractual_target_kw == null ? null : 100 * Number(row.contractual_target_kw) / maximum,
    })),
  };
}

export function adjacentPeriodAnchor(period, direction) {
  if (!period || ![-1, 1].includes(direction)) return null;
  if (period.period_type === "custom") {
    const start = new Date(`${period.start_local.slice(0, 10)}T00:00:00Z`);
    const end = new Date(`${period.end_local.slice(0, 10)}T00:00:00Z`);
    const days = Math.round((end - start) / 86400000);
    start.setUTCDate(start.getUTCDate() + direction * days);
    end.setUTCDate(end.getUTCDate() + direction * days - 1);
    return {
      anchor: start.toISOString().slice(0, 10),
      customStart: start.toISOString().slice(0, 10),
      customEnd: end.toISOString().slice(0, 10),
    };
  }
  const instant = direction < 0
    ? new Date(new Date(period.start_utc).getTime() - 1)
    : new Date(period.end_utc);
  return {anchor: instant.toISOString()};
}

export function periodDrillDown(periodType, bin, resolution = null) {
  if (!bin) return null;
  const actualResolution = resolution || (
    /^\d{4}-\d{2}$/.test(bin.bin_key || "") ? "month" :
      /^\d{4}-\d{2}-\d{2}$/.test(bin.bin_key || "") ? "day" :
        String(bin.bin_key || "").includes("|") ? "hour" : "quarter"
  );
  const canonicalStart = bin.expected_start_utc || bin.start_utc;
  if (actualResolution === "month" && /^\d{4}-\d{2}$/.test(bin.bin_key || "")) {
    return {periodType: "month", anchor: `${bin.bin_key}-01`};
  }
  if (actualResolution === "day" && /^\d{4}-\d{2}-\d{2}$/.test(bin.bin_key || "")) {
    return {periodType: "day", anchor: bin.bin_key};
  }
  if (actualResolution === "hour" && canonicalStart) {
    return {periodType: "hour", anchor: canonicalStart};
  }
  if (actualResolution === "quarter" && canonicalStart) {
    return {quarterStartUtc: canonicalStart};
  }
  return null;
}

export function periodBinDescription(bin) {
  const key = String(bin?.bin_key || "Unknown interval");
  if (bin?.status === "missing" || bin?.status === "unavailable") {
    return `${key}; ${bin.status}; no measured value is available; missing data is not zero`;
  }
  const validCount = Number(bin?.valid_count || 0);
  const expectedCount = Number(bin?.expected_count || 0);
  if (bin?.status === "incomplete" && validCount === 0) {
    return `${key}; incomplete; no valid measured value; partial observations are excluded`;
  }
  const importValue = Number(bin?.import_kwh || 0).toFixed(3);
  const state = bin?.status === "incomplete" ? "incomplete valid coverage" : "measured";
  return `${key}; ${state}; ${importValue} kWh imported; ${validCount} of ${expectedCount} quarters valid`;
}

function niceStep(rawStep, integerOnly = false) {
  if (!Number.isFinite(rawStep) || rawStep <= 0) return 1;
  const exponent = 10 ** Math.floor(Math.log10(rawStep));
  const fraction = rawStep / exponent;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  const step = niceFraction * exponent;
  return integerOnly ? Math.max(1, Math.ceil(step)) : step;
}

export function niceAxisScale(values, kind = "energy") {
  if (kind === "coverage") {
    return {maximum: 100, step: 25, ticks: [0, 25, 50, 75, 100]};
  }
  const finite = values.map(Number).filter(value => Number.isFinite(value) && value >= 0);
  const rawMaximum = Math.max(0, ...finite);
  if (kind === "power" && rawMaximum <= 10) {
    const maximum = Math.max(1, Math.ceil(rawMaximum));
    return {
      maximum,
      step: 1,
      ticks: Array.from({length: maximum + 1}, (_unused, index) => index),
    };
  }
  const integerOnly = kind === "count";
  const step = niceStep((rawMaximum || 1) / 4, integerOnly);
  const maximum = Math.max(step, Math.ceil((rawMaximum || step) / step) * step);
  const ticks = [];
  for (let value = 0; value <= maximum + step / 1000; value += step) {
    ticks.push(Number(value.toPrecision(12)));
  }
  return {maximum, step, ticks};
}

function localParts(instant, options) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Ljubljana",
    ...options,
  }).format(new Date(instant));
}

export function periodAxisLabels(bins, resolution) {
  const labels = bins.map(bin => {
    const instant = bin.expected_start_utc || bin.start_utc;
    if (!instant) return String(bin.bin_key || "");
    if (resolution === "month") {
      return localParts(instant, {month: "short", year: "numeric"});
    }
    if (resolution === "day") {
      return localParts(instant, {day: "2-digit", month: "short"});
    }
    return localParts(instant, {hour: "2-digit", minute: "2-digit", hourCycle: "h23"});
  });
  const duplicates = new Set(labels.filter((label, index) => labels.indexOf(label) !== index));
  return labels.map((label, index) => {
    if (!duplicates.has(label) || !["quarter", "hour"].includes(resolution)) return label;
    const instant = bins[index].expected_start_utc || bins[index].start_utc;
    const offset = localParts(instant, {timeZoneName: "shortOffset"}).split(" ").at(-1);
    return `${label} ${offset}`;
  });
}

export function periodChartModel(bins, mode, width = 1120, height = 330) {
  const margin = {top: 24, right: 24, bottom: 54, left: 68};
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const values = bins.flatMap(bin => {
    const hasMeasuredData = !["missing", "unavailable"].includes(bin.status)
      && (bin.status !== "incomplete" || Number(bin.valid_count || 0) > 0);
    if (!hasMeasuredData) return [];
    if (mode === "energy") return [bin.import_kwh, bin.export_kwh];
    if (mode === "demand") return [
      bin.maximum_import_demand_kw, bin.average_import_demand_kw, ...(bin.targets_kw || []),
    ];
    if (mode === "exceedances") return [bin.exceeded_count];
    return [bin.coverage_pct];
  }).filter(value => Number.isFinite(Number(value))).map(Number);
  const scale = niceAxisScale(
    values,
    mode === "demand" ? "power" : mode === "coverage" ? "coverage" : mode === "exceedances" ? "count" : "energy",
  );
  const maximum = scale.maximum;
  const step = plotWidth / Math.max(1, bins.length);
  const valueToY = value => margin.top + plotHeight * (1 - Math.max(0, Number(value)) / maximum);
  return {
    width, height, margin, maximum, ticks: scale.ticks, tickStep: scale.step, step, valueToY,
    items: bins.map((bin, index) => {
      const hasMeasuredData = !["missing", "unavailable"].includes(bin.status)
        && (bin.status !== "incomplete" || Number(bin.valid_count || 0) > 0);
      return {
        ...bin,
        hasMeasuredData,
        showAverage: mode === "demand" && Number(bin.expected_count || bin.valid_count || 1) > 1,
        centerX: margin.left + step * (index + 0.5),
        barWidth: Math.max(2, step * 0.32),
      };
    }),
  };
}
