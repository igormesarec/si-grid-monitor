import {
  BLOCK_COLORS,
  RequestGate,
  calendarDateLabel,
  chartViewStateForRender,
  dayStatusLabel,
  historyErrorMessage,
  ljubljanaDate,
  ljubljanaTimeLabel,
  livePowerChartModel,
  localQuarterLabel,
  quarterEnergyModel,
  quarterNavigation,
  restoreChartScrollState,
  selectTimelineHour,
  todayChartModel,
} from "./dashboard-model.mjs?v=0.4.1";

const fmt = (value, digits = 2) => value == null ? "—" : Number(value).toFixed(digits);
const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
})[character]);
const localDate = value => ljubljanaDate(value);
const localTime = value => ljubljanaTimeLabel(value);

class SIGridMonitorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._tab = "overview";
    this._entryId = null;
    this._entries = [];
    this._selectedDate = localDate();
    this._gate = new RequestGate();
    this._resetEntryState();
  }

  set hass(value) {
    this._hass = value;
    if (!this._loaded) this._load();
  }

  set panel(value) { this._panel = value; }
  set route(value) { this._route = value; }

  connectedCallback() {
    this._render();
    if (!this._timer) this._timer = setInterval(() => this._tick(), 1000);
    if (!this._refresh) this._refresh = setInterval(() => this._refreshVisible(), 10000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    clearInterval(this._refresh);
    this._timer = null;
    this._refresh = null;
    this._gate.invalidate();
  }

  _resetEntryState() {
    this._live = null;
    this._day = null;
    this._dayError = null;
    this._calendar = null;
    this._calendarError = null;
    this._transitions = null;
    this._historical = null;
    this._historicalStart = null;
    this._historicalDate = null;
    this._historicalError = null;
    this._historicalLoading = false;
    this._selectedHourUtc = null;
    this._calendarScrollLeft = 0;
    this._chartScrollPositions = {power: 0, energy: 0};
    this._chartDataKey = null;
    this._resetChartScrollOnRender = true;
    this._error = null;
  }

  async _call(type, extra = {}, entryId = this._entryId) {
    if (!entryId) throw new Error("No SI Grid Monitor meter is selected");
    return this._hass.connection.sendMessagePromise({
      type: `si_grid_monitor/${type}`,
      entry_id: entryId,
      ...extra,
    });
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const result = await this._hass.connection.sendMessagePromise({
        type: "si_grid_monitor/entries",
      });
      this._entries = result.entries || [];
      const entryId = this._entries.some(item => item.entry_id === this._entryId)
        ? this._entryId : this._entries[0]?.entry_id;
      if (entryId !== this._entryId) {
        this._entryId = entryId;
        this._gate.switchEntry(entryId);
        this._resetEntryState();
      }
      await this._loadTab();
      this._loaded = true;
      this._error = null;
    } catch (error) {
      this._error = error?.message || String(error);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _selectEntry(entryId) {
    if (entryId === this._entryId) return;
    this._entryId = entryId;
    this._gate.switchEntry(entryId);
    this._resetEntryState();
    this._render();
    await this._loadTab();
  }

  async _loadTab() {
    if (!this._entryId) return;
    const token = this._gate.invalidate();
    const entryId = this._entryId;
    try {
      if (this._tab === "overview") {
        const [live, transitions] = await Promise.all([
          this._call("current", {}, entryId),
          this._call("transitions", {}, entryId),
        ]);
        if (!this._gate.accepts(token)) return;
        this._live = live;
        this._transitions = transitions;
      } else if (this._tab === "today") {
        const day = await this._call("day", {date: this._selectedDate}, entryId);
        if (!this._gate.accepts(token)) return;
        this._day = day;
        this._dayError = null;
      } else {
        const calendar = await this._call("calendar", {date: this._selectedDate}, entryId);
        if (!this._gate.accepts(token)) return;
        this._calendar = calendar;
        this._calendarError = null;
      }
      this._error = null;
    } catch (error) {
      if (this._gate.accepts(token)) {
        if (this._tab === "today") {
          this._day = null;
          this._dayError = historyErrorMessage("day", error);
        } else if (this._tab === "calendar") {
          this._calendar = null;
          this._calendarError = error?.message || "Could not load the tariff calendar.";
        } else {
          this._error = error?.message || String(error);
        }
      }
    }
    this._render();
  }

  _refreshVisible() {
    if (!this.isConnected || !this._entryId) return;
    if (this._tab === "overview" ||
        (this._tab === "today" && this._selectedDate === localDate())) {
      this._loadTab();
    }
  }

  async _chooseTab(tab) {
    this._tab = tab;
    this._error = null;
    if (this._historicalDate && this._historicalDate !== this._selectedDate) {
      this._historical = null;
      this._historicalStart = null;
      this._historicalDate = null;
    }
    this._render();
    await this._loadTab();
  }

  async _setDate(value) {
    this._selectedDate = value;
    this._selectedHourUtc = null;
    this._historical = null;
    this._historicalStart = null;
    this._historicalDate = null;
    this._historicalError = null;
    this._historicalLoading = false;
    this._calendarScrollLeft = 0;
    if (this._tab === "today") {
      this._day = null;
      this._dayError = null;
    }
    if (this._tab === "calendar") {
      this._calendar = null;
      this._calendarError = null;
    }
    await this._loadTab();
  }

  async _moveDay(delta) {
    const selected = new Date(`${this._selectedDate}T12:00:00`);
    selected.setDate(selected.getDate() + delta);
    await this._setDate(localDate(selected));
  }

  async _quarter(startUtc) {
    if (!startUtc) return;
    const token = this._gate.invalidate();
    const entryId = this._entryId;
    this._historicalStart = startUtc;
    this._historicalDate = localDate(new Date(startUtc));
    this._historical = null;
    this._historicalError = null;
    this._historicalLoading = true;
    this._render();
    try {
      const historical = await this._call("quarter", {start_utc: startUtc}, entryId);
      if (!this._gate.accepts(token)) return;
      this._historical = historical;
      this._historicalError = null;
      this._error = null;
    } catch (error) {
      if (this._gate.accepts(token)) {
        this._historical = null;
        this._historicalError = historyErrorMessage("quarter", error);
      }
    } finally {
      if (this._gate.accepts(token)) this._historicalLoading = false;
    }
    this._render();
  }

  _tick() {
    const countdown = this.shadowRoot?.querySelector("[data-countdown]");
    if (!countdown || !this._live?.quarter?.end_utc) return;
    const seconds = Math.max(0, Math.floor(
      (new Date(this._live.quarter.end_utc).getTime() - Date.now()) / 1000,
    ));
    countdown.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  _metric(label, value, unit = "", kind = "") {
    return `<div class="metric ${kind}"><span>${esc(label)}</span><strong>${esc(value)}${unit ? ` <small>${unit}</small>` : ""}</strong></div>`;
  }

  _liveChart(live) {
    const trace = live?.trace || [];
    if (!trace.length) return `<div class="empty">No measured samples yet. Missing data is not drawn as zero.</div>`;
    const start = Date.parse(live.quarter.start_utc);
    const end = Date.parse(live.quarter.end_utc);
    const tariff = live.tariff;
    const forecast = live.projection;
    const forecastEnergyConsistent = forecast.forecast_smoothed_kw == null
      || forecast.forecast_smoothed_kw * 0.25 + 0.001 >= live.quarter.import_kwh;
    const model = livePowerChartModel({
      trace,
      nowUtc: live.now_utc,
      quarterEndUtc: live.quarter.end_utc,
      contractualTargetKw: tariff.contractual_target_kw,
      contractualSafetyTargetKw: tariff.safety_margin_kw > 0
        ? tariff.contractual_operational_target_kw : null,
      operationalTargetKw: forecast.operational_target_kw,
      simulationTargetKw: tariff.simulation_enabled ? tariff.simulation_target_kw : null,
      windowSeconds: live.sustained?.smoothing_seconds || 120,
      staleAfterSeconds: live.trace_stale_after_seconds || 60,
      futureImportPowerKw: forecastEnergyConsistent
        ? forecast.smoothed_future_import_kw : null,
      futureAnchorUtc: forecast.smoothed_future_anchor_utc,
      forecastQuality: forecastEnergyConsistent
        ? forecast.smoothed_future_quality : "unavailable",
      forecastReason: forecastEnergyConsistent
        ? forecast.smoothed_future_reason
        : "projected final energy is below energy already imported",
    });
    const maxKw = model.gridLimitKw;
    const x = timestamp => 44 + (Date.parse(timestamp) - start) / (end - start) * 1036;
    const y = value => 120 - Number(value) / maxKw * 92;
    const path = points => points.map(point => `${x(point.timestamp)},${y(point.kw)}`).join(" ");
    const paths = (segments, className) => segments
      .filter(points => points.length > 1)
      .map(points => `<polyline class="${className}" points="${path(points)}"/>`).join("");
    const reference = (value, className) => value == null ? "" :
      `<line class="${className}" x1="44" x2="1080" y1="${y(value)}" y2="${y(value)}"/>`;
    const contractual = reference(tariff.contractual_target_kw, "contractual-target");
    const contractualSafety = tariff.safety_margin_kw > 0
      ? reference(tariff.contractual_operational_target_kw, "contractual-safety-target") : "";
    const simulation = tariff.simulation_enabled
      ? reference(tariff.simulation_target_kw, "simulation-target") : "";
    const showOperational = forecast.operational_target_kw != null && (
      tariff.simulation_enabled
      || tariff.contractual_operational_target_kw == null
      || Math.abs(forecast.operational_target_kw - tariff.contractual_operational_target_kw) > 0.0001
    );
    const operational = showOperational
      ? reference(forecast.operational_target_kw, "operational-target") : "";
    const labelEvery = Math.max(1, Math.ceil(maxKw / 8));
    const grid = model.gridValues.map(value => `<g><line class="power-grid ${value === 0 ? "zero" : ""}" x1="44" x2="1080" y1="${y(value)}" y2="${y(value)}"/>${value % labelEvery === 0 ? `<text x="5" y="${y(value) + 4}">${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value)} kW</text>` : ""}</g>`).join("");
    const future = model.futureForecast.length
      ? `<polyline class="forecast-continuation" points="${path(model.futureForecast)}"/>` : "";
    const detachedAnchor = model.detachedForecastAnchor
      ? `<circle class="forecast-anchor" cx="${x(model.detachedForecastAnchor.timestamp)}" cy="${y(model.detachedForecastAnchor.kw)}" r="6"/>`
      : "";
    const forecastNote = model.futureForecast.length
      ? `Dashed blue uses the backend's ${fmt(forecast.smoothed_future_import_kw)} kW future import-power assumption (${esc(model.forecastQuality)}${model.forecastReason ? `: ${esc(model.forecastReason)}` : ""}). Projected final quarter-average demand: ${fmt(forecast.forecast_smoothed_kw)} kW.`
      : `Forecast continuation unavailable: ${esc(model.forecastReason || "no supported forecast")}`;
    const anchorNote = model.detachedForecastAnchor
      ? " The outlined anchor is a backend forecast value; current-quarter trace coverage does not support connecting it to the solid measured smoothing line."
      : "";
    const legend = [
      ["import", "Actual import"], ["export", "Actual export"],
      ["smooth", "Historical smoothing"], ["future", "Future assumption"],
      ...(tariff.contractual_target_kw == null ? [] : [["contract", `Distributor limit ${fmt(tariff.contractual_target_kw)} kW`]]),
      ...(tariff.safety_margin_kw > 0 && tariff.contractual_operational_target_kw != null ? [["contract-safety", `Contract safety reference ${fmt(tariff.contractual_operational_target_kw)} kW`]] : []),
      ...(tariff.simulation_enabled ? [["simulation", `SIMULATION threshold ${fmt(tariff.simulation_target_kw)} kW`]] : []),
      ...(showOperational ? [["operational", `Engine operational target ${fmt(forecast.operational_target_kw)} kW`]] : []),
    ].map(([kind, label]) => `<span><i class="swatch ${kind}"></i>${esc(label)}</span>`).join("");
    return `<div class="live-chart"><div class="chart-scroll" data-chart-scroll="power" tabindex="0" aria-label="Scrollable live power chart"><svg viewBox="0 0 1120 260" role="img" aria-label="Live import and export power with measured smoothing, future import-power assumption, one-kilowatt support lines, and separate contractual and operational targets">${grid}${contractual}${contractualSafety}${simulation}${operational}${paths(model.actualImportSegments, "import-trace")}${paths(model.actualExportSegments, "export-trace")}${paths(model.smoothedImportSegments, "smoothed-trace")}${future}${detachedAnchor}<text class="axis-title" x="8" y="14">Power (kW)</text><text class="time-label" x="44" y="246">${esc(localTime(live.quarter.start_utc))}</text><text class="time-label" x="1080" y="246" text-anchor="end">${esc(localTime(live.quarter.end_utc))}</text></svg></div><div class="chart-legend">${legend}</div><p class="chart-key">${forecastNote}${anchorNote}</p></div>`;
  }

  _energyChart(live) {
    const quarter = live.quarter;
    const forecast = live.projection;
    const energy = quarterEnergyModel({
      trace: live.trace || [],
      quarterStartUtc: quarter.start_utc,
      quarterEndUtc: quarter.end_utc,
      nowUtc: live.now_utc,
      importKwh: quarter.import_kwh,
      contractualTargetKw: live.tariff.contractual_target_kw,
      contractualSafetyTargetKw: live.tariff.safety_margin_kw > 0
        ? live.tariff.contractual_operational_target_kw : null,
      operationalTargetKw: forecast.operational_target_kw,
      simulationTargetKw: live.tariff.simulation_target_kw,
      simulationEnabled: live.tariff.simulation_enabled,
      forecastSmoothedKw: forecast.forecast_smoothed_kw,
      staleAfterSeconds: live.trace_stale_after_seconds || 60,
    });
    const start = Date.parse(quarter.start_utc);
    const end = Date.parse(quarter.end_utc);
    const maxKwh = Math.max(
      0.1,
      energy.usedKwh,
      energy.projectedFinalKwh || 0,
      energy.contractualLimitKwh || 0,
      energy.contractualSafetyTargetKwh || 0,
      energy.operationalTargetKwh || 0,
      energy.simulationTargetKwh || 0,
    ) * 1.12;
    const x = timestamp => 48 + (Date.parse(timestamp) - start) / (end - start) * 1028;
    const y = value => 205 - Number(value) / maxKwh * 170;
    const points = values => values.map(point => `${x(point.timestamp)},${y(point.kwh)}`).join(" ");
    const reference = (value, className) => value == null ? "" :
      `<line class="${className}" x1="48" x2="1076" y1="${y(value)}" y2="${y(value)}"/>`;
    const contractual = reference(
      energy.contractualLimitKwh, "energy-contractual-limit",
    );
    const contractualSafety = reference(
      energy.contractualSafetyTargetKwh, "energy-contractual-safety-target",
    );
    const simulation = reference(
      energy.simulationTargetKwh, "energy-simulation-target",
    );
    const showOperational = energy.operationalTargetKwh != null && (
      live.tariff.simulation_enabled
      || energy.contractualSafetyTargetKwh == null
      || Math.abs(energy.operationalTargetKwh - energy.contractualSafetyTargetKwh) > 0.0001
    );
    const operational = showOperational
      ? reference(energy.operationalTargetKwh, "energy-operational-target") : "";
    const projection = energy.projection.length ? `<polyline class="energy-projection" points="${points(energy.projection)}"/>` : "";
    const actual = energy.actual.length
      ? `<polyline class="energy-actual" points="${points(energy.actual)}"/>` : "";
    const trajectoryNote = energy.trajectoryAvailable
      ? "Solid red is the supported cumulative imported-energy trajectory."
      : esc(energy.trajectoryReason);
    const projectionNote = energy.projection.length
      ? "Dashed purple is an estimate from the authoritative current point, not a measurement."
      : esc(energy.projectionReason);
    const legend = [
      ["energy-actual", "Imported energy"], ["energy-projection", "Projected energy"],
      ...(energy.contractualLimitKwh == null ? [] : [["contract", `Distributor limit ${fmt(energy.contractualLimitKwh)} kWh`]]),
      ...(energy.contractualSafetyTargetKwh == null ? [] : [["contract-safety", `Contract safety reference ${fmt(energy.contractualSafetyTargetKwh)} kWh`]]),
      ...(energy.simulationTargetKwh == null ? [] : [["simulation", `SIMULATION threshold ${fmt(energy.simulationTargetKwh)} kWh`]]),
      ...(showOperational ? [["operational", `Engine operational target ${fmt(energy.operationalTargetKwh)} kWh`]] : []),
    ].map(([kind, label]) => `<span><i class="swatch ${kind}"></i>${esc(label)}</span>`).join("");
    return `<section class="energy-progress"><h3>Quarter energy progress</h3><div class="chart-scroll" data-chart-scroll="energy" tabindex="0" aria-label="Scrollable quarter energy chart"><svg viewBox="0 0 1120 260" role="img" aria-label="Cumulative import-only quarter energy in kilowatt-hours, with gaps left undisguised and separate contractual, safety, simulation, and engine targets">${contractual}${contractualSafety}${simulation}${operational}<line class="energy-zero" x1="48" x2="1076" y1="${y(0)}" y2="${y(0)}"/>${actual}${projection}<circle class="energy-current" cx="${x(energy.currentPoint.timestamp)}" cy="${y(energy.currentPoint.kwh)}" r="5"/><text class="axis-title" x="8" y="14">Energy (kWh)</text><text x="5" y="${y(0) + 4}">0</text><text x="5" y="${y(maxKwh) + 4}">${fmt(maxKwh)}</text><text class="time-label" x="48" y="246">${esc(localTime(quarter.start_utc))}</text><text class="time-label" x="1076" y="246" text-anchor="end">${esc(localTime(quarter.end_utc))}</text></svg></div><div class="chart-legend">${legend}</div><div class="grid">${this._metric("Used so far", fmt(energy.usedKwh), "kWh")}${this._metric("Projected final energy", fmt(energy.projectedFinalKwh), "kWh")}${this._metric("Distributor contractual limit", fmt(energy.contractualLimitKwh), "kWh")}${this._metric("Contract safety reference", fmt(energy.contractualSafetyTargetKwh), "kWh")}${live.tariff.simulation_enabled ? this._metric("SIMULATION threshold", fmt(energy.simulationTargetKwh), "kWh") : ""}${this._metric("Engine operational energy target", fmt(energy.operationalTargetKwh), "kWh")}${this._metric("Remaining operational budget", fmt(forecast.budget_remaining_kwh), "kWh")}</div><p class="chart-key">${trajectoryNote} ${projectionNote} Export contributes zero and never reduces imported energy.</p></section>`;
  }

  _overview() {
    const live = this._live;
    if (!live) return `<section class="card">Loading live meter…</section>`;
    if (!live.available) return `<section class="card"><h2>Waiting for measurements</h2><p>${esc(live.reason)}</p></section>`;
    const quarter = live.quarter;
    const power = live.power;
    const tariff = live.tariff;
    const forecast = live.projection;
    const sustained = live.sustained || {};
    const instantProjectionConsistent = forecast.forecast_instant_kw != null
      && forecast.forecast_instant_kw * 0.25 + 0.001 >= quarter.import_kwh;
    const smoothedProjectionConsistent = forecast.forecast_smoothed_kw != null
      && forecast.forecast_smoothed_kw * 0.25 + 0.001 >= quarter.import_kwh;
    const displayedInstantForecast = instantProjectionConsistent
      ? forecast.forecast_instant_kw : null;
    const displayedSmoothedForecast = smoothedProjectionConsistent
      ? forecast.forecast_smoothed_kw : null;
    const projectionWarning = (
      (forecast.forecast_instant_kw != null && !instantProjectionConsistent)
      || (forecast.forecast_smoothed_kw != null && !smoothedProjectionConsistent)
    )
      ? `<p class="error">Projection unavailable: projected final imported energy is below energy already imported. The diagnostic backend value is retained but not presented as a valid forecast.</p>`
      : "";
    return `<section class="card hero"><div class="herohead"><div><p class="eyebrow">CURRENT FIXED 15-MINUTE INTERVAL</p><h2>${esc(quarter.start_local.slice(0, 10))} · ${esc(quarter.start_local.slice(11, 16))}–${esc(quarter.end_local.slice(11, 16))}</h2><p>B${esc(tariff.block)} · ${fmt(tariff.target_kw)} kW · ${esc(quarter.quality)}</p></div><div class="count" data-countdown>--:--</div></div>
      <div class="direction"><div class="import"><span>IMPORT</span><b>${fmt(power.import_kw)} kW</b></div><div class="export"><span>EXPORT</span><b>${fmt(power.export_kw)} kW</b></div></div>${this._liveChart(live)}${this._energyChart(live)}
      <div class="grid">${this._metric("Signed grid power", fmt(power.signed_kw), "kW")}${this._metric("Imported so far", fmt(quarter.import_kwh), "kWh")}${this._metric("Exported so far", fmt(quarter.export_kwh), "kWh")}${this._metric("Import average", fmt(quarter.import_average_kw), "kW")}${this._metric("Instant projected final quarter average", fmt(displayedInstantForecast), "kW")}${this._metric("Smoothed projected final quarter average", fmt(displayedSmoothedForecast), "kW")}${this._metric("Utilization", fmt(forecast.current_utilization_pct), "%")}${this._metric("Remaining budget", fmt(forecast.budget_remaining_kwh), "kWh")}${this._metric("Allowed remainder", fmt(forecast.allowed_remaining_import_kw), "kW")}${this._metric("CAN ADD THIS QUARTER", fmt(forecast.can_add_kw), "kW", "good")}${this._metric("MUST REDUCE THIS QUARTER", fmt(forecast.must_reduce_kw), "kW", forecast.must_reduce_kw > 0 ? "bad" : "")}${this._metric("SUSTAINED CAN ADD", fmt(sustained.can_add_kw), "kW", "accent")}${this._metric("SUSTAINED MUST REDUCE", fmt(sustained.must_reduce_kw), "kW", sustained.must_reduce_kw > 0 ? "bad" : "")}${this._metric("Forecast quality", sustained.quality || "unavailable")}</div>${projectionWarning}
      <p class="safety">15-minute energy-budget headroom is not physical breaker, phase, grid-connection or inverter capacity.</p></section>
      ${this._transitionCard()}<section class="card"><div class="row"><h2>Quarter archive</h2><button data-prev>Previous quarter</button><button data-next>Next quarter</button><button data-live>Current / live</button></div>${this._historicalCard()}</section>`;
  }

  _transitionCard() {
    const data = this._transitions || {};
    const rows = data.transitions || [];
    const lower = data.next_lower_target;
    const forecastText = !lower ? "" : !lower.inside_sustained_horizon
      ? "This lower limit is outside the sustained forecast horizon and is informational only."
      : lower.forecast_status === "reduction_needed"
        ? `Forecast reduction needed over the ${data.sustained_horizon_minutes}-minute horizon. Limiting quarter: ${esc(data.sustained_limiting_quarter_start_utc || "not identified")}.`
        : lower.forecast_status === "no_reduction_projected"
          ? `No reduction projected over the ${data.sustained_horizon_minutes}-minute horizon; the threshold still becomes lower.`
          : `Forecast unavailable: ${esc(lower.forecast_reason || "missing, stale or insufficient measurements")}.`;
    return `<section class="card"><h2>Next tariff transition</h2><div class="grid">${this._metric("Current block", data.current_block ? `B${data.current_block}` : "Unknown")}${this._metric("Current contracted target", fmt(data.current_target_kw), "kW")}${this._metric("Sustained horizon", data.sustained_horizon_minutes ?? "—", "minutes")}</div><div class="transition-list">${rows.map(row => `<div><b>B${esc(row.from_block)} → B${esc(row.to_block)}</b><span>${esc(row.local_datetime?.replace("T", " ").slice(0, 16))} · ${fmt(row.seconds_until / 60, 0)} min</span><span>${fmt(row.from_target_kw)} → ${fmt(row.to_target_kw)} kW · ${esc(row.direction)} ${row.difference_kw == null ? "" : `(${row.difference_kw >= 0 ? "+" : ""}${fmt(row.difference_kw)} kW)`}</span></div>`).join("") || "No verified transition found"}</div><h3>Next lower contracted-power target</h3><p>${lower ? `B${esc(lower.to_block)} at ${esc(lower.local_datetime?.replace("T", " ").slice(0, 16))}: ${fmt(lower.from_target_kw)} → ${fmt(lower.to_target_kw)} kW. Limit decreases by ${fmt(lower.decrease_kw)} kW.` : "No verified lower target within the bounded lookahead."}</p>${lower ? `<p>${forecastText}</p>` : ""}</section>`;
  }

  _historicalCard() {
    if (this._historicalLoading) return `<p>Loading archived quarter…</p>`;
    if (this._historicalError) return `<div class="error"><strong>Archive request failed</strong><p>${esc(this._historicalError)}</p><button data-retry-quarter>Retry</button></div>`;
    const quarter = this._historical?.quarter;
    if (!quarter) return `<p>${this._historicalStart ? `No archived summary exists for ${esc(localQuarterLabel(this._historicalStart))}. The interval is missing, still live, or outside retained history.` : "Select a completed quarter to inspect its immutable SQLite summary."}</p>`;
    return `<div class="grid">${this._metric("Local interval", localQuarterLabel(quarter.start_utc))}${this._metric("Import demand", fmt(quarter.import_demand_kw), "kW")}${this._metric("Import", fmt(quarter.import_kwh), "kWh")}${this._metric("Export", fmt(quarter.export_kwh), "kWh")}${this._metric("Original target", fmt(quarter.contractual_target_kw), "kW")}${this._metric("Quality", quarter.quality || "unknown")}${this._metric("Rule status", quarter.tariff_rule_status || "unknown")}${this._metric("Exceeded", quarter.confirmed_exceeded == null ? "Unknown" : quarter.confirmed_exceeded ? "Yes" : "No")}</div><div class="empty">Detailed power trace unavailable. The aggregate is shown without fabricated samples.</div>`;
  }

  _todayChart(quarters) {
    const model = todayChartModel(quarters);
    const ticks = [-model.domainKw, -model.domainKw / 2, 0, model.domainKw / 2, model.domainKw];
    const backgrounds = model.items.map(item => `<rect x="${item.centerX - model.slot / 2}" y="${model.margin.top}" width="${model.slot}" height="${model.height - model.margin.top - model.margin.bottom}" fill="${BLOCK_COLORS[item.tariff_block] || "#64748b"}" opacity="0.08"/>`).join("");
    const states = model.items.map(item => {
      const classes = ["quarter-slot", item.display_status, item.quality, item.contractual_status];
      const slotTop = model.margin.top;
      const slotHeight = model.height - model.margin.top - model.margin.bottom;
      const stateRect = ["missing", "upcoming", "live_unavailable"].includes(item.display_status) || !item.measurement_valid && item.display_status !== "live" || item.contractual_status === "provisional_estimate"
        ? `<rect class="state ${esc(classes.join(" "))}" x="${item.centerX - model.slot * 0.32}" y="${slotTop}" width="${model.slot * 0.64}" height="${slotHeight}"/>` : "";
      const importBar = item.importY == null ? "" : `<rect class="import-bar" x="${item.leftX}" y="${item.importY}" width="${item.barWidth}" height="${item.importHeight}"/>`;
      const exportBar = item.exportHeight <= 0 ? "" : `<rect class="export-bar" x="${item.leftX}" y="${item.exportY}" width="${item.barWidth}" height="${item.exportHeight}"/>`;
      const exceeded = item.confirmed_exceeded ? `<rect class="exceeded" x="${item.centerX - model.slot * 0.42}" y="${slotTop}" width="${model.slot * 0.84}" height="${slotHeight}"/>` : "";
      const projection = item.display_status === "live" && item.projected_import_demand_kw != null
        ? `<circle class="projection" cx="${item.centerX}" cy="${model.valueToY(item.projected_import_demand_kw)}" r="4"/>` : "";
      return `<g data-quarter="${esc(item.start_utc)}" data-status="${esc(item.display_status)}" aria-label="${esc(`${localQuarterLabel(item.start_utc)}; ${dayStatusLabel(item)}; import ${fmt(item.importKw)} kW; export ${fmt(item.exportKw)} kW; target ${fmt(item.targetKw)} kW`)}">${stateRect}${importBar}${exportBar}${exceeded}${projection}</g>`;
    }).join("");
    const targets = model.targetSegments.map(segment => `<line class="target-step" x1="${segment.x1}" x2="${segment.x2}" y1="${segment.y}" y2="${segment.y}"/>`).join("");
    const axis = ticks.map(value => `<g><line class="gridline ${value === 0 ? "zero" : ""}" x1="${model.margin.left}" x2="${model.width - model.margin.right}" y1="${model.valueToY(value)}" y2="${model.valueToY(value)}"/><text x="4" y="${model.valueToY(value) + 4}">${value > 0 ? "+" : value < 0 ? "−" : ""}${fmt(Math.abs(value))} kW</text></g>`).join("");
    return `<div class="daychart"><svg viewBox="0 0 ${model.width} ${model.height}" role="img" aria-label="Zero-centered daily power chart in kW. Import demand is above zero, exported average power below zero, and the gold stepped line is contracted power."><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#f59e0b" stroke-width="2"/></pattern></defs>${backgrounds}${axis}${targets}${states}<text class="axis-title" x="4" y="14">Power (kW)</text></svg></div>`;
  }

  _today() {
    if (this._dayError) return `<section class="card error"><h2>Daily history unavailable</h2><p>${esc(this._dayError)}</p><button data-retry-day>Retry</button></section>`;
    const day = this._day;
    if (!day) return `<section class="card">Loading day…</section>`;
    const quarters = day.quarters || [];
    const current = quarters.find(quarter => quarter.display_status === "live");
    const liveCard = current ? `<div class="selected-quarter"><h3>LIVE / IN PROGRESS</h3><div class="grid">${this._metric("Imported so far", fmt(current.import_kwh), "kWh")}${this._metric("Exported so far", fmt(current.export_kwh), "kWh")}${this._metric("Elapsed", fmt(current.elapsed_seconds / 60), "minutes")}${this._metric("Measurement coverage", fmt(current.coverage_seconds), "seconds")}${this._metric("Current import average", fmt(current.import_demand_kw), "kW")}${this._metric("Projected final import demand", fmt(current.projected_import_demand_kw), "kW")}${this._metric("Projected exceedance", current.projected_exceedance == null ? "Unavailable" : current.projected_exceedance ? "Projected" : "No")}${this._metric("Confirmed exceedance", "Not until completion")}</div><p class="safety">The projection is not a completed contractual result and is excluded from confirmed statistics.</p></div>` : "";
    return `<section class="card"><div class="row"><button data-day="-1">‹</button><input data-date type="date" value="${esc(this._selectedDate)}"><button data-day="1">›</button><button data-today>Today</button></div><h2>${esc(this._selectedDate)} · ${day.expected_quarters} aligned quarters</h2>${this._todayChart(quarters)}<div class="chart-key">Red: import-only quarter demand (kW) · Green: average exported power below zero (kW) · Gold: original contracted limit · Dot: live projection · Outline: confirmed exceedance · Hatched: missing/incomplete/provisional</div>${liveCard}${this._historicalStart && this._historicalDate === this._selectedDate ? `<div class="selected-quarter"><h3>Selected 15-minute interval</h3>${this._historicalCard()}</div>` : ""}<div class="grid">${this._metric("Imported energy", fmt(day.summary.import_kwh), "kWh")}${this._metric("Exported energy", fmt(day.summary.export_kwh), "kWh")}${this._metric("Partial observed import", fmt(day.summary.partial_observed_import_kwh), "kWh")}${this._metric("Partial observed export", fmt(day.summary.partial_observed_export_kwh), "kWh")}${this._metric("Maximum valid demand", fmt(day.summary.maximum_import_demand_kw), "kW")}${this._metric("Average valid demand", fmt(day.summary.average_import_demand_kw), "kW")}${this._metric("Valid quarters", day.summary.valid_count)}${this._metric("Contract eligible", day.summary.contractual_eligible_count)}${this._metric("Incomplete", day.summary.incomplete_count)}${this._metric("Missing", day.summary.missing_count)}${this._metric("Upcoming", day.summary.upcoming_count)}${this._metric("Confirmed exceedances", day.summary.exceeded_count)}</div><h3>Five tariff blocks</h3><table><thead><tr><th>Block</th><th>Active</th><th>Hours</th><th>Original targets</th><th>Valid / eligible</th><th>Incomplete / missing</th><th>Max / avg kW</th><th>Import / export kWh</th><th>Confirmed exceeded</th></tr></thead><tbody>${day.blocks.map(block => `<tr><td><span class="chip b${block.block}">B${block.block}</span></td><td>${block.active ? "Yes" : "Not active today"}</td><td>${fmt(block.active_hours)}</td><td>${block.targets_kw.length ? block.targets_kw.map(value => fmt(value)).join(", ") : "Unknown"}</td><td>${block.valid_count} / ${block.contractual_eligible_count}</td><td>${block.incomplete_count} / ${block.missing_count}</td><td>${fmt(block.maximum_import_demand_kw)} / ${fmt(block.average_import_demand_kw)}</td><td>${fmt(block.import_kwh)} / ${fmt(block.export_kwh)}</td><td>${block.confirmed_exceedances} / ${fmt(block.confirmed_exceedance_pct)}%</td></tr>`).join("")}</tbody></table></section>`;
  }

  _calendarView() {
    if (this._calendarError) return `<section class="card error"><h2>Tariff calendar unavailable</h2><p>${esc(this._calendarError)}</p><button data-retry-calendar>Retry</button></section>`;
    const calendar = this._calendar;
    if (!calendar) return `<section class="card">Loading calendar…</section>`;
    const selected = calendar.hours.find(hour => hour.start_utc === this._selectedHourUtc) || calendar.hours[0];
    const locale = this._hass?.language || this._hass?.locale?.language || "en";
    const slovenian = String(locale).toLowerCase().startsWith("sl");
    const classification = {
      working_day: slovenian ? "delovni dan" : "Working day",
      weekend: slovenian ? "konec tedna" : "Weekend",
      public_holiday: slovenian ? "praznik" : "Public holiday",
    }[calendar.day_classification] || calendar.day_classification || "Unknown";
    const season = calendar.season === "higher"
      ? slovenian ? "višja sezona" : "Higher season"
      : calendar.season === "lower"
        ? slovenian ? "nižja sezona" : "Lower season"
        : "Unknown season";
    return `<section class="card"><div class="row"><button data-day="-1">‹</button><input data-date type="date" min="2026-01-01" max="2030-12-31" value="${esc(this._selectedDate)}"><button data-day="1">›</button><button data-today>Today</button></div><h2>Tariff calendar · ${esc(calendarDateLabel(calendar.date, locale))}</h2><p>${esc(classification)} · ${esc(season)}${calendar.holiday_name ? ` · ${esc(calendar.holiday_name)}` : ""}</p><div class="timeline" role="listbox" aria-label="Tariff hours">${calendar.hours.map(hour => `<button type="button" data-hour="${esc(hour.start_utc)}" class="hour b${hour.block || 0} ${selected?.start_utc === hour.start_utc ? "selected" : ""}" aria-pressed="${selected?.start_utc === hour.start_utc}"><b>${esc(hour.local_datetime.slice(11, 16))}</b><span>${hour.block ? `B${hour.block}` : "Unknown"}</span><small>${fmt(hour.target_kw)} kW</small><small>UTC${hour.utc_offset_seconds / 3600 >= 0 ? "+" : ""}${hour.utc_offset_seconds / 3600}${hour.fold ? " · fold 1" : ""}</small></button>`).join("")}</div><div class="legend">${[1, 2, 3, 4, 5].map(block => `<span class="chip b${block}">B${block}</span>`).join("")}</div><div data-calendar-details>${this._calendarDetails(selected)}</div></section>`;
  }

  _calendarDetails(selected) {
    if (!selected) return "";
    return `<div class="selected-quarter"><h3>Selected hour · ${esc(selected.local_datetime?.slice(11, 16))}</h3><div class="grid">${this._metric("Tariff block", selected.block ? `B${selected.block}` : "Unknown")}${this._metric("Contracted target", fmt(selected.target_kw), "kW")}${this._metric("Rule status", selected.rule_status || "Unknown")}${this._metric("Rule version", selected.rule_version || "Unknown")}${this._metric("Season", selected.season || "Unknown")}${this._metric("Day type", selected.day_type || "Unknown")}${this._metric("Holiday", selected.holiday_name || "None")}${this._metric("UTC offset", selected.utc_offset_seconds / 3600, "hours")}${this._metric("DST fold", selected.fold ?? 0)}${this._metric("Start (UTC)", selected.start_utc || "Unknown")}</div></div>`;
  }

  _selectCalendarHour(startUtc, focus = false) {
    const selected = this._calendar?.hours?.find(hour => hour.start_utc === startUtc);
    if (!selected) return;
    this._selectedHourUtc = startUtc;
    const timeline = this.shadowRoot?.querySelector(".timeline");
    const button = selectTimelineHour(timeline, startUtc);
    const details = this.shadowRoot?.querySelector("[data-calendar-details]");
    if (details) details.innerHTML = this._calendarDetails(selected);
    if (focus) button?.focus();
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach(element => {
      element.onclick = () => this._chooseTab(element.dataset.tab);
    });
    root.querySelector("select[data-entry]")?.addEventListener("change", event => {
      this._selectEntry(event.target.value);
    });
    root.querySelectorAll("[data-day]").forEach(element => {
      element.onclick = () => this._moveDay(Number(element.dataset.day));
    });
    root.querySelector("[data-date]")?.addEventListener("change", event => {
      this._setDate(event.target.value);
    });
    root.querySelector("[data-today]")?.addEventListener("click", () => this._setDate(localDate()));
    root.querySelector("[data-prev]")?.addEventListener("click", () => {
      const origin = this._historicalStart || this._live.quarter.start_utc;
      this._quarter(quarterNavigation(origin, -1, this._live.quarter.start_utc));
    });
    root.querySelector("[data-next]")?.addEventListener("click", () => {
      const origin = this._historicalStart || this._live.quarter.start_utc;
      const next = quarterNavigation(origin, 1, this._live.quarter.start_utc);
      if (next) this._quarter(next);
      else {
        this._historical = null;
        this._historicalStart = null;
        this._historicalDate = null;
        this._render();
      }
    });
    root.querySelector("[data-live]")?.addEventListener("click", () => {
      this._historical = null;
      this._historicalStart = null;
      this._historicalDate = null;
      this._historicalError = null;
      this._historicalLoading = false;
      this._render();
    });
    root.querySelector("[data-retry-quarter]")?.addEventListener("click", () => {
      if (this._historicalStart) this._quarter(this._historicalStart);
    });
    root.querySelector("[data-retry-day]")?.addEventListener("click", () => this._loadTab());
    root.querySelector("[data-retry-calendar]")?.addEventListener("click", () => this._loadTab());
    root.querySelectorAll("g[data-quarter]").forEach(element => {
      const quarter = this._day?.quarters?.find(item => item.start_utc === element.dataset.quarter);
      if (quarter?.display_status === "completed" || quarter?.display_status === "simulation") {
        element.onclick = () => this._quarter(element.dataset.quarter);
      }
    });
    root.querySelectorAll("[data-hour]").forEach(element => {
      element.onclick = () => this._selectCalendarHour(element.dataset.hour);
      element.onkeydown = event => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        const hours = this._calendar?.hours || [];
        const index = hours.findIndex(hour => hour.start_utc === element.dataset.hour);
        const next = Math.min(hours.length - 1, Math.max(0, index + (event.key === "ArrowRight" ? 1 : -1)));
        if (hours[next]) this._selectCalendarHour(hours[next].start_utc, true);
      };
    });
    const timeline = root.querySelector(".timeline");
    if (timeline) {
      timeline.scrollLeft = this._calendarScrollLeft || 0;
      timeline.addEventListener("scroll", () => {
        this._calendarScrollLeft = timeline.scrollLeft;
      }, {passive: true});
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    const priorTimelineScroll = this.shadowRoot.querySelector(".timeline")?.scrollLeft;
    if (priorTimelineScroll != null) this._calendarScrollLeft = priorTimelineScroll;
    const nextChartDataKey = this._live?.quarter?.start_utc
      ? `${this._entryId}:${this._live.quarter.start_utc}` : null;
    const chartView = chartViewStateForRender(
      this.shadowRoot,
      this._chartScrollPositions || {power: 0, energy: 0},
      {
        reset: this._resetChartScrollOnRender,
        previousDataKey: this._chartDataKey,
        nextDataKey: nextChartDataKey,
      },
    );
    this._chartScrollPositions = chartView.positions;
    if (nextChartDataKey) this._chartDataKey = nextChartDataKey;
    this._resetChartScrollOnRender = false;
    const active = this._entries.find(entry => entry.entry_id === this._entryId);
    this.shadowRoot.innerHTML = `<style>${this._styles()}</style><main><header><div class="brand"><span>SI</span><div><h1>SI Grid Monitor</h1><p>Import-only contractual demand intelligence</p></div></div><div class="meter"><small>Active meter</small>${this._entries.length > 1 ? `<select data-entry>${this._entries.map(entry => `<option value="${esc(entry.entry_id)}" ${entry.entry_id === this._entryId ? "selected" : ""}>${esc(entry.title)}</option>`).join("")}</select>` : `<strong>${esc(active?.title || "None")}</strong>`}</div></header><nav>${[["overview", "OVERVIEW"], ["today", "TODAY"], ["calendar", "TARIFF CALENDAR"]].map(([id, label]) => `<button data-tab="${id}" class="${this._tab === id ? "active" : ""}">${label}</button>`).join("")}</nav>${this._error ? `<div class="error">Connection error: ${esc(this._error)}. The panel will retry automatically.</div>` : ""}${!this._entries.length ? `<section class="card"><h2>No configured meter</h2><p>Complete the SI Grid Monitor integration setup wizard first.</p></section>` : this._tab === "overview" ? this._overview() : this._tab === "today" ? this._today() : this._calendarView()}</main>`;
    this._bind();
    restoreChartScrollState(
      this.shadowRoot, this._chartScrollPositions, chartView.focused,
    );
    const timeline = this.shadowRoot.querySelector(".timeline");
    if (timeline) timeline.scrollLeft = this._calendarScrollLeft || 0;
    this._tick();
  }

  _styles() {
    return `:host{display:block;min-height:100%;font-family:var(--paper-font-body1_-_font-family,system-ui);background:var(--primary-background-color);color:var(--primary-text-color);--line:var(--divider-color,#d6d9de);--card:var(--card-background-color,#fff)}*{box-sizing:border-box}main{max-width:1450px;margin:auto;padding:18px}header,.row,.herohead,.direction,nav{display:flex;align-items:center;gap:12px}header{justify-content:space-between}.brand{display:flex;align-items:center;gap:12px}.brand>span{display:grid;place-items:center;width:48px;height:48px;border:4px solid #15803d;border-left-color:#e11d48;border-radius:50%;font-weight:800}.brand h1{margin:0;font-size:1.45rem}.brand p,.eyebrow,.meter small{margin:2px 0;color:var(--secondary-text-color);font-size:.78rem}.meter{display:flex;flex-direction:column;align-items:flex-end;gap:3px}nav{margin:18px 0;border-bottom:1px solid var(--line)}button,select,input{font:inherit;color:inherit;background:transparent;border:1px solid var(--line);border-radius:8px;padding:9px 12px;cursor:pointer}nav button{border:0;border-radius:0;font-weight:700}nav .active{border-bottom:3px solid var(--primary-color,#03a9f4);color:var(--primary-color,#03a9f4)}.card{background:var(--card);border-radius:14px;padding:18px;margin:14px 0;box-shadow:var(--ha-card-box-shadow,0 2px 8px #0002)}.herohead{justify-content:space-between}.hero h2{margin:4px 0}.count{font:700 2.2rem ui-monospace}.direction>div{flex:1;padding:14px;border-radius:10px}.import{background:#ef444418;color:#c62828}.export{background:#22c55e18;color:#15803d}.direction b{display:block;font-size:1.7rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px;margin:14px 0}.metric{padding:12px;background:color-mix(in srgb,var(--card),var(--primary-text-color) 5%);border-radius:9px}.metric span{display:block;color:var(--secondary-text-color);font-size:.78rem}.metric strong{font-size:1.2rem}.metric small{font-size:.75rem}.metric.good{border-left:4px solid #16a34a}.metric.bad{border-left:4px solid #dc2626}.metric.accent{border-left:4px solid #0284c7}.notice,.empty,.error,.safety{padding:12px;border-radius:8px;background:#0284c715}.error{background:#f59e0b22}.safety{font-size:.85rem;background:#64748b18}svg{width:100%;height:auto;background:color-mix(in srgb,var(--card),var(--primary-text-color) 3%);border-radius:10px}svg .zero{stroke:var(--primary-text-color);stroke-width:1.8}.contractual-target,.energy-contractual-limit,.target-step{stroke:#f59e0b;stroke-width:2;stroke-dasharray:7 4}.operational-target,.energy-operational-target{stroke:#ea580c;stroke-width:2;stroke-dasharray:2 3}.simulation-target,.energy-simulation-target{stroke:#8b5cf6;stroke-width:2;stroke-dasharray:10 3 2 3}.power-grid{stroke:var(--divider-color,#d6d9de);stroke-width:.7}.import-trace{fill:none;stroke:#dc2626;stroke-width:3}.export-trace{fill:none;stroke:#16a34a;stroke-width:3}.smoothed-trace{fill:none;stroke:#38bdf8;stroke-width:2.5}.forecast-continuation{fill:none;stroke:#0284c7;stroke-width:2.5;stroke-dasharray:7 4}.energy-actual{fill:none;stroke:#dc2626;stroke-width:3}.energy-projection{fill:none;stroke:#8b5cf6;stroke-width:2.5;stroke-dasharray:7 4}.energy-zero{stroke:var(--primary-text-color);stroke-width:1}.energy-current{fill:#dc2626;stroke:var(--card);stroke-width:2}.reference-label{paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round}svg text{fill:var(--secondary-text-color);font-size:12px}.transition-list>div{display:grid;grid-template-columns:1fr 1.4fr 1.2fr;padding:8px;border-bottom:1px solid var(--line)}.daychart{width:100%;overflow-x:auto}.daychart svg{min-width:1000px}.gridline{stroke:var(--divider-color,#d6d9de);stroke-width:1}.import-bar{fill:#e5484d}.export-bar{fill:#2f9e67}.target-step{stroke:#e6a700}.projection{fill:#8b5cf6;stroke:var(--card);stroke-width:1.5}.exceeded{fill:none;stroke:#dc2626;stroke-width:2}.state{fill:transparent;stroke:#94a3b8;stroke-dasharray:3 3}.state.missing,.state.incomplete,.state.unavailable{fill:url(#hatch);stroke:#f59e0b}.state.upcoming{stroke-opacity:.35}.state.provisional_estimate{stroke:#8b5cf6;stroke-width:2}.axis-title{font-weight:700}.quarter-slot{cursor:pointer}.chart-key{font-size:.78rem;color:var(--secondary-text-color);margin:8px 0}.selected-quarter{border:1px solid var(--line);padding:12px;border-radius:10px;margin-top:12px}table{width:100%;border-collapse:collapse;overflow:auto;display:block}th,td{padding:9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}.chip{display:inline-block;padding:4px 8px;border-radius:12px;color:white}.b1{background:${BLOCK_COLORS[1]}}.b2{background:${BLOCK_COLORS[2]}}.b3{background:${BLOCK_COLORS[3]}}.b4{background:${BLOCK_COLORS[4]}}.b5{background:${BLOCK_COLORS[5]}}.b0{background:#64748b}.timeline{display:flex;overflow-x:auto;gap:3px}.hour{min-width:72px;padding:10px 6px;color:white;display:flex;flex-direction:column;border-radius:7px;text-align:left;border:0}.hour.selected{outline:3px solid var(--primary-color,#03a9f4);outline-offset:-3px}.hour small{font-size:.67rem}.legend{display:flex;gap:8px;margin:15px 0}@media(max-width:700px){main{padding:8px}.brand p{display:none}.herohead{align-items:flex-start}.count{font-size:1.6rem}.direction{flex-direction:column}.direction>div{width:100%}.grid{grid-template-columns:repeat(2,1fr)}.transition-list>div{grid-template-columns:1fr}.card{padding:12px}nav{overflow-x:auto}nav button{white-space:nowrap}.meter{max-width:45%}.reference-label{font-size:10px}}.contractual-safety-target,.energy-contractual-safety-target{stroke:#ea580c;stroke-width:2;stroke-dasharray:2 3}.operational-target,.energy-operational-target{stroke:#0891b2;stroke-width:2.4;stroke-dasharray:10 3 2 3}.simulation-target,.energy-simulation-target{stroke:#8b5cf6;stroke-width:2;stroke-dasharray:12 4}.chart-scroll{width:100%;max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain;-webkit-overflow-scrolling:touch}.chart-scroll svg{display:block;width:max(100%,1120px);min-width:1120px}.chart-legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:8px 0;font-size:.78rem;color:var(--secondary-text-color)}.chart-legend span{display:inline-flex;align-items:center;gap:6px}.swatch{display:inline-block;width:24px;height:0;border-top:3px solid}.swatch.import,.swatch.energy-actual{border-color:#dc2626}.swatch.export{border-color:#16a34a}.swatch.smooth{border-color:#38bdf8}.swatch.future,.swatch.energy-projection{border-color:#0284c7;border-top-style:dashed}.swatch.contract{border-color:#f59e0b;border-top-style:dashed}.swatch.contract-safety{border-color:#ea580c;border-top-style:dotted}.swatch.simulation{border-color:#8b5cf6;border-top-style:dashed}.swatch.operational{border-color:#0891b2;border-top-style:dashed}.forecast-anchor{fill:var(--card);stroke:#0284c7;stroke-width:4}.time-label{font-size:12px}.axis-title{font-size:13px}@media(max-width:700px){.chart-legend{font-size:.78rem;gap:8px 12px}.chart-key{font-size:.78rem;line-height:1.4}.time-label{font-size:13px}.axis-title{font-size:14px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}`;
  }
}

customElements.define("si-grid-monitor-panel", SIGridMonitorPanel);
