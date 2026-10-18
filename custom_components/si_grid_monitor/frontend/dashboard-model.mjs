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
