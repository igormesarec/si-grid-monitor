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

export function smoothedImportSeries(trace, windowSeconds = 120) {
  if (!trace.length) return [];
  const windowMs = Math.max(1, Number(windowSeconds)) * 1000;
  return trace.map((sample, index) => {
    const end = sampleTime(sample);
    const start = end - windowMs;
    let energyKwMs = 0;
    let coverageMs = 0;
    for (let cursor = 0; cursor <= index; cursor += 1) {
      const segmentStart = Math.max(start, sampleTime(trace[cursor]));
      const segmentEnd = Math.min(
        end,
        cursor < index ? sampleTime(trace[cursor + 1]) : end,
      );
      if (segmentEnd > segmentStart) {
        const duration = segmentEnd - segmentStart;
        energyKwMs += importPower(trace[cursor]) * duration;
        coverageMs += duration;
      }
    }
    return {
      timestamp: sample.timestamp,
      import_kw: coverageMs > 0 ? energyKwMs / coverageMs : importPower(sample),
    };
  });
}

export function livePowerChartModel(trace, targetKw, windowSeconds = 120) {
  const actualImport = trace.map(sample => ({
    timestamp: sample.timestamp,
    kw: importPower(sample),
  }));
  const actualExport = trace.map(sample => {
    const signed = Number(sample.signed_kw);
    return {timestamp: sample.timestamp, kw: signed < 0 ? signed : 0};
  });
  const smoothedImport = smoothedImportSeries(trace, windowSeconds).map(sample => ({
    timestamp: sample.timestamp,
    kw: sample.import_kw,
  }));
  const magnitudes = [Number(targetKw) || 0];
  for (const point of [...actualImport, ...actualExport, ...smoothedImport]) {
    magnitudes.push(Math.abs(point.kw));
  }
  const gridLimitKw = Math.max(1, Math.ceil(Math.max(...magnitudes)));
  const gridValues = Array.from(
    {length: gridLimitKw * 2 + 1},
    (_, index) => index - gridLimitKw,
  );
  return {actualImport, actualExport, smoothedImport, gridLimitKw, gridValues};
}

export function quarterEnergyModel({
  trace,
  quarterStartUtc,
  quarterEndUtc,
  nowUtc,
  importKwh,
  targetKw,
  forecastSmoothedKw,
}) {
  const start = new Date(quarterStartUtc).getTime();
  const end = new Date(quarterEndUtc).getTime();
  const now = Math.min(end, Math.max(start, new Date(nowUtc).getTime()));
  const samples = trace
    .filter(sample => sampleTime(sample) <= now)
    .sort((left, right) => sampleTime(left) - sampleTime(right));
  let reconstructedKwh = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const segmentStart = Math.max(start, sampleTime(samples[index]));
    const segmentEnd = Math.min(
      now,
      index + 1 < samples.length ? sampleTime(samples[index + 1]) : now,
    );
    if (segmentEnd > segmentStart) {
      reconstructedKwh += importPower(samples[index]) * (segmentEnd - segmentStart) / 3600000;
    }
  }
  const usedKwh = Math.max(0, Number(importKwh) || 0);
  const priorKwh = Math.max(0, usedKwh - reconstructedKwh);
  let cumulative = priorKwh;
  const actual = [];
  if (samples.length) actual.push({timestamp: samples[0].timestamp, kwh: cumulative});
  for (let index = 0; index < samples.length; index += 1) {
    const segmentStart = Math.max(start, sampleTime(samples[index]));
    const segmentEnd = Math.min(
      now,
      index + 1 < samples.length ? sampleTime(samples[index + 1]) : now,
    );
    if (segmentEnd > segmentStart) {
      cumulative += importPower(samples[index]) * (segmentEnd - segmentStart) / 3600000;
      actual.push({timestamp: new Date(segmentEnd).toISOString(), kwh: cumulative});
    }
  }
  if (!actual.length) actual.push({timestamp: new Date(now).toISOString(), kwh: usedKwh});
  actual[actual.length - 1].kwh = usedKwh;
  const projectedFinalKwh = forecastSmoothedKw == null
    ? null : Math.max(0, Number(forecastSmoothedKw)) * 0.25;
  return {
    actual,
    projection: projectedFinalKwh == null ? [] : [
      {timestamp: new Date(now).toISOString(), kwh: usedKwh},
      {timestamp: new Date(end).toISOString(), kwh: projectedFinalKwh},
    ],
    usedKwh,
    projectedFinalKwh,
    limitKwh: targetKw == null ? null : Math.max(0, Number(targetKw)) * 0.25,
    priorObservedKwh: priorKwh,
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
