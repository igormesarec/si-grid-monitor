import {
  BLOCK_COLORS,
  CHART_SERIES,
  RequestGate,
  adjacentPeriodAnchor,
  blockChartModel,
  calendarDateLabel,
  chartViewStateForRender,
  dayStatusLabel,
  defaultTodayQuarter,
  energyAxisScale,
  exceedanceRequest,
  historyErrorMessage,
  historyQuarterChartModel,
  ljubljanaDate,
  ljubljanaTimeLabel,
  livePowerChartModel,
  localQuarterLabel,
  moveTodayQuarter,
  periodChartModel,
  periodAxisLabels,
  periodBinDescription,
  periodDrillDown,
  periodRequest,
  quarterEnergyModel,
  quarterNavigation,
  restoreChartScrollState,
  selectTimelineHour,
  todayChartModel,
  todayQuarterAction,
} from "./dashboard-model.mjs?v=0.8.0";
import {dashboardLanguage, localizeDashboard, translateDashboard} from "./dashboard-i18n.mjs?v=0.8.0";

const fmt = (value, digits = 2) => value == null ? "—" : Number(value).toFixed(digits);
const fmtEnergyReference = value => value == null ? "—" : Number(value).toFixed(3);
const fmtAxis = value => {
  const magnitude = Math.abs(Number(value));
  if (magnitude < 1e-12) return "0";
  return magnitude < 0.1 ? Number(value).toFixed(3) : magnitude < 1 ? Number(value).toFixed(2) : Number(value).toFixed(1);
};
const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
})[character]);
const localDate = value => ljubljanaDate(value);
const localTime = value => ljubljanaTimeLabel(value);

export class SIGridMonitorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._tab = "overview";
    this._entryId = null;
    this._entries = [];
    this._selectedDate = localDate();
    this._gate = new RequestGate();
    this._historyGate = new RequestGate();
    this._resetEntryState();
  }

  set hass(value) {
    const previousLanguage = dashboardLanguage(this._hass);
    this._hass = value;
    if (!this._loaded) this._load();
    else if (previousLanguage !== dashboardLanguage(value)) this._render();
  }

  set panel(value) { this._panel = value; }
  set route(value) { this._route = value; }

  _t(key, parameters = {}) {
    return translateDashboard(key, dashboardLanguage(this._hass), parameters);
  }

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
    this._historyGate.invalidate();
  }

  _resetEntryState() {
    this._live = null;
    this._day = null;
    this._dayError = null;
    this._calendar = null;
    this._tariffStatus = null;
    this._calendarError = null;
    this._transitions = null;
    this._period = null;
    this._blocks = null;
    this._exceedances = null;
    this._historyPage = null;
    this._historyPageError = null;
    this._historyPageLoading = false;
    this._historyAudit = null;
    this._historyAuditError = null;
    this._historyAuditLoading = false;
    this._historyPageNumber ??= 1;
    this._historyPageSize ??= 50;
    this._historyQuality ??= "all";
    this._historyBlock ??= "all";
    this._historyConfirmed ??= "all";
    this._historySourceEpoch = "all";
    this._historySort ??= "start_utc";
    this._historyDirection ??= "desc";
    if (!this._historyStartDate) {
      const start = new Date();
      start.setDate(start.getDate() - 30);
      this._historyStartDate = localDate(start);
    }
    this._historyEndDate ??= this._selectedDate;
    this._periodError = null;
    this._periodLoading = false;
    this._periodType ??= "day";
    this._periodAnchor ??= this._selectedDate;
    this._periodBlock ??= "all";
    this._periodChartMode ??= "energy";
    this._selectedBlock ??= null;
    this._exceedanceSort ??= "date";
    this._exceedanceDirection ??= "desc";
    this._exceedancePage ??= 1;
    this._exceedancePageSize ??= 25;
    this._customStart ??= this._selectedDate;
    this._customEnd ??= this._selectedDate;
    this._historical = null;
    this._historicalStart = null;
    this._historicalDate = null;
    this._historicalError = null;
    this._historicalLoading = false;
    this._historicalRequestOwner = null;
    this._historicalRequestPromise = null;
    this._historicalRequestToken = null;
    this._selectedHourUtc = null;
    this._selectedTodayQuarterUtc = null;
    this._todaySelectionMessage = null;
    this._calendarScrollLeft = 0;
    this._todayScrollLeft = 0;
    this._chartScrollPositions = {power: 0, energy: 0};
    this._chartDataKey = null;
    this._resetChartScrollOnRender = true;
    this._error = null;
  }

  _resetAnalysisScroll() {
    this._chartScrollPositions = {
      ...this._chartScrollPositions,
      period: 0,
      exceedances: 0,
    };
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
        this._historyGate.switchEntry(entryId);
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
    this._historyGate.switchEntry(entryId);
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
        const starts = new Set((day.quarters || []).map(item => item.start_utc));
        if (!this._selectedTodayQuarterUtc || !starts.has(this._selectedTodayQuarterUtc)) {
          this._selectedTodayQuarterUtc = defaultTodayQuarter(
            day.quarters || [], this._selectedDate, localDate(),
          );
          this._todaySelectionMessage = null;
        }
        const selectedQuarter = (day.quarters || []).find(
          item => item.start_utc === this._selectedTodayQuarterUtc,
        );
        if (todayQuarterAction(selectedQuarter) === "archive") {
          await this._loadHistoricalQuarter(selectedQuarter.start_utc, {
            entryId, selectedDate: this._selectedDate, render: false,
          });
          if (!this._gate.accepts(token)) return;
        } else if (todayQuarterAction(selectedQuarter) !== "archive") {
          this._historyGate.invalidate();
          this._historicalRequestOwner = null;
          this._historicalRequestPromise = null;
          this._historicalRequestToken = null;
          this._historical = null;
          this._historicalStart = null;
          this._historicalDate = null;
          this._historicalError = null;
        }
        this._dayError = null;
      } else if (this._tab === "period") {
        this._periodLoading = true;
        const period = await this._call(
          "period",
          periodRequest({
            periodType: this._periodType,
            periodAnchor: this._periodAnchor,
            selectedDate: this._selectedDate,
            customStart: this._customStart,
            customEnd: this._customEnd,
            periodBlock: this._periodBlock,
          }),
          entryId,
        );
        if (!this._gate.accepts(token)) return;
        this._period = period;
        this._periodError = null;
        this._periodLoading = false;
      } else if (this._tab === "blocks") {
        this._periodLoading = true;
        const blocks = await this._call("blocks", periodRequest({
          periodType: this._periodType,
          periodAnchor: this._periodAnchor,
          selectedDate: this._selectedDate,
          customStart: this._customStart,
          customEnd: this._customEnd,
          periodBlock: this._periodBlock,
        }), entryId);
        if (!this._gate.accepts(token)) return;
        this._blocks = blocks;
        this._periodError = null;
        this._periodLoading = false;
      } else if (this._tab === "exceedances") {
        this._periodLoading = true;
        const exceedances = await this._call("exceedances", exceedanceRequest({
          periodType: this._periodType,
          periodAnchor: this._periodAnchor,
          selectedDate: this._selectedDate,
          customStart: this._customStart,
          customEnd: this._customEnd,
          periodBlock: this._periodBlock,
          exceedanceSort: this._exceedanceSort,
          exceedanceDirection: this._exceedanceDirection,
          exceedancePage: this._exceedancePage,
          exceedancePageSize: this._exceedancePageSize,
        }), entryId);
        if (!this._gate.accepts(token)) return;
        this._exceedances = exceedances;
        this._periodError = null;
        this._periodLoading = false;
      } else if (this._tab === "history") {
        this._historyPageLoading = true;
        const history = await this._call("history", {
          start_date: this._historyStartDate,
          end_date: this._historyEndDate,
          ...(this._historyBlock === "all" ? {} : {tariff_block: Number(this._historyBlock)}),
          ...(this._historyQuality === "all" ? {} : {qualities: [this._historyQuality]}),
          ...(this._historyConfirmed === "all" ? {} : {exceedance_status: this._historyConfirmed}),
          ...(this._historySourceEpoch === "all" ? {} : {source_epoch: Number(this._historySourceEpoch)}),
          page: this._historyPageNumber,
          page_size: this._historyPageSize,
          sort_by: this._historySort,
          direction: this._historyDirection,
        }, entryId);
        if (!this._gate.accepts(token)) return;
        this._historyPage = history;
        this._historyPageError = null;
        this._historyPageLoading = false;
      } else {
        const [calendar, tariffStatus] = await Promise.all([
          this._call("calendar", {date: this._selectedDate}, entryId),
          this._call("tariff_status", {}, entryId),
        ]);
        if (!this._gate.accepts(token)) return;
        this._calendar = calendar;
        this._tariffStatus = tariffStatus;
        this._calendarError = null;
      }
      this._error = null;
    } catch (error) {
      if (this._gate.accepts(token)) {
        if (this._tab === "today") {
          this._day = null;
          this._dayError = historyErrorMessage("day", error);
        } else if (["period", "blocks", "exceedances"].includes(this._tab)) {
          this._period = null;
          this._blocks = null;
          this._exceedances = null;
          this._periodLoading = false;
          this._periodError = error?.message || "Could not load the selected period.";
        } else if (this._tab === "history") {
          this._historyPage = null;
          this._historyPageLoading = false;
          this._historyPageError = error?.message || "Could not load the HISTORY archive.";
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
        (this._tab === "today" && this._selectedDate === localDate()) ||
        (["period", "blocks", "exceedances"].includes(this._tab)
          && (this._period || this._blocks || this._exceedances)?.period?.partial)) {
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
    if (["period", "blocks", "exceedances"].includes(this._tab)) {
      this._resetAnalysisScroll();
      this._periodAnchor = value;
      if (this._periodType === "custom") {
        this._customStart = value;
        this._customEnd = value;
      }
      this._period = null;
      this._blocks = null;
      this._exceedances = null;
      this._periodError = null;
    }
    this._historyGate.invalidate();
    this._selectedHourUtc = null;
    this._selectedTodayQuarterUtc = null;
    this._todaySelectionMessage = null;
    this._historical = null;
    this._historicalStart = null;
    this._historicalDate = null;
    this._historicalError = null;
    this._historicalLoading = false;
    this._historicalRequestOwner = null;
    this._historicalRequestPromise = null;
    this._historicalRequestToken = null;
    this._calendarScrollLeft = 0;
    this._todayScrollLeft = 0;
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

  async _loadHistoricalQuarter(startUtc, {
    entryId = this._entryId,
    selectedDate = localDate(new Date(startUtc)),
    render = true,
    force = false,
  } = {}) {
    if (!startUtc || !entryId) return null;
    const owner = `${entryId}|${selectedDate}|${startUtc}`;
    if (!force && owner === this._historicalRequestOwner) {
      if (this._historicalRequestPromise && this._historicalRequestToken
          && this._historyGate.accepts(this._historicalRequestToken)) {
        return this._historicalRequestPromise;
      }
      this._historicalRequestPromise = null;
      this._historicalRequestToken = null;
      this._historicalLoading = false;
      if (this._historical || this._historicalError) return this._historical;
    }
    const token = this._historyGate.invalidate();
    this._historicalRequestOwner = owner;
    this._historicalStart = startUtc;
    this._historicalDate = selectedDate;
    this._historical = null;
    this._historicalError = null;
    this._historicalLoading = true;
    this._historicalRequestToken = token;
    if (render) this._render();
    let request;
    request = (async () => {
      try {
        const historical = await this._call("quarter", {start_utc: startUtc}, entryId);
        if (!this._historyGate.accepts(token)
            || this._historicalRequestOwner !== owner) return null;
        this._historical = historical;
        this._historicalError = null;
        this._error = null;
        return historical;
      } catch (error) {
        if (this._historyGate.accepts(token)
            && this._historicalRequestOwner === owner) {
          this._historical = null;
          this._historicalError = historyErrorMessage("quarter", error);
        }
        return null;
      } finally {
        if (this._historyGate.accepts(token)
            && this._historicalRequestOwner === owner) {
          this._historicalLoading = false;
          if (this._historicalRequestPromise === request) {
            this._historicalRequestPromise = null;
            this._historicalRequestToken = null;
          }
          if (render) this._render();
        }
      }
    })();
    this._historicalRequestPromise = request;
    return request;
  }

  async _quarter(startUtc, {force = false} = {}) {
    return this._loadHistoricalQuarter(startUtc, {force});
  }

  async _selectTodayQuarter(startUtc, focus = false) {
    const quarters = this._day?.quarters || [];
    const selected = quarters.find(item => item.start_utc === startUtc);
    if (!selected) return;
    this._selectedTodayQuarterUtc = startUtc;
    const action = todayQuarterAction(selected);
    this._todaySelectionMessage = action === "upcoming"
      ? "Not measured yet. This interval is upcoming."
      : action === "missing"
        ? "No valid archived measurement exists for this past interval; missing data is not shown as zero."
        : action === "live"
          ? selected.display_status === "live"
            ? "Live interval in progress; projected values are not confirmed results."
            : "The current interval has no valid live measurement yet."
          : null;
    if (action === "archive") {
      await this._quarter(startUtc);
    } else {
      this._historyGate.invalidate();
      this._historicalRequestOwner = null;
      this._historicalRequestPromise = null;
      this._historicalRequestToken = null;
      this._historical = null;
      this._historicalStart = null;
      this._historicalDate = null;
      this._historicalError = null;
      this._historicalLoading = false;
      this._render();
    }
    if (focus) {
      [...(this.shadowRoot?.querySelectorAll("[data-quarter]") || [])]
        .find(element => element.dataset.quarter === startUtc)
        ?.focus({preventScroll: true});
    }
  }

  _moveTodayQuarter(delta) {
    const next = moveTodayQuarter(
      this._day?.quarters || [], this._selectedTodayQuarterUtc, delta,
    );
    if (next) this._selectTodayQuarter(next, true);
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

  _chartLegend(items) {
    return items.map(([kind, label]) => `<span><svg class="legend-line" viewBox="0 0 28 6" aria-hidden="true"><line class="${kind}" x1="1" x2="27" y1="3" y2="3"/></svg>${esc(label)}</span>`).join("");
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
    const x = timestamp => 44 + (Date.parse(timestamp) - start) / (end - start) * 1036;
    const plotTop = 24;
    const plotBottom = 220;
    const domainSpan = model.domainMaxKw - model.domainMinKw;
    const y = value => plotBottom
      - (Number(value) - model.domainMinKw) / domainSpan * (plotBottom - plotTop);
    const path = points => points.map(point => `${x(point.timestamp)},${y(point.kw)}`).join(" ");
    const paths = (segments, className) => segments
      .filter(points => points.length > 1)
      .map(points => `<polyline class="${className}" points="${path(points)}"/>`).join("");
    const reference = (value, className) => value == null ? "" :
      `<line class="${className}" x1="44" x2="1080" y1="${y(value)}" y2="${y(value)}"/>`;
    const same = (left, right) => left != null && right != null
      && Math.abs(Number(left) - Number(right)) <= 0.0001;
    const operationalMatchesContract = same(
      forecast.operational_target_kw, tariff.contractual_target_kw,
    );
    const operationalMatchesSafety = same(
      forecast.operational_target_kw, tariff.contractual_operational_target_kw,
    ) && tariff.safety_margin_kw > 0;
    const contractual = reference(tariff.contractual_target_kw, "contractual-target");
    const contractualSafety = tariff.safety_margin_kw > 0
      ? reference(tariff.contractual_operational_target_kw, "contractual-safety-target") : "";
    const simulation = tariff.simulation_enabled
      ? reference(tariff.simulation_target_kw, "simulation-target") : "";
    const showOperational = forecast.operational_target_kw != null
      && !operationalMatchesContract && !operationalMatchesSafety;
    const operational = showOperational
      ? reference(forecast.operational_target_kw, "operational-target") : "";
    const grid = model.gridValues.map(value => `<g><line class="power-grid ${value === 0 ? "zero" : ""}" x1="44" x2="1080" y1="${y(value)}" y2="${y(value)}"/><text x="5" y="${y(value) + 4}">${value > 0 ? "+" : value < 0 ? "−" : ""}${fmtAxis(Math.abs(value))} kW</text></g>`).join("");
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
    const legend = this._chartLegend([
      ["import", "Actual import"], ...(model.hasExport ? [["export", "Actual export"]] : []),
      ["smooth", "Historical smoothing"], ["future", "Future assumption"],
      ...(tariff.contractual_target_kw == null ? [] : [["contract", `${operationalMatchesContract ? "Distributor / operational target" : "Distributor limit"} ${fmt(tariff.contractual_target_kw)} kW`]]),
      ...(tariff.safety_margin_kw > 0 && tariff.contractual_operational_target_kw != null ? [["contract-safety", `${operationalMatchesSafety ? "Contract safety / operational target" : "Contract safety reference"} ${fmt(tariff.contractual_operational_target_kw)} kW`]] : []),
      ...(tariff.simulation_enabled ? [["simulation", `SIMULATION threshold ${fmt(tariff.simulation_target_kw)} kW`]] : []),
      ...(showOperational ? [["operational", `Engine operational target ${fmt(forecast.operational_target_kw)} kW`]] : []),
    ]);
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
    const scale = energyAxisScale([
      energy.usedKwh,
      energy.projectedFinalKwh,
      energy.contractualLimitKwh,
      energy.contractualSafetyTargetKwh,
      energy.operationalTargetKwh,
      energy.simulationTargetKwh,
    ]);
    const maxKwh = scale.maxKwh;
    const x = timestamp => 48 + (Date.parse(timestamp) - start) / (end - start) * 1028;
    const y = value => 205 - Number(value) / maxKwh * 170;
    const points = values => values.map(point => `${x(point.timestamp)},${y(point.kwh)}`).join(" ");
    const reference = (value, className) => value == null ? "" :
      `<line class="${className}" x1="48" x2="1076" y1="${y(value)}" y2="${y(value)}"/>`;
    const same = (left, right) => left != null && right != null
      && Math.abs(Number(left) - Number(right)) <= 0.000001;
    const operationalMatchesContract = same(
      energy.operationalTargetKwh, energy.contractualLimitKwh,
    );
    const operationalMatchesSafety = same(
      energy.operationalTargetKwh, energy.contractualSafetyTargetKwh,
    );
    const contractual = reference(
      energy.contractualLimitKwh, "energy-contractual-limit",
    );
    const contractualSafety = reference(
      energy.contractualSafetyTargetKwh, "energy-contractual-safety-target",
    );
    const simulation = reference(
      energy.simulationTargetKwh, "energy-simulation-target",
    );
    const showOperational = energy.operationalTargetKwh != null
      && !operationalMatchesContract && !operationalMatchesSafety;
    const operational = showOperational
      ? reference(energy.operationalTargetKwh, "energy-operational-target") : "";
    const projection = energy.projection.length ? `<polyline class="energy-projection" points="${points(energy.projection)}"/>` : "";
    const actual = energy.actualSegments
      .filter(segment => segment.length > 1)
      .map(segment => `<polyline class="energy-actual" points="${points(segment)}"/>`).join("");
    const trajectoryNote = esc(energy.trajectoryReason);
    const projectionNote = energy.projection.length
      ? "Dashed purple is an estimate from the authoritative current point, not a measurement."
      : esc(energy.projectionReason);
    const legend = this._chartLegend([
      ["energy-actual", "Imported energy"], ["energy-projection", "Projected energy"],
      ...(energy.contractualLimitKwh == null ? [] : [["contract", `${operationalMatchesContract ? "Distributor / operational target" : "Distributor limit"} ${fmtEnergyReference(energy.contractualLimitKwh)} kWh`]]),
      ...(energy.contractualSafetyTargetKwh == null ? [] : [["contract-safety", `${operationalMatchesSafety ? "Contract safety / operational target" : "Contract safety reference"} ${fmtEnergyReference(energy.contractualSafetyTargetKwh)} kWh`]]),
      ...(energy.simulationTargetKwh == null ? [] : [["simulation", `SIMULATION threshold ${fmtEnergyReference(energy.simulationTargetKwh)} kWh`]]),
      ...(showOperational ? [["operational", `Engine operational target ${fmtEnergyReference(energy.operationalTargetKwh)} kWh`]] : []),
    ]);
    const energyGrid = scale.ticks.map(value => `<g><line class="power-grid ${value === 0 ? "zero" : ""}" x1="48" x2="1076" y1="${y(value)}" y2="${y(value)}"/><text x="5" y="${y(value) + 4}">${fmtAxis(value)} kWh</text></g>`).join("");
    return `<section class="energy-progress"><h3>Quarter energy progress</h3><div class="chart-scroll" data-chart-scroll="energy" tabindex="0" aria-label="Scrollable quarter energy chart"><svg viewBox="0 0 1120 260" role="img" aria-label="Cumulative import-only quarter energy in kilowatt-hours, with gaps left undisguised and separate contractual, safety, simulation, and engine targets">${energyGrid}${contractual}${contractualSafety}${simulation}${operational}${actual}${projection}<circle class="energy-current" cx="${x(energy.currentPoint.timestamp)}" cy="${y(energy.currentPoint.kwh)}" r="5"/><text class="axis-title" x="8" y="14">Energy (kWh)</text><text class="time-label" x="48" y="246">${esc(localTime(quarter.start_utc))}</text><text class="time-label" x="1076" y="246" text-anchor="end">${esc(localTime(quarter.end_utc))}</text></svg></div><div class="chart-legend">${legend}</div><div class="grid">${this._metric("Used so far", fmt(energy.usedKwh, 3), "kWh")}${this._metric("Projected final energy", fmt(energy.projectedFinalKwh, 3), "kWh")}${this._metric("Distributor contractual limit", fmtEnergyReference(energy.contractualLimitKwh), "kWh")}${this._metric("Contract safety reference", fmtEnergyReference(energy.contractualSafetyTargetKwh), "kWh")}${live.tariff.simulation_enabled ? this._metric("SIMULATION threshold", fmtEnergyReference(energy.simulationTargetKwh), "kWh") : ""}${this._metric("Engine operational energy target", fmtEnergyReference(energy.operationalTargetKwh), "kWh")}${this._metric("Remaining operational budget", fmt(forecast.budget_remaining_kwh, 3), "kWh")}</div><p class="chart-key">${trajectoryNote} ${projectionNote} Export contributes zero and never reduces imported energy.</p></section>`;
  }

  _overview() {
    const live = this._live;
    if (!live) return `<section class="card">${esc(this._t("error.live_loading"))}</section>`;
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
    const currentForecastQuality = forecast.smoothed_future_quality || "unavailable";
    const currentForecastStatus = currentForecastQuality === "unavailable"
      ? `Unavailable: ${forecast.smoothed_future_reason || "no supported smoothed forecast"}`
      : `${currentForecastQuality}${forecast.smoothed_future_reason ? `: ${forecast.smoothed_future_reason}` : ""}`;
    const sustainedStatus = sustained.quality === "available"
      ? `Available · ${fmt(sustained.coverage_seconds, 0)} s coverage`
      : `Unavailable: ${sustained.reason || "insufficient valid measurement history"}`;
    return `<section class="card hero"><div class="herohead"><div><p class="eyebrow">CURRENT FIXED 15-MINUTE INTERVAL</p><h2>${esc(quarter.start_local.slice(0, 10))} · ${esc(quarter.start_local.slice(11, 16))}–${esc(quarter.end_local.slice(11, 16))}</h2><p>B${esc(tariff.block)} · ${fmt(tariff.target_kw)} kW · ${esc(quarter.quality)}</p></div><div class="count" data-countdown>--:--</div></div>
      <div class="direction"><div class="import"><span>IMPORT</span><b>${fmt(power.import_kw)} kW</b></div><div class="export"><span>EXPORT</span><b>${fmt(power.export_kw)} kW</b></div></div>${this._liveChart(live)}${this._energyChart(live)}
      <div class="grid">${this._metric("Signed grid power", fmt(power.signed_kw), "kW")}${this._metric("Source measurement age", fmt(power.source_age_seconds, 0), "seconds")}${this._metric("Imported so far", fmt(quarter.import_kwh, 3), "kWh")}${this._metric("Exported so far", fmt(quarter.export_kwh, 3), "kWh")}${this._metric("Import average", fmt(quarter.import_average_kw), "kW")}${this._metric("Instant projected final quarter average", fmt(displayedInstantForecast), "kW")}${this._metric("Smoothed projected final quarter average", fmt(displayedSmoothedForecast), "kW")}${this._metric("Current-quarter forecast status", currentForecastStatus)}${this._metric("Utilization", fmt(forecast.current_utilization_pct), "%")}${this._metric("Remaining budget", fmt(forecast.budget_remaining_kwh, 3), "kWh")}${this._metric("Allowed remainder", fmt(forecast.allowed_remaining_import_kw), "kW")}${this._metric("CAN ADD THIS QUARTER", fmt(forecast.can_add_kw), "kW", "good")}${this._metric("MUST REDUCE THIS QUARTER", fmt(forecast.must_reduce_kw), "kW", forecast.must_reduce_kw > 0 ? "bad" : "")}${this._metric("SUSTAINED CAN ADD", fmt(sustained.can_add_kw), "kW", "accent")}${this._metric("SUSTAINED MUST REDUCE", fmt(sustained.must_reduce_kw), "kW", sustained.must_reduce_kw > 0 ? "bad" : "")}${this._metric("Sustained forecast quality", sustainedStatus)}${this._metric("Sustained horizon", sustained.horizon_minutes, "minutes")}</div>${projectionWarning}
      <p class="safety"><strong>Electrical safety:</strong> CAN ADD and sustained headroom are billing-energy-budget estimates only. They are not permission or assurance that the breaker, phases, grid connection, wiring, or inverter can carry that instantaneous load.</p></section>
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
      if (item.start_utc === this._selectedTodayQuarterUtc) classes.push("selected");
      const slotTop = model.margin.top;
      const slotHeight = model.height - model.margin.top - model.margin.bottom;
      const stateRect = ["missing", "upcoming", "live_unavailable"].includes(item.display_status) || !item.measurement_valid && item.display_status !== "live" || item.contractual_status === "provisional_estimate"
        ? `<rect class="state ${esc(classes.join(" "))}" x="${item.centerX - model.slot * 0.32}" y="${slotTop}" width="${model.slot * 0.64}" height="${slotHeight}"/>` : "";
      const importBar = item.importY == null ? "" : `<rect class="import-bar" x="${item.leftX}" y="${item.importY}" width="${item.barWidth}" height="${item.importHeight}"/>`;
      const exportBar = item.exportHeight <= 0 ? "" : `<rect class="export-bar" x="${item.leftX}" y="${item.exportY}" width="${item.barWidth}" height="${item.exportHeight}"/>`;
      const exceeded = item.confirmed_exceeded ? `<rect class="exceeded" x="${item.centerX - model.slot * 0.42}" y="${slotTop}" width="${model.slot * 0.84}" height="${slotHeight}"/>` : "";
      const projection = item.display_status === "live" && item.projected_import_demand_kw != null
        ? `<circle class="projection" cx="${item.centerX}" cy="${model.valueToY(item.projected_import_demand_kw)}" r="4"/>` : "";
      const hitArea = `<rect class="quarter-hit-area" x="${item.centerX - model.slot / 2}" y="${slotTop}" width="${model.slot}" height="${slotHeight}"/>`;
      const selection = item.start_utc === this._selectedTodayQuarterUtc
        ? `<rect class="quarter-selection" x="${item.centerX - model.slot * 0.46}" y="${slotTop}" width="${model.slot * 0.92}" height="${slotHeight}"/>` : "";
      return `<g class="${esc(classes.join(" "))}" tabindex="0" role="button" aria-pressed="${item.start_utc === this._selectedTodayQuarterUtc}" data-quarter="${esc(item.start_utc)}" data-status="${esc(item.display_status)}" aria-label="${esc(`${localQuarterLabel(item.start_utc)}; ${dayStatusLabel(item)}; import ${fmt(item.importKw)} kW; export ${fmt(item.exportKw)} kW; target ${fmt(item.targetKw)} kW`)}">${hitArea}${stateRect}${importBar}${exportBar}${exceeded}${projection}${selection}</g>`;
    }).join("");
    const targets = model.targetSegments.map(segment => `<line class="target-step" x1="${segment.x1}" x2="${segment.x2}" y1="${segment.y}" y2="${segment.y}"/>`).join("");
    const axis = ticks.map(value => `<g><line class="gridline ${value === 0 ? "zero" : ""}" x1="${model.margin.left}" x2="${model.width - model.margin.right}" y1="${model.valueToY(value)}" y2="${model.valueToY(value)}"/><text x="4" y="${model.valueToY(value) + 4}">${value > 0 ? "+" : value < 0 ? "−" : ""}${fmt(Math.abs(value))} kW</text></g>`).join("");
    return `<div class="daychart" data-today-scroll tabindex="0"><svg viewBox="0 0 ${model.width} ${model.height}" role="img" aria-label="Zero-centered daily power chart in kW. Import demand is above zero, exported average power below zero, and the gold stepped line is contracted power."><defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#f59e0b" stroke-width="2"/></pattern></defs>${backgrounds}${axis}${targets}${states}<text class="axis-title" x="4" y="14">Power (kW)</text></svg></div>`;
  }

  _todayQuarterDetails(selected) {
    if (!selected) return `<div class="empty">Select a 15-minute interval.</div>`;
    const status = dayStatusLabel(selected);
    const heading = `${localQuarterLabel(selected.start_utc)} – ${localTime(selected.end_utc)} · ${status}`;
    if (selected.display_status === "live") {
      return `<div class="selected-quarter"><h3>${esc(heading)}</h3><div class="grid">${this._metric("Live current-quarter energy", fmt(selected.import_kwh, 3), "kWh")}${this._metric("Live exported energy", fmt(selected.export_kwh, 3), "kWh")}${this._metric("Elapsed", fmt(selected.elapsed_seconds / 60), "minutes")}${this._metric("Measurement coverage", fmt(selected.coverage_seconds), "seconds")}${this._metric("Current import average", fmt(selected.import_demand_kw), "kW")}${this._metric("Projected final import demand", fmt(selected.projected_import_demand_kw), "kW")}${this._metric("Projected exceedance", selected.projected_exceedance == null ? "Unavailable" : selected.projected_exceedance ? "Projected" : "No")}${this._metric("Confirmed exceedance", "Not until completion")}</div><p class="safety">Live and projected values are separate from completed-quarter statistics.</p></div>`;
    }
    if (["completed", "simulation"].includes(selected.display_status)) {
      return `<div class="selected-quarter"><h3>${esc(heading)}</h3>${this._historicalCard()}</div>`;
    }
    if (selected.display_status === "live_unavailable") {
      return `<div class="selected-quarter"><h3>${esc(heading)}</h3><p class="empty">Current measurements are unavailable. SI Grid Monitor is waiting for a valid live source reading; this is not a missing historical archive record.</p></div>`;
    }
    return `<div class="selected-quarter"><h3>${esc(heading)}</h3><p class="empty">${esc(this._todaySelectionMessage || (selected.display_status === "upcoming" ? "Not measured yet." : "No valid archived measurement exists."))}</p></div>`;
  }

  _today() {
    if (this._dayError) return `<section class="card error"><h2>${esc(this._t("error.day_unavailable"))}</h2><p>${esc(this._dayError)}</p><button data-retry-day>${esc(this._t("common.retry"))}</button></section>`;
    const day = this._day;
    if (!day) return `<section class="card">${esc(this._t("error.day_loading"))}</section>`;
    const quarters = day.quarters || [];
    const current = quarters.find(item => item.display_status === "live");
    const selected = quarters.find(item => item.start_utc === this._selectedTodayQuarterUtc);
    const selectedIndex = quarters.findIndex(item => item.start_utc === this._selectedTodayQuarterUtc);
    const selector = `<div class="quarter-selector" aria-label="15-minute interval selection"><button data-today-prev data-today-control="prev" ${selectedIndex <= 0 ? "disabled" : ""}>Previous 15 minutes</button><select data-today-quarter data-today-control="select" aria-label="Selected 15-minute interval">${quarters.map(item => `<option value="${esc(item.start_utc)}" ${item.start_utc === this._selectedTodayQuarterUtc ? "selected" : ""}>${esc(`${localTime(item.start_utc)}–${localTime(item.end_utc)} · ${dayStatusLabel(item)}`)}</option>`).join("")}</select><button data-today-next data-today-control="next" ${selectedIndex < 0 || selectedIndex >= quarters.length - 1 ? "disabled" : ""}>Next 15 minutes</button></div>`;
    return `<section class="card"><div class="row"><button data-day="-1">‹</button><input data-date type="date" value="${esc(this._selectedDate)}"><button data-day="1">›</button><button data-today>Today</button></div><h2>${esc(this._selectedDate)} · ${day.expected_quarters} aligned quarters</h2>${this._todayChart(quarters)}<div class="chart-key">Red: import-only quarter demand (kW) · Green: average exported power below zero (kW) · Gold: original contracted limit · Dot: live projection · Outline: confirmed exceedance · Hatched: missing/incomplete/provisional</div>${selector}${this._todayQuarterDetails(selected)}<div class="grid">${this._metric("Valid completed-quarter energy", fmt(day.summary.import_kwh), "kWh")}${this._metric("Valid completed-quarter export", fmt(day.summary.export_kwh), "kWh")}${this._metric("Separately observed incomplete-quarter import", fmt(day.summary.partial_observed_import_kwh), "kWh")}${this._metric("Separately observed incomplete-quarter export", fmt(day.summary.partial_observed_export_kwh), "kWh")}${this._metric("Live current-quarter energy", fmt(current?.import_kwh, 3), "kWh")}${this._metric("Live current-quarter export", fmt(current?.export_kwh, 3), "kWh")}${this._metric("Maximum valid completed-quarter demand", fmt(day.summary.maximum_import_demand_kw), "kW")}${this._metric("Average valid completed-quarter demand", fmt(day.summary.average_import_demand_kw), "kW")}${this._metric("Contributing valid completed quarters", day.summary.valid_count)}${this._metric("Contract eligible", day.summary.contractual_eligible_count)}${this._metric("Incomplete completed quarters", day.summary.incomplete_count)}${this._metric("Missing past intervals", day.summary.missing_count)}${this._metric("Upcoming intervals", day.summary.upcoming_count)}${this._metric("Confirmed exceedances", day.summary.exceeded_count)}</div><p class="chart-key">Average valid demand is the arithmetic mean of import-only demand across the contributing valid completed 15-minute quarters, not a whole-day or instantaneous average. Partial observed and live energy are excluded from valid totals. Confirmed exceedances use eligible completed quarters only; zero confirmed exceedances does not prove incomplete quarters stayed below their limits.</p><h3>Five tariff blocks</h3><table><thead><tr><th>Block</th><th>Active</th><th>Hours</th><th>Original targets</th><th>Valid / eligible</th><th>Incomplete / missing</th><th>Max / avg kW</th><th>Import / export kWh</th><th>Confirmed exceeded</th></tr></thead><tbody>${day.blocks.map(block => `<tr><td><span class="chip b${block.block}">B${block.block}</span></td><td>${block.active ? "Yes" : "Not active today"}</td><td>${fmt(block.active_hours)}</td><td>${block.targets_kw.length ? block.targets_kw.map(value => fmt(value)).join(", ") : "Unknown"}</td><td>${block.valid_count} / ${block.contractual_eligible_count}</td><td>${block.incomplete_count} / ${block.missing_count}</td><td>${fmt(block.maximum_import_demand_kw)} / ${fmt(block.average_import_demand_kw)}</td><td>${fmt(block.import_kwh)} / ${fmt(block.export_kwh)}</td><td>${block.confirmed_exceedances} / ${fmt(block.confirmed_exceedance_pct)}%</td></tr>`).join("")}</tbody></table></section>`;
  }

  _periodControls() {
    const custom = this._periodType === "custom"
      ? `<label>Start <input data-custom-start type="date" value="${esc(this._customStart)}"></label><label>End <input data-custom-end type="date" value="${esc(this._customEnd)}"></label>`
      : `<input data-date type="date" value="${esc(this._selectedDate)}">`;
    return `<div class="period-controls"><button data-period-move="-1" aria-label="Previous period">‹</button><select data-period-type aria-label="Period type">${["hour", "day", "week", "month", "year", "custom"].map(value => `<option value="${value}" ${this._periodType === value ? "selected" : ""}>${value[0].toUpperCase()}${value.slice(1)}</option>`).join("")}</select>${custom}<select data-period-block aria-label="Tariff block filter"><option value="all">All blocks</option>${[1, 2, 3, 4, 5].map(block => `<option value="${block}" ${String(this._periodBlock) === String(block) ? "selected" : ""}>B${block}</option>`).join("")}</select><button data-period-move="1" aria-label="Next period">›</button><button data-period-current>Current period</button></div>`;
  }

  _periodChart() {
    const bins = this._period?.bins || [];
    if (!bins.length) return `<div class="empty">No completed archive bins are available for this selection.</div>`;
    const mode = this._periodChartMode;
    const model = periodChartModel(bins, mode);
    const resolution = this._period?.period?.resolution || "quarter";
    const labels = periodAxisLabels(bins, resolution);
    const labelBases = labels.map(label => label.replace(/ GMT[+-]\d+$/, ""));
    const repeatedLabels = new Set(
      labelBases.filter((label, index) => labelBases.indexOf(label) !== index),
    );
    const unit = mode === "energy" ? "kWh" : mode === "demand" ? "kW" : mode === "coverage" ? "%" : "count";
    const grid = model.ticks.map(value => `<g><line class="gridline" x1="${model.margin.left}" x2="${model.width - model.margin.right}" y1="${model.valueToY(value)}" y2="${model.valueToY(value)}"/><text x="4" y="${model.valueToY(value) + 4}">${fmtAxis(value)} ${unit}</text></g>`).join("");
    const items = model.items.map((item, index) => {
      const x = item.centerX;
      let marks = "";
      if (!item.hasMeasuredData) {
        marks = "";
      } else if (mode === "energy") {
        const importY = model.valueToY(item.import_kwh);
        const exportY = model.valueToY(item.export_kwh);
        marks = `<rect class="import-bar" x="${x - item.barWidth}" y="${importY}" width="${item.barWidth}" height="${model.valueToY(0) - importY}"/><rect class="export-bar" x="${x}" y="${exportY}" width="${item.barWidth}" height="${model.valueToY(0) - exportY}"/>`;
      } else if (mode === "demand") {
        const maximumY = model.valueToY(item.maximum_import_demand_kw);
        const averageY = model.valueToY(item.average_import_demand_kw);
        const targets = item.targets_kw || [];
        const targetLines = targets.map(target => `<line class="target-step" x1="${x - model.step / 2}" x2="${x + model.step / 2}" y1="${model.valueToY(target)}" y2="${model.valueToY(target)}"><title>Historical target ${fmt(target)} kW</title></line>`).join("");
        const maximumX = item.showAverage ? x - item.barWidth : x - item.barWidth / 2;
        const average = item.showAverage
          ? `<rect class="average-bar" x="${x}" y="${averageY}" width="${item.barWidth}" height="${model.valueToY(0) - averageY}"/>`
          : "";
        marks = `<rect class="import-bar" x="${maximumX}" y="${maximumY}" width="${item.barWidth}" height="${model.valueToY(0) - maximumY}"/>${average}${targetLines}`;
      } else {
        const value = mode === "coverage" ? item.coverage_pct : item.exceeded_count;
        const y = model.valueToY(value);
        marks = `<rect class="${mode === "coverage" ? "coverage-bar" : "exceedance-bar"}" x="${x - item.barWidth / 2}" y="${y}" width="${item.barWidth}" height="${model.valueToY(0) - y}"/>`;
      }
      const label = bins.length <= 32 || repeatedLabels.has(labelBases[index])
        || index % Math.ceil(bins.length / 12) === 0
        ? `<text class="time-label" x="${x}" y="${model.height - 18}" text-anchor="middle">${esc(labels[index])}</text>` : "";
      const description = periodBinDescription(item);
      return `<g class="period-bin ${item.status}" tabindex="0" role="button" data-period-bin="${index}" aria-label="${esc(description)}"><title>${esc(description)}</title><rect class="period-hit-area" x="${x - model.step / 2}" y="${model.margin.top}" width="${model.step}" height="${model.height - model.margin.top - model.margin.bottom}"/>${marks}${label}</g>`;
    }).join("");
    const measured = model.items.filter(item => item.hasMeasuredData);
    const missingVisible = model.items.some(item => !item.hasMeasuredData);
    let legend = "";
    if (mode === "energy") {
      legend = `<span><i class="swatch import"></i>${esc(this._t("period.imported_energy"))}</span><span><i class="swatch export"></i>${esc(this._t("period.exported_energy"))}</span>`;
    } else if (mode === "demand") {
      const average = measured.some(item => item.showAverage)
        ? `<span><i class="swatch smooth"></i>${esc(this._t("period.average_demand"))}</span>` : "";
      const target = measured.some(item => (item.targets_kw || []).length)
        ? `<span><i class="swatch contract"></i>${esc(this._t("period.historical_limit"))}</span>` : "";
      legend = `<span><i class="swatch import"></i>${esc(this._t("period.maximum_demand"))}</span>${average}${target}`;
    } else if (mode === "coverage") {
      legend = `<span><i class="swatch coverage"></i>${esc(this._t("period.valid_coverage"))}</span>`;
    } else {
      legend = `<span><i class="swatch exceedance"></i>${esc(this._t("period.confirmed_exceedances"))}</span>`;
    }
    if (missingVisible) legend += `<span><i class="swatch missing"></i>${esc(this._t("period.missing_measurements"))}</span>`;
    return `<div class="chart-scroll" data-chart-scroll="period" tabindex="0"><svg viewBox="0 0 ${model.width} ${model.height}" role="img" aria-label="${esc(this._t("period.chart_aria", {mode, unit}))}">${grid}${items}<text class="axis-title" x="4" y="14">${esc(unit)}</text></svg></div><div class="chart-legend" data-period-legend="${esc(mode)}">${legend}</div>`;
  }

  _periodView() {
    if (this._periodError) return `<section class="card error"><h2>${esc(this._t("error.period_unavailable"))}</h2><p>${esc(this._periodError)}</p><button data-retry-period>${esc(this._t("common.retry"))}</button></section>`;
    if (!this._period || this._periodLoading) return `<section class="card">${this._periodControls()}<p>${esc(this._t("error.period_loading"))}</p></section>`;
    const data = this._period;
    const summary = data.summary;
    const comparison = data.comparison;
    const comparisonReasons = {
      current_period_incomplete: "the selected period is partial or lacks complete valid coverage",
      no_previous_archive: "the previous period has no archived measurements",
      previous_period_incomplete: "the previous period lacks complete valid coverage",
      period_length_mismatch: "the periods contain different numbers of quarter-hours",
    };
    const quality = value => value
      ? `${value.valid_count}/${value.expected_count} valid, ${value.incomplete_count} incomplete, ${value.missing_count} missing (${fmt(value.coverage_pct)}% coverage)`
      : "not evaluated";
    const comparisonHtml = !comparison?.available
      ? `<div class="notice"><p>Previous-period comparison unavailable: ${esc(comparisonReasons[comparison?.reason] || comparison?.reason || "no comparable archive")}. Missing energy is not extrapolated or treated as zero.</p><p>Selected: ${esc(quality(comparison?.current_quality))} · Previous: ${esc(quality(comparison?.previous_quality))}</p></div>`
      : `<div class="grid">${this._metric("Import change", fmt(comparison.changes.import_kwh), "kWh")}${this._metric("Export change", fmt(comparison.changes.export_kwh), "kWh")}${this._metric("Maximum-demand change", fmt(comparison.changes.maximum_import_demand_kw), "kW")}</div><p class="chart-key">Comparable coverage: selected ${esc(quality(comparison.current_quality))}; previous ${esc(quality(comparison.previous_quality))}.</p>`;
    return `<section class="card">${this._periodControls()}<div class="herohead"><div><p class="eyebrow">HISTORICAL PERIOD</p><h2>${esc(data.period.label)}</h2><p>${esc(data.period.resolution)} bins · half-open ${esc(data.period.start_utc)} to ${esc(data.period.end_utc)}</p></div>${data.period.partial ? `<span class="chip b0">PARTIAL</span>` : ""}</div><div class="row chart-modes">${[["energy", "Import / export energy"], ["demand", "Import demand"], ["exceedances", "Exceedances"], ["coverage", "Coverage"]].map(([value, label]) => `<button data-chart-mode="${value}" class="${this._periodChartMode === value ? "active" : ""}">${label}</button>`).join("")}</div>${this._periodChart()}<div class="grid">${this._metric("Valid imported energy", fmt(summary.import_kwh), "kWh")}${this._metric("Valid exported energy", fmt(summary.export_kwh), "kWh")}${this._metric("Signed net energy", fmt(summary.signed_net_kwh), "kWh")}${this._metric("Maximum quarter import demand", fmt(summary.maximum_import_demand_kw), "kW")}${this._metric("Average valid quarter demand", fmt(summary.average_import_demand_kw), "kW")}${this._metric("Minimum signed quarter average", fmt(summary.minimum_signed_average_kw), "kW")}${this._metric("Maximum signed quarter average", fmt(summary.maximum_signed_average_kw), "kW")}${this._metric("Valid completed quarters", summary.valid_count)}${this._metric("Contract eligible", summary.contractual_eligible_count)}${this._metric("Incomplete", summary.incomplete_count)}${this._metric("Missing", summary.missing_count)}${this._metric("Partial observed import", fmt(summary.partial_observed_import_kwh), "kWh")}${this._metric("Partial observed export", fmt(summary.partial_observed_export_kwh), "kWh")}${this._metric("Confirmed exceedances", summary.exceeded_count)}${this._metric("Confirmed exceedance rate", fmt(summary.confirmed_exceedance_pct), "%")}${this._metric("Exceeded duration", summary.exceeded_duration_minutes, "minutes")}${this._metric("Data coverage", fmt(summary.coverage_pct), "%")}</div><p class="chart-key">Valid measurement totals exclude incomplete and simulation rows. Contractual results use only quarters with confirmed original targets and official rule status. Partial observed energy remains separate.</p><h3>Previous equivalent period</h3>${comparisonHtml}</section>`;
  }

  _blockCharts(blocks, totals = this._blocks?.totals) {
    const model = blockChartModel(blocks);
    const chart = (title, scale, value, value2 = null, unit = "") => {
      const left = 48;
      const plotWidth = 510;
      const grid = scale.ticks.map(tick => {
        const x = left + plotWidth * tick / scale.maximum;
        return `<g><line class="gridline" x1="${x}" x2="${x}" y1="24" y2="265"/><text x="${x}" y="282" text-anchor="middle">${fmtAxis(tick)}</text></g>`;
      }).join("");
      const rows = model.rows.map((row, index) => {
        const first = Number(value(row) || 0);
        const second = value2 ? Number(value2(row) || 0) : null;
        const width = plotWidth * first / scale.maximum;
        const width2 = second == null ? 0 : plotWidth * second / scale.maximum;
        const y = 34 + index * 48;
        return `<g class="block-chart-row" tabindex="0" role="button" data-block="${row.block}" aria-label="${esc(this._t("blocks.row_aria", {block: `B${row.block}`, maximum: fmt(first), average: second == null ? "" : fmt(second), unit}))}"><text x="8" y="${y + 15}">B${row.block}</text><rect x="${left}" y="${y}" width="${width}" height="14" fill="${BLOCK_COLORS[row.block]}"/>${second == null ? "" : `<rect x="${left}" y="${y + 18}" width="${width2}" height="8" fill="#38bdf8"/>`}<text x="630" y="${y + 15}" text-anchor="end">${fmt(first)}${second == null ? "" : ` / ${fmt(second)}`} ${unit}</text></g>`;
      }).join("");
      return `<div class="block-chart"><h3>${esc(title)}</h3><svg viewBox="0 0 640 300" role="img" aria-label="${esc(this._t("blocks.chart_aria", {title, unit}))}">${grid}${rows}<text x="558" y="296" text-anchor="end">${esc(unit)}</text></svg></div>`;
    };
    const reconciliation = totals ? `<div class="grid">${this._metric("Reconciled valid import", fmt(totals.import_kwh), "kWh")}${this._metric("Reconciled valid export", fmt(totals.export_kwh), "kWh")}${this._metric("Reconciled valid quarters", totals.valid_count)}${this._metric("Reconciled eligible quarters", totals.contractual_eligible_count)}</div>` : "";
    return `${reconciliation}<div class="block-charts">${chart(this._t("blocks.imported_energy"), model.energyScale, row => row.import_kwh, null, "kWh")}<div class="chart-legend">${model.rows.map(row => `<span><i class="block-swatch" style="background:${BLOCK_COLORS[row.block]}"></i>B${row.block}</span>`).join("")}<span>${esc(this._t("blocks.grid_energy"))}</span></div>${chart(this._t("blocks.maximum_average"), model.demandScale, row => row.maximum_import_demand_kw, row => row.average_import_demand_kw, "kW")}<div class="chart-legend"><span><i class="swatch import"></i>${esc(this._t("blocks.maximum_legend"))}</span><span><i class="swatch smooth"></i>${esc(this._t("blocks.average_legend"))}</span><span>${esc(this._t("blocks.grid_power"))}</span></div>${chart(this._t("blocks.confirmed_exceeded"), model.exceedanceScale, row => row.exceeded_count, null, this._t("common.quarters"))}</div>`;
  }

  _blocksView() {
    if (this._periodError) return `<section class="card error"><h2>${esc(this._t("error.blocks_unavailable"))}</h2><p>${esc(this._periodError)}</p><button data-retry-period>${esc(this._t("common.retry"))}</button></section>`;
    if (!this._blocks || this._periodLoading) return `<section class="card">${this._periodControls()}<p>${esc(this._t("error.blocks_loading"))}</p></section>`;
    const data = this._blocks;
    const selectedNumber = this._periodBlock === "all" ? null : Number(this._periodBlock);
    const selected = data.blocks.find(row => row.block === selectedNumber);
    const details = selected ? `<section class="block-detail"><h3>B${selected.block} details</h3><div class="grid">${this._metric("Peak timestamp", selected.peak_timestamp || "Unavailable")}${this._metric("Maximum demand", fmt(selected.maximum_import_demand_kw), "kW")}${this._metric("Average demand", fmt(selected.average_import_demand_kw), "kW")}${this._metric("Valid measured time", fmt(selected.valid_measured_hours), "hours")}${this._metric("Confirmed exceedances", selected.exceeded_count)}${this._metric("Largest excess", fmt(selected.maximum_excess_kw), "kW")}</div><h4>Highest-demand quarters</h4>${selected.high_demand_quarters.length ? `<table><thead><tr><th>Start</th><th>Demand</th><th>Original target</th><th>Quality</th></tr></thead><tbody>${selected.high_demand_quarters.map(row => `<tr data-block-quarter="${esc(row.start_utc)}" tabindex="0"><td>${esc(localQuarterLabel(row.start_utc))}</td><td>${fmt(row.import_demand_kw)} kW</td><td>${fmt(row.contractual_target_kw)} kW</td><td>${esc(row.quality)}</td></tr>`).join("")}</tbody></table>` : `<p class="empty">No valid measured quarters for B${selected.block}.</p>`}<button data-open-exceedances>View B${selected.block} exceedances</button></section>` : `<p class="notice">Select B1–B5 to inspect its original targets and highest-demand quarters.</p>`;
    return `<section class="card">${this._periodControls()}<p class="eyebrow">TARIFF BLOCK ANALYSIS</p><h2>${esc(data.period.label)}</h2>${this._blockCharts(data.blocks)}<table class="blocks-table"><thead><tr><th>Block</th><th>Active</th><th>Valid hours</th><th>Valid / eligible</th><th>Incomplete / missing</th><th>Import / export</th><th>Max / avg demand</th><th>Historical targets</th><th>Exceeded / rate</th><th>Largest excess</th></tr></thead><tbody>${data.blocks.map(row => `<tr data-block="${row.block}" tabindex="0" class="${selectedNumber === row.block ? "selected-row" : ""}"><td><span class="chip b${row.block}">B${row.block}</span></td><td>${row.active ? "Yes" : "Not active"}</td><td>${fmt(row.valid_measured_hours)}</td><td>${row.valid_count} / ${row.contractual_eligible_count}</td><td>${row.incomplete_count} / ${row.missing_count}</td><td>${fmt(row.import_kwh)} / ${fmt(row.export_kwh)} kWh</td><td>${fmt(row.maximum_import_demand_kw)} / ${fmt(row.average_import_demand_kw)} kW</td><td>${row.targets_kw.length ? row.targets_kw.map(target => fmt(target)).join("–") + " kW" : "Unknown"}</td><td>${row.exceeded_count} / ${fmt(row.confirmed_exceedance_pct)}%</td><td>${fmt(row.maximum_excess_kw)} kW</td></tr>`).join("")}</tbody></table><p class="chart-key">All five blocks remain visible. Values use each archived quarter's original target and provenance; provisional and simulation results never enter confirmed exceedances.</p>${details}</section>`;
  }

  _exceedancesView() {
    if (this._periodError) return `<section class="card error"><h2>${esc(this._t("error.exceedances_unavailable"))}</h2><p>${esc(this._periodError)}</p><button data-retry-period>${esc(this._t("common.retry"))}</button></section>`;
    if (!this._exceedances || this._periodLoading) return `<section class="card">${this._periodControls()}<p>${esc(this._t("error.exceedances_loading"))}</p></section>`;
    const data = this._exceedances;
    const summary = data.summary;
    const greatest = summary.greatest_exceedance;
    const emptyState = data.items.length ? "" : `<p class="notice">No confirmed exceeded quarters were found. This does not prove incomplete or missing intervals stayed below their limits.</p>`;
    const bins = data.bins || [];
    const chart = bins.length ? (() => {
      const width = 1120;
      const bottom = 214;
      const left = 62;
      const plotWidth = width - left - 24;
      const countMax = Math.max(1, ...bins.map(bin => Number(bin.exceeded_count || 0)));
      const excessMax = Math.max(1, ...bins.map(bin => Number(bin.maximum_excess_kw || 0)));
      const step = plotWidth / bins.length;
      const marks = bins.map((bin, index) => {
        const x = left + index * step;
        const countHeight = 160 * Number(bin.exceeded_count || 0) / countMax;
        const excessY = bottom - 160 * Number(bin.maximum_excess_kw || 0) / excessMax;
        return `<g><rect class="exceedance-bar" x="${x + step * .12}" y="${bottom - countHeight}" width="${Math.max(2, step * .45)}" height="${countHeight}"/><circle class="excess-point" cx="${x + step * .72}" cy="${excessY}" r="4" fill="var(--card)" stroke="#dc2626" stroke-width="3"><title>${fmt(bin.maximum_excess_kw)} kW maximum excess</title></circle></g>`;
      }).join("");
      return `<div class="chart-scroll" data-chart-scroll="exceedances" tabindex="0"><svg viewBox="0 0 ${width} 250" role="img" aria-label="Confirmed exceedance count and maximum excess severity"><line class="zero" x1="${left}" x2="${width - 24}" y1="${bottom}" y2="${bottom}"/>${marks}<text x="8" y="25">Count</text><text x="${width - 8}" y="25" text-anchor="end">Maximum excess (kW)</text><text x="8" y="${bottom}">0</text></svg></div><div class="chart-key">Purple bars: confirmed exceeded-quarter count · outlined points: maximum excess in kW. Axes are labeled separately.</div>`;
    })() : `<p class="empty">No archived bins are available for the exceedance chart.</p>`;
    const zeroState = `${emptyState}${chart}`;
    const table = data.items.length ? `<table class="exceedance-table"><thead><tr><th>Date / quarter</th><th>Block</th><th>Original target</th><th>Demand</th><th>Excess</th><th>Excess %</th><th>Equivalent energy</th><th>Quality</th><th>Rule status</th></tr></thead><tbody>${data.items.map(row => `<tr data-exceedance-quarter="${esc(row.start_utc)}" tabindex="0"><td>${esc(localQuarterLabel(row.start_utc))}–${esc(localTime(row.end_utc))}</td><td>${row.tariff_block ? `B${row.tariff_block}` : "Unknown"}</td><td>${fmt(row.contractual_target_kw)} kW</td><td>${fmt(row.import_demand_kw)} kW</td><td>${fmt(row.excess_kw)} kW</td><td>${fmt(row.excess_percentage)}%</td><td>${fmt(row.excess_energy_kwh, 3)} kWh</td><td>${esc(row.quality)}</td><td>${esc(row.contractual_status)}</td></tr>`).join("")}</tbody></table>` : "";
    return `<section class="card">${this._periodControls()}<div class="herohead"><div><p class="eyebrow">CONFIRMED CONTRACTUAL EXCEEDANCES</p><h2>${esc(data.period.label)}</h2></div><strong class="count">${summary.exceedance_count}</strong></div><div class="grid">${this._metric("Exceeded quarters", summary.exceedance_count)}${this._metric("Exceeded duration", summary.exceeded_duration_minutes, "minutes")}${this._metric("Maximum import demand", fmt(summary.maximum_import_demand_kw), "kW")}${this._metric("Maximum excess", fmt(summary.maximum_excess_kw), "kW")}${this._metric("Maximum excess percentage", fmt(summary.maximum_excess_percentage), "%")}${this._metric("Average excess", fmt(summary.average_excess_kw), "kW")}${this._metric("Confirmed rate", fmt(summary.confirmed_exceedance_rate_pct), "%")}${this._metric("Eligible quarters", summary.contractual_eligible_count)}${this._metric("Incomplete / unconfirmed", summary.incomplete_or_unconfirmed_count)}${this._metric("Most affected block", summary.most_affected_block ? `B${summary.most_affected_block}` : "—")}${this._metric("Greatest exceedance", greatest?.start_utc ? localQuarterLabel(greatest.start_utc) : "—")}</div><div class="exceedance-controls"><label>Sort <select data-exceedance-sort>${[["date", "Date"], ["demand", "Demand"], ["excess_kw", "Excess kW"], ["excess_percentage", "Excess %"]].map(([value, label]) => `<option value="${value}" ${value === this._exceedanceSort ? "selected" : ""}>${label}</option>`).join("")}</select></label><label>Order <select data-exceedance-direction><option value="desc" ${this._exceedanceDirection === "desc" ? "selected" : ""}>Descending</option><option value="asc" ${this._exceedanceDirection === "asc" ? "selected" : ""}>Ascending</option></select></label></div>${zeroState}${table}<div class="pagination"><button data-exceedance-page="${data.pagination.page - 1}" ${data.pagination.page <= 1 ? "disabled" : ""}>Previous</button><span>Page ${data.pagination.page} of ${Math.max(1, data.pagination.pages)} · ${data.pagination.total} quarters</span><button data-exceedance-page="${data.pagination.page + 1}" ${data.pagination.page >= data.pagination.pages ? "disabled" : ""}>Next</button></div><p class="chart-key">Each row is one confirmed 15-minute interval. Consecutive intervals are never merged. Equivalent excess energy is analytical only and is not an official network fee.</p></section>`;
  }

  _historyQuarterReport(data) {
    if (this._historyBlock === "all") {
      return `<p class="notice">${esc(this._t("history.select_block_report"))}</p>`;
    }
    const model = historyQuarterChartModel(data.items || []);
    if (!model.rows.length) return `<p class="empty">${esc(this._t("history.empty"))}</p>`;
    const grid = model.ticks.map(value => `<i class="history-grid" style="left:${100 * value / model.maximum}%"><b>${fmtAxis(value)}</b></i>`).join("");
    const chartRows = model.rows.map(row => {
      const demand = row.measured_valid && row.demandPct != null
        ? `<i class="history-demand" style="width:${row.demandPct}%"></i>`
        : `<em>${esc(this._t("common.unavailable"))}</em>`;
      const peak = row.peakPct == null ? "" : `<i class="history-peak" style="left:${row.peakPct}%" title="${esc(this._t("history.measured_peak"))}: ${fmt(row.measured_peak_kw)} kW"></i>`;
      const target = row.targetPct == null ? "" : `<i class="history-target" style="left:${row.targetPct}%" title="${esc(this._t("history.historical_limit"))}: ${fmt(row.contractual_target_kw)} kW"></i>`;
      return `<button type="button" class="history-chart-row" data-history-quarter="${esc(row.start_utc)}" aria-label="${esc(this._t("history.row_aria", {quarter: localQuarterLabel(row.start_utc), demand: fmt(row.import_demand_kw), target: fmt(row.contractual_target_kw), quality: row.quality}))}"><span>${esc(localQuarterLabel(row.start_utc))}<small>B${row.tariff_block} · ${esc(row.quality)}</small></span><span class="history-bar">${grid}${demand}${peak}${target}</span><span><b>${fmt(row.import_demand_kw)} kW</b><small>${fmt(row.coverage_pct)}%</small></span></button>`;
    }).join("");
    const tableRows = model.rows.map(row => `<tr data-history-quarter="${esc(row.start_utc)}" tabindex="0"><td>${esc(localQuarterLabel(row.start_utc))}–${esc(localTime(row.end_utc))}</td><td><code>${esc(row.start_utc)}</code></td><td>B${row.tariff_block}</td><td>${row.measured_valid ? `${fmt(row.import_demand_kw)} kW` : this._t("common.unavailable")}</td><td>${row.measured_peak_kw == null ? this._t("history.peak_not_archived") : `${fmt(row.measured_peak_kw)} kW`}</td><td>${fmt(row.contractual_target_kw)} kW</td><td>${row.confirmed_exceeded === true ? `${this._t("common.yes")} · ${fmt(row.excess_kw)} kW` : row.confirmed_exceeded === false ? this._t("common.no") : this._t("common.unconfirmed")}</td><td>${fmt(row.import_kwh,3)} / ${fmt(row.export_kwh,3)} kWh</td><td>${esc(row.quality)} · ${fmt(row.coverage_pct)}%</td><td>${esc(row.source_id || this._t("common.unknown"))} / ${row.source_epoch ?? "—"}</td><td>${esc(row.tariff_rule_version || this._t("common.unknown"))} · ${esc(row.tariff_rule_status || this._t("common.unknown"))}</td></tr>`).join("");
    return `<section class="history-quarter-report"><h3>${esc(this._t("history.quarter_report", {block: `B${this._historyBlock}`}))}</h3><p>${esc(this._t("history.quarter_report_help"))}</p><div class="history-axis"><span></span><span>${grid}</span><b>kW</b></div><div class="history-quarter-chart" data-chart-scroll="historyQuarters" tabindex="0" role="list" aria-label="${esc(this._t("history.chart_aria", {block: `B${this._historyBlock}`}))}">${chartRows}</div><div class="chart-legend"><span><i class="swatch import"></i>${esc(this._t("history.quarter_average"))}</span><span><i class="history-peak legend-marker"></i>${esc(this._t("history.measured_peak_evidence"))}</span><span><i class="swatch contract"></i>${esc(this._t("history.historical_limit"))}</span><span>${esc(this._t("history.grid_power"))}</span></div><div class="table-scroll"><table class="history-table"><thead><tr><th>${esc(this._t("history.local_quarter"))}</th><th>${esc(this._t("history.utc_identity"))}</th><th>${esc(this._t("history.block"))}</th><th>${esc(this._t("history.quarter_average"))}</th><th>${esc(this._t("history.measured_peak"))}</th><th>${esc(this._t("history.historical_limit"))}</th><th>${esc(this._t("history.excess"))}</th><th>${esc(this._t("history.import_export"))}</th><th>${esc(this._t("history.quality_coverage"))}</th><th>${esc(this._t("history.source_epoch"))}</th><th>${esc(this._t("history.tariff_rule"))}</th></tr></thead><tbody>${tableRows}</tbody></table></div></section>`;
  }

  _historyView() {
    if (this._historyPageError) return `<section class="card error"><h2>${esc(this._t("error.history_unavailable"))}</h2><p>${esc(this._historyPageError)}</p><button data-history-retry>${esc(this._t("common.retry"))}</button></section>`;
    const data = this._historyPage;
    const epochs = this._historyPage?.summary?.source_epochs || [];
    const qualityOptions = [
      ["all", this._t("history.all")], ["measured_aligned", "Measured aligned"],
      ["counter_derived", "Counter derived"], ["reconstructed", "Reconstructed"],
      ["incomplete", "Incomplete"], ["unavailable", this._t("common.unavailable")],
    ];
    const exceedanceOptions = [
      ["all", this._t("history.all")], ["confirmed_yes", this._t("history.confirmed_yes")],
      ["confirmed_no", this._t("history.confirmed_no")], ["unconfirmed", this._t("history.unconfirmed")],
    ];
    const controls = `<section class="card"><div class="history-controls"><label>${esc(this._t("history.from"))}<input data-history-start type="date" value="${esc(this._historyStartDate)}"></label><label>${esc(this._t("history.through"))}<input data-history-end type="date" value="${esc(this._historyEndDate)}"></label><label>${esc(this._t("history.tariff_block_filter"))}<select data-history-block><option value="all">${esc(this._t("history.all"))}</option>${[1,2,3,4,5].map(block => `<option value="${block}" ${this._historyBlock === String(block) ? "selected" : ""}>B${block}</option>`).join("")}</select></label><label>${esc(this._t("history.data_quality_filter"))}<select data-history-quality>${qualityOptions.map(([value,label]) => `<option value="${value}" ${this._historyQuality === value ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></label><label>${esc(this._t("history.exceedance_filter"))}<select data-history-confirmed>${exceedanceOptions.map(([value,label]) => `<option value="${value}" ${this._historyConfirmed === value ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></label><label>${esc(this._t("history.source_epoch_filter"))}<select data-history-source-epoch><option value="all">${esc(this._t("history.all_known_epochs"))}</option>${epochs.filter(item => item.source_epoch != null).map(item => `<option value="${item.source_epoch}" ${this._historySourceEpoch === String(item.source_epoch) ? "selected" : ""}>${esc(this._t("history.epoch_option", {source: item.source_id || this._t("common.unknown"), epoch: item.source_epoch, count: item.count}))}</option>`).join("")}</select></label><button data-history-apply>${esc(this._t("history.apply_filters"))}</button></div><p class="chart-key">${esc(this._t("history.epoch_help"))}</p></section>`;
    if (!data) return `${controls}<section class="card">${esc(this._t(this._historyPageLoading ? "history.loading" : "history.select_range"))}</section>`;
    const summary = data.summary || {};
    const storage = data.storage || {};
    const missing = summary.missing_count == null ? this._t("history.missing_filtered") : summary.missing_count;
    const quality = Object.entries(summary.quality_distribution || {}).map(([name,count]) => `${esc(name)}: ${count}`).join(" · ") || "No archived rows";
    const provenance = Object.entries(summary.provenance_distribution || {}).map(([name,count]) => `${esc(name)}: ${count}`).join(" · ") || "No archived rows";
    const report = this._historyQuarterReport(data);
    return `${controls}<section class="card"><div class="herohead"><div><p class="eyebrow">PERMANENT 15-MINUTE ARCHIVE</p><h2>HISTORY</h2><p>${esc(this._t("history.scope"))}</p></div><strong class="count">${summary.total ?? 0}</strong></div><div class="grid">${this._metric("Overall range archived quarters", summary.total ?? 0)}${this._metric("Matching filtered quarters", data.pagination.total ?? 0)}${this._metric("Oldest archived quarter", summary.oldest ? localQuarterLabel(summary.oldest) : "—")}${this._metric("Newest archived quarter", summary.newest ? localQuarterLabel(summary.newest) : "—")}${this._metric("Valid completed quarters", summary.valid_count ?? 0)}${this._metric("Incomplete / unavailable", summary.incomplete_count ?? 0)}${this._metric("Missing expected intervals", missing)}${this._metric("Valid imported energy", fmt(summary.import_kwh,3), "kWh")}${this._metric("Valid exported energy", fmt(summary.export_kwh,3), "kWh")}${this._metric("Partial observed import", fmt(summary.partial_import_kwh,3), "kWh")}${this._metric("Archive schema", storage.schema_version)}${this._metric("Database size", storage.size_bytes == null ? "—" : fmt(storage.size_bytes / 1048576,2), "MiB")}${this._metric("Retention", storage.retention || "Unknown")}</div><p class="chart-key">Quality: ${quality}</p><p class="chart-key">Provenance: ${provenance}</p>${report}<div class="pagination"><button data-history-page="${data.pagination.page - 1}" ${data.pagination.page <= 1 ? "disabled" : ""}>${esc(this._t("common.previous"))}</button><span>${esc(this._t("history.page", {page: data.pagination.page, pages: Math.max(1,data.pagination.pages), count: data.pagination.total}))}</span><button data-history-page="${data.pagination.page + 1}" ${data.pagination.page >= data.pagination.pages ? "disabled" : ""}>${esc(this._t("common.next"))}</button></div><p class="safety">${esc(this._t("history.no_fabricated_curve"))}</p></section>`;
  }

  _historyAuditPanel() {
    const audit = this._historyAudit;
    const candidates = audit?.candidates?.length
      ? `<table><thead><tr><th>Quarter (UTC)</th><th>Decision</th><th>Existing → proposed quality</th><th>Coverage</th><th>Import difference</th><th>Contractual status</th></tr></thead><tbody>${audit.candidates.map(item => `<tr><td><code>${esc(item.start_utc)}</code></td><td>${esc(item.action)}</td><td>${esc(item.existing_quality || "missing")} → ${esc(item.proposed_quality)}</td><td>${fmt(item.existing_coverage_seconds,0)} → ${fmt(item.proposed_coverage_seconds,0)} s</td><td>${fmt(item.import_difference_kwh,4)} kWh</td><td>${esc(item.contractual_status)}</td></tr>`).join("")}</tbody></table>`
      : "";
    const result = audit
      ? `<div class="grid">${this._metric("Candidates", audit.summary.candidate_count)}${this._metric("Missing inserts", audit.summary.insert_count)}${this._metric("Quality improvements", audit.summary.improve_count)}${this._metric("Protected / skipped", audit.summary.skip_count)}${this._metric("Contractually unconfirmed", audit.summary.contractually_unconfirmed_count)}</div>${candidates}${audit.candidates_truncated ? `<p class="notice">${esc(this._t("audit.preview_limited"))}</p>` : ""}<p class="safety">${esc(this._t("audit.safety"))}</p><label class="row"><input data-recorder-confirm type="checkbox"> ${esc(this._t("audit.confirm"))}</label><button data-recorder-apply>${esc(this._t("audit.apply"))}</button>`
      : "";
    return `<section class="selected-quarter" data-history-audit-panel><h3>Home Assistant Recorder audit</h3><p>${esc(this._t("audit.description"))}</p><button data-recorder-audit ${this._historyAuditLoading ? "disabled" : ""}>${esc(this._t(this._historyAuditLoading ? "audit.loading" : "audit.start"))}</button>${this._historyAuditError ? `<p class="error">${esc(this._historyAuditError)}</p>` : ""}${result}</section>`;
  }

  _tariffStatusView() {
    const status = this._tariffStatus;
    if (!status) return "";
    return `<section class="card"><h2>Tariff-rule status</h2><div class="grid">${this._metric("Installed integration", status.integration_version)}${this._metric("Applied rule", status.current_rule_version || "Unavailable")}${this._metric("Rule status", status.current_status)}${this._metric("Official coverage ends", status.official_coverage_end || "Unknown")}${this._metric("Update", status.update_recommended ? "Recommended" : "Not currently required")}</div><table><thead><tr><th>Year</th><th>Version</th><th>Status</th><th>Enabled by policy</th><th>Source</th></tr></thead><tbody>${(status.years || []).map(rule => `<tr><td>${rule.year}</td><td>${esc(rule.version)}</td><td>${esc(rule.status)}</td><td>${rule.enabled ? "Yes" : "No"}</td><td><a href="${esc(rule.source_url)}" target="_blank" rel="noreferrer">URO</a></td></tr>`).join("")}</tbody></table><p class="safety">Rule metadata is bundled and works offline. Downloaded or unreviewed rules never become effective automatically.</p></section>`;
  }

  _calendarView() {
    if (this._calendarError) return `<section class="card error"><h2>${esc(this._t("error.calendar_unavailable"))}</h2><p>${esc(this._calendarError)}</p><button data-retry-calendar>${esc(this._t("common.retry"))}</button></section>`;
    const calendar = this._calendar;
    if (!calendar) return `<section class="card">${esc(this._t("error.calendar_loading"))}</section>`;
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

  async _movePeriod(direction) {
    const moved = adjacentPeriodAnchor(
      (this._period || this._blocks || this._exceedances)?.period, direction,
    );
    if (!moved) return;
    this._periodAnchor = moved.anchor;
    this._resetAnalysisScroll();
    this._selectedDate = /^\d{4}-\d{2}-\d{2}$/.test(moved.anchor)
      ? moved.anchor : localDate(new Date(moved.anchor));
    if (moved.customStart) this._customStart = moved.customStart;
    if (moved.customEnd) this._customEnd = moved.customEnd;
    this._period = null;
    this._blocks = null;
    this._exceedances = null;
    await this._loadTab();
  }

  async _drillPeriod(index) {
    const action = periodDrillDown(
      this._periodType,
      this._period?.bins?.[index],
      this._period?.period?.resolution,
    );
    if (!action) return;
    if (action.quarterStartUtc) {
      this._tab = "today";
      this._selectedDate = localDate(new Date(action.quarterStartUtc));
      this._selectedTodayQuarterUtc = action.quarterStartUtc;
      this._day = null;
      this._render();
      await this._loadTab();
      return;
    }
    this._periodType = action.periodType;
    this._periodAnchor = action.anchor;
    this._selectedDate = action.anchor.slice(0, 10);
    this._period = null;
    this._render();
    await this._loadTab();
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
      if (this._historicalStart) this._quarter(this._historicalStart, {force: true});
    });
    root.querySelector("[data-retry-day]")?.addEventListener("click", () => this._loadTab());
    root.querySelector("[data-retry-calendar]")?.addEventListener("click", () => this._loadTab());
    root.querySelector("[data-retry-period]")?.addEventListener("click", () => this._loadTab());
    root.querySelector("[data-period-type]")?.addEventListener("change", event => {
      this._resetAnalysisScroll();
      this._periodType = event.target.value;
      this._periodAnchor = this._periodType === "hour"
        ? new Date().toISOString() : this._selectedDate;
      this._period = null;
      this._blocks = null;
      this._exceedances = null;
      this._render();
      this._loadTab();
    });
    root.querySelector("[data-period-block]")?.addEventListener("change", event => {
      this._resetAnalysisScroll();
      this._periodBlock = event.target.value;
      this._period = null;
      this._blocks = null;
      this._exceedances = null;
      this._exceedancePage = 1;
      this._render();
      this._loadTab();
    });
    root.querySelectorAll("[data-period-move]").forEach(element => {
      element.addEventListener("click", () => {
        this._movePeriod(Number(element.dataset.periodMove));
      });
    });
    root.querySelector("[data-period-current]")?.addEventListener("click", () => {
      this._resetAnalysisScroll();
      this._selectedDate = localDate();
      this._periodAnchor = new Date().toISOString();
      if (this._periodType === "custom") {
        this._customStart = this._selectedDate;
        this._customEnd = this._selectedDate;
      }
      this._period = null;
      this._blocks = null;
      this._exceedances = null;
      this._render();
      this._loadTab();
    });
    for (const field of ["start", "end"]) {
      root.querySelector(`[data-custom-${field}]`)?.addEventListener("change", event => {
        this._resetAnalysisScroll();
        if (field === "start") this._customStart = event.target.value;
        else this._customEnd = event.target.value;
        this._periodAnchor = this._customStart;
        this._period = null;
        this._blocks = null;
        this._exceedances = null;
        this._loadTab();
      });
    }
    root.querySelectorAll("[data-block]").forEach(element => {
      const activate = () => {
        this._periodBlock = String(element.dataset.block);
        this._blocks = null;
        this._render();
        this._loadTab();
      };
      element.addEventListener("click", activate);
      element.addEventListener("keydown", event => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          activate();
        }
      });
    });
    root.querySelector("[data-open-exceedances]")?.addEventListener("click", () => {
      this._tab = "exceedances";
      this._exceedancePage = 1;
      this._exceedances = null;
      this._render();
      this._loadTab();
    });
    for (const field of ["sort", "direction"]) {
      root.querySelector(`[data-exceedance-${field}]`)?.addEventListener("change", event => {
        if (field === "sort") this._exceedanceSort = event.target.value;
        else this._exceedanceDirection = event.target.value;
        this._exceedancePage = 1;
        this._exceedances = null;
        this._loadTab();
      });
    }
    root.querySelectorAll("[data-exceedance-page]").forEach(element => {
      element.addEventListener("click", () => {
        this._exceedancePage = Number(element.dataset.exceedancePage);
        this._exceedances = null;
        this._loadTab();
      });
    });
    root.querySelectorAll("[data-exceedance-quarter],[data-block-quarter]").forEach(element => {
      const start = element.dataset.exceedanceQuarter || element.dataset.blockQuarter;
      const activate = () => {
        this._tab = "today";
        this._selectedDate = localDate(new Date(start));
        this._selectedTodayQuarterUtc = start;
        this._day = null;
        this._render();
        this._loadTab();
      };
      element.addEventListener("click", activate);
      element.addEventListener("keydown", event => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          activate();
        }
      });
    });
    root.querySelector("[data-history-apply]")?.addEventListener("click", () => {
      this._historyStartDate = root.querySelector("[data-history-start]")?.value || this._historyStartDate;
      this._historyEndDate = root.querySelector("[data-history-end]")?.value || this._historyEndDate;
      this._historyBlock = root.querySelector("[data-history-block]")?.value || "all";
      this._historyQuality = root.querySelector("[data-history-quality]")?.value || "all";
      this._historyConfirmed = root.querySelector("[data-history-confirmed]")?.value || "all";
      this._historySourceEpoch = root.querySelector("[data-history-source-epoch]")?.value || "all";
      this._historySort = root.querySelector("[data-history-sort]")?.value || "start_utc";
      this._historyDirection = root.querySelector("[data-history-direction]")?.value || "desc";
      if (this._historyBlock !== "all") {
        this._historySort = "start_utc";
        this._historyDirection = "desc";
      }
      this._historyPageNumber = 1;
      this._historyPage = null;
      this._historyAudit = null;
      this._historyAuditError = null;
      this._loadTab();
    });
    root.querySelector("[data-open-history]")?.addEventListener("click", () => {
      const period = (this._period || this._blocks || this._exceedances)?.period;
      this._historyStartDate = period?.start_local?.slice(0, 10) || this._selectedDate;
      this._historyEndDate = period?.end_utc
        ? localDate(new Date(new Date(period.end_utc).getTime() - 1))
        : this._selectedDate;
      this._historyPageNumber = 1;
      this._historyPage = null;
      this._tab = "history";
      this._render();
      this._loadTab();
    });
    root.querySelector("[data-history-retry]")?.addEventListener("click", () => this._loadTab());
    root.querySelector("[data-recorder-audit]")?.addEventListener("click", async () => {
      this._historyAuditLoading = true;
      this._historyAuditError = null;
      this._render();
      try {
        this._historyAudit = await this._call("recorder_audit", {
          start_date: this._historyStartDate,
          end_date: this._historyEndDate,
        });
      } catch (error) {
        this._historyAudit = null;
        this._historyAuditError = error?.message || String(error);
      } finally {
        this._historyAuditLoading = false;
        this._render();
      }
    });
    if (this._historyAudit?.candidates_truncated) {
      root.querySelector("[data-recorder-apply]")?.setAttribute("disabled", "");
    }
    root.querySelector("[data-recorder-apply]")?.addEventListener("click", async () => {
      if (!root.querySelector("[data-recorder-confirm]")?.checked
          || !this._historyAudit || this._historyAudit.candidates_truncated) return;
      this._historyAuditLoading = true;
      this._render();
      try {
        await this._call("recorder_reconstruct", {
          audit_token: this._historyAudit.audit_token,
          confirm: true,
        });
        this._historyAudit = null;
        this._historyPage = null;
        await this._loadTab();
      } catch (error) {
        this._historyAuditError = error?.message || String(error);
      } finally {
        this._historyAuditLoading = false;
        this._render();
      }
    });
    root.querySelectorAll("[data-history-page]").forEach(element => {
      element.addEventListener("click", () => {
        this._historyPageNumber = Number(element.dataset.historyPage);
        this._historyPage = null;
        this._loadTab();
      });
    });
    root.querySelectorAll("[data-history-quarter]").forEach(element => {
      const activate = () => {
        const start = element.dataset.historyQuarter;
        this._tab = "today";
        this._selectedDate = localDate(new Date(start));
        this._selectedTodayQuarterUtc = start;
        this._day = null;
        this._render();
        this._loadTab();
      };
      element.addEventListener("click", activate);
      element.addEventListener("keydown", event => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          activate();
        }
      });
    });
    root.querySelectorAll("[data-chart-mode]").forEach(element => {
      element.addEventListener("click", () => {
        this._periodChartMode = element.dataset.chartMode;
        this._render();
      });
    });
    root.querySelectorAll("[data-period-bin]").forEach(element => {
      const activate = () => this._drillPeriod(Number(element.dataset.periodBin));
      element.addEventListener("click", activate);
      element.addEventListener("keydown", event => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          activate();
        }
      });
    });
    root.querySelectorAll("g[data-quarter]").forEach(element => {
      element.onclick = () => this._selectTodayQuarter(element.dataset.quarter);
      element.onkeydown = event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this._selectTodayQuarter(element.dataset.quarter, true);
        }
      };
    });
    root.querySelector("[data-today-quarter]")?.addEventListener("change", event => {
      this._selectTodayQuarter(event.target.value);
    });
    root.querySelector("[data-today-prev]")?.addEventListener("click", () => {
      this._moveTodayQuarter(-1);
    });
    root.querySelector("[data-today-next]")?.addEventListener("click", () => {
      this._moveTodayQuarter(1);
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
    const todayChart = root.querySelector("[data-today-scroll]");
    if (todayChart) {
      todayChart.scrollLeft = this._todayScrollLeft || 0;
      todayChart.addEventListener("scroll", () => {
        this._todayScrollLeft = todayChart.scrollLeft;
      }, {passive: true});
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    const activeElement = this.shadowRoot.activeElement;
    const analysisKey = [
      "periodType", "periodBlock", "periodMove", "periodCurrent",
      "customStart", "customEnd", "chartMode", "exceedanceSort",
      "exceedanceDirection", "exceedancePage",
    ].find(key => activeElement?.dataset && key in activeElement.dataset);
    const focusState = activeElement?.dataset?.todayControl
      ? {type: "today-control", value: activeElement.dataset.todayControl}
      : activeElement?.dataset?.quarter
        ? {type: "quarter", value: activeElement.dataset.quarter}
        : activeElement?.dataset?.hour
          ? {type: "hour", value: activeElement.dataset.hour}
          : activeElement?.dataset?.block
            ? {type: "block", value: activeElement.dataset.block}
            : activeElement?.dataset?.exceedanceQuarter
              ? {type: "exceedance", value: activeElement.dataset.exceedanceQuarter}
              : analysisKey
                ? {type: "analysis", key: analysisKey, value: activeElement.dataset[analysisKey]}
                : null;
    const priorTimelineScroll = this.shadowRoot.querySelector(".timeline")?.scrollLeft;
    if (priorTimelineScroll != null) this._calendarScrollLeft = priorTimelineScroll;
    const priorTodayScroll = this.shadowRoot.querySelector("[data-today-scroll]")?.scrollLeft;
    if (priorTodayScroll != null) this._todayScrollLeft = priorTodayScroll;
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
    const tabs = ["overview", "today", "period", "blocks", "exceedances", "history", "calendar"];
    const content = !this._entries.length
      ? `<section class="card"><h2>${esc(this._t("setup.no_meter"))}</h2><p>${esc(this._t("setup.no_meter_help"))}</p></section>`
      : this._tab === "overview" ? this._overview()
        : this._tab === "today" ? this._today()
          : this._tab === "period" ? this._periodView()
            : this._tab === "blocks" ? this._blocksView()
              : this._tab === "exceedances" ? this._exceedancesView()
                : this._tab === "history" ? this._historyView()
                  : `${this._calendarView()}${this._tariffStatusView()}`;
    this.shadowRoot.innerHTML = `<style>${this._styles()}</style><style>${this._legendStyles()}</style><main><header><div class="brand"><span>SI</span><div><h1>SI Grid Monitor</h1><p>Import-only contractual demand intelligence</p></div></div><div class="meter"><small>Active meter</small>${this._entries.length > 1 ? `<select data-entry>${this._entries.map(entry => `<option value="${esc(entry.entry_id)}" ${entry.entry_id === this._entryId ? "selected" : ""}>${esc(entry.title)}</option>`).join("")}</select>` : `<strong>${esc(active?.title || "None")}</strong>`}</div></header><nav>${tabs.map(id => `<button data-tab="${id}" class="${this._tab === id ? "active" : ""}">${esc(this._t(`nav.${id}`))}</button>`).join("")}</nav>${this._error ? `<div class="error">${esc(this._t("error.connection", {message: this._error}))}</div>` : ""}${content}</main>`;
    if (this._tab === "history" && this._historyPage) {
      this.shadowRoot.querySelector("main > section.card:last-of-type")?.insertAdjacentHTML(
        "beforeend", this._historyAuditPanel(),
      );
    }
    if (this._tab === "history") {
      this.shadowRoot.querySelector(".history-controls")?.insertAdjacentHTML(
        "beforeend",
        `<label>Sort by<select data-history-sort>${[["start_utc", "Date"], ["import_kwh", "Imported energy"], ["import_demand_kw", "Import demand"], ["utilization_pct", "Utilization"], ["quality", "Quality"]].map(([value, label]) => `<option value="${value}" ${this._historySort === value ? "selected" : ""}>${label}</option>`).join("")}</select></label><label>Order<select data-history-direction><option value="desc" ${this._historyDirection === "desc" ? "selected" : ""}>Descending</option><option value="asc" ${this._historyDirection === "asc" ? "selected" : ""}>Ascending</option></select></label>`,
      );
    }
    if (["today", "period", "blocks", "exceedances"].includes(this._tab)) {
      this.shadowRoot.querySelector("main > section.card:last-of-type")?.insertAdjacentHTML(
        "beforeend", '<button data-open-history>Open this range in HISTORY</button>',
      );
    }
    localizeDashboard(this.shadowRoot, dashboardLanguage(this._hass));
    this._bind();
    restoreChartScrollState(
      this.shadowRoot, this._chartScrollPositions, chartView.focused,
    );
    const timeline = this.shadowRoot.querySelector(".timeline");
    if (timeline) timeline.scrollLeft = this._calendarScrollLeft || 0;
    const todayChart = this.shadowRoot.querySelector("[data-today-scroll]");
    if (todayChart) todayChart.scrollLeft = this._todayScrollLeft || 0;
    const focusTarget = focusState?.type === "today-control"
      ? this.shadowRoot.querySelector(`[data-today-control="${focusState.value}"]`)
      : focusState?.type === "quarter"
        ? [...this.shadowRoot.querySelectorAll("[data-quarter]")]
          .find(element => element.dataset.quarter === focusState.value)
        : focusState?.type === "hour"
          ? [...this.shadowRoot.querySelectorAll("[data-hour]")]
            .find(element => element.dataset.hour === focusState.value)
          : focusState?.type === "block"
            ? [...this.shadowRoot.querySelectorAll("[data-block]")]
              .find(element => element.dataset.block === focusState.value)
            : focusState?.type === "exceedance"
              ? [...this.shadowRoot.querySelectorAll("[data-exceedance-quarter]")]
                .find(element => element.dataset.exceedanceQuarter === focusState.value)
              : focusState?.type === "analysis"
                ? [...this.shadowRoot.querySelectorAll("button,select,input")]
                  .find(element => element.dataset[focusState.key] === focusState.value)
                : null;
    focusTarget?.focus({preventScroll: true});
    this._tick();
  }

  _legendStyles() {
    return `.legend-line{width:28px;height:6px;min-width:28px;background:none}.legend-line line{fill:none;stroke-width:3}.legend-line .import,.legend-line .energy-actual{stroke:${CHART_SERIES.import.color}}.legend-line .export{stroke:${CHART_SERIES.export.color}}.legend-line .smooth{stroke:${CHART_SERIES.smooth.color}}.legend-line .future{stroke:${CHART_SERIES.future.color};stroke-dasharray:${CHART_SERIES.future.dash}}.legend-line .energy-projection{stroke:${CHART_SERIES.energyProjection.color};stroke-dasharray:${CHART_SERIES.energyProjection.dash}}.legend-line .contract{stroke:${CHART_SERIES.contract.color};stroke-dasharray:${CHART_SERIES.contract.dash}}.legend-line .contract-safety{stroke:${CHART_SERIES.contractSafety.color};stroke-dasharray:${CHART_SERIES.contractSafety.dash}}.legend-line .simulation{stroke:${CHART_SERIES.simulation.color};stroke-dasharray:${CHART_SERIES.simulation.dash}}.legend-line .operational{stroke:${CHART_SERIES.operational.color};stroke-dasharray:${CHART_SERIES.operational.dash}}.quarter-hit-area{fill:transparent;pointer-events:all}.period-hit-area{fill:transparent;pointer-events:all}.quarter-selection{pointer-events:none}.period-controls{display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin-bottom:14px}.period-controls label{display:flex;flex-direction:column;font-size:.75rem;color:var(--secondary-text-color)}.chart-modes{flex-wrap:wrap;margin:12px 0}.chart-modes .active{border-color:var(--primary-color,#03a9f4);color:var(--primary-color,#03a9f4)}.average-bar{fill:${CHART_SERIES.smooth.color}}.coverage-bar{fill:#0891b2}.exceedance-bar{fill:#8b5cf6}.period-bin{cursor:pointer}.period-bin:focus{outline:none}.period-bin:focus .period-hit-area{stroke:var(--primary-color,#03a9f4);stroke-width:2}.period-bin.missing .period-hit-area,.period-bin.unavailable .period-hit-area{fill:#f59e0b18;stroke:#f59e0b;stroke-dasharray:3 3}.swatch.coverage{border-color:#0891b2}.swatch.exceedance{border-color:#8b5cf6}.swatch.missing{height:10px;border:1px dashed #f59e0b;background:#f59e0b18}.block-swatch{display:inline-block;width:20px;height:10px;border-radius:2px}.history-quarter-report{margin-top:18px}.history-axis,.history-chart-row{display:grid;grid-template-columns:minmax(190px,1.2fr) minmax(420px,4fr) minmax(110px,.8fr);gap:10px;align-items:center;min-width:760px}.history-axis{font-size:.72rem;color:var(--secondary-text-color);padding:0 10px}.history-axis>span:nth-child(2){display:flex;justify-content:space-between}.history-quarter-chart{max-height:620px;overflow:auto;overscroll-behavior:contain;border:1px solid var(--line);border-radius:9px}.history-chart-row{width:100%;border:0;border-bottom:1px solid var(--line);border-radius:0;text-align:left;min-height:52px;background:transparent}.history-chart-row:hover,.history-chart-row:focus{background:#0284c712;outline:2px solid var(--primary-color,#03a9f4);outline-offset:-2px}.history-chart-row span,.history-chart-row small{display:block}.history-bar{height:24px;position:relative;background:color-mix(in srgb,var(--card),var(--primary-text-color) 5%);overflow:hidden}.history-grid{position:absolute;inset-block:0;border-left:1px solid var(--divider-color,#d6d9de)}.history-demand{position:absolute;inset-block:4px;background:${CHART_SERIES.import.color};opacity:.85}.history-peak{position:absolute;inset-block:0;border-left:3px solid #b91c1c}.history-target{position:absolute;inset-block:0;border-left:3px dashed ${CHART_SERIES.contract.color}}.legend-marker{position:relative;display:inline-block;width:24px;height:12px;border-left:3px solid #b91c1c}.table-scroll{max-width:100%;overflow:auto}.history-table thead th{position:sticky;top:0;background:var(--card);z-index:1}`;
  }

  _styles() {
    return `:host{display:block;min-height:100%;font-family:var(--paper-font-body1_-_font-family,system-ui);background:var(--primary-background-color);color:var(--primary-text-color);--line:var(--divider-color,#d6d9de);--card:var(--card-background-color,#fff)}*{box-sizing:border-box}main{max-width:1450px;margin:auto;padding:18px;overflow-x:hidden}header,.row,.herohead,.direction,nav{display:flex;align-items:center;gap:12px}header{justify-content:space-between}.brand{display:flex;align-items:center;gap:12px}.brand>span{display:grid;place-items:center;width:48px;height:48px;border:4px solid #15803d;border-left-color:#e11d48;border-radius:50%;font-weight:800}.brand h1{margin:0;font-size:1.45rem}.brand p,.eyebrow,.meter small{margin:2px 0;color:var(--secondary-text-color);font-size:.78rem}.meter{display:flex;flex-direction:column;align-items:flex-end;gap:3px}nav{margin:18px 0;border-bottom:1px solid var(--line)}button,select,input{font:inherit;color:inherit;background:transparent;border:1px solid var(--line);border-radius:8px;padding:9px 12px;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}nav button{border:0;border-radius:0;font-weight:700}nav .active{border-bottom:3px solid var(--primary-color,#03a9f4);color:var(--primary-color,#03a9f4)}.card{background:var(--card);border-radius:14px;padding:18px;margin:14px 0;box-shadow:var(--ha-card-box-shadow,0 2px 8px #0002)}.herohead{justify-content:space-between}.hero h2{margin:4px 0}.count{font:700 2.2rem ui-monospace}.direction>div{flex:1;padding:14px;border-radius:10px}.import{background:#ef444418;color:#c62828}.export{background:#22c55e18;color:#15803d}.direction b{display:block;font-size:1.7rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px;margin:14px 0}.metric{padding:12px;background:color-mix(in srgb,var(--card),var(--primary-text-color) 5%);border-radius:9px}.metric span{display:block;color:var(--secondary-text-color);font-size:.78rem}.metric strong{font-size:1.2rem;overflow-wrap:anywhere}.metric small{font-size:.75rem}.metric.good{border-left:4px solid #16a34a}.metric.bad{border-left:4px solid #dc2626}.metric.accent{border-left:4px solid #0284c7}.notice,.empty,.error,.safety{padding:12px;border-radius:8px;background:#0284c715}.error{background:#f59e0b22}.safety{font-size:.85rem;background:#64748b18}svg{width:100%;height:auto;background:color-mix(in srgb,var(--card),var(--primary-text-color) 3%);border-radius:10px}svg .zero{stroke:var(--primary-text-color);stroke-width:1.8}.contractual-target,.energy-contractual-limit,.target-step{stroke:${CHART_SERIES.contract.color};stroke-width:2;stroke-dasharray:${CHART_SERIES.contract.dash}}.contractual-safety-target,.energy-contractual-safety-target{stroke:${CHART_SERIES.contractSafety.color};stroke-width:2;stroke-dasharray:${CHART_SERIES.contractSafety.dash}}.operational-target,.energy-operational-target{stroke:${CHART_SERIES.operational.color};stroke-width:2.4;stroke-dasharray:${CHART_SERIES.operational.dash}}.simulation-target,.energy-simulation-target{stroke:${CHART_SERIES.simulation.color};stroke-width:2;stroke-dasharray:${CHART_SERIES.simulation.dash}}.power-grid{stroke:var(--divider-color,#d6d9de);stroke-width:.7}.import-trace{fill:none;stroke:${CHART_SERIES.import.color};stroke-width:3}.export-trace{fill:none;stroke:${CHART_SERIES.export.color};stroke-width:3}.smoothed-trace{fill:none;stroke:${CHART_SERIES.smooth.color};stroke-width:2.5}.forecast-continuation{fill:none;stroke:${CHART_SERIES.future.color};stroke-width:2.5;stroke-dasharray:${CHART_SERIES.future.dash}}.energy-actual{fill:none;stroke:${CHART_SERIES.energyActual.color};stroke-width:3}.energy-projection{fill:none;stroke:${CHART_SERIES.energyProjection.color};stroke-width:2.5;stroke-dasharray:${CHART_SERIES.energyProjection.dash}}.energy-current{fill:${CHART_SERIES.energyActual.color};stroke:var(--card);stroke-width:2}.reference-label{paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round}svg text{fill:var(--secondary-text-color);font-size:12px}.transition-list>div{display:grid;grid-template-columns:1fr 1.4fr 1.2fr;padding:8px;border-bottom:1px solid var(--line)}.daychart{width:100%;max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain}.daychart svg{min-width:1000px}.gridline{stroke:var(--divider-color,#d6d9de);stroke-width:1}.import-bar{fill:#e5484d}.export-bar{fill:#2f9e67}.target-step{stroke:#e6a700}.projection{fill:#8b5cf6;stroke:var(--card);stroke-width:1.5}.exceeded{fill:none;stroke:#dc2626;stroke-width:2}.state{fill:transparent;stroke:#94a3b8;stroke-dasharray:3 3}.state.missing,.state.incomplete,.state.unavailable{fill:url(#hatch);stroke:#f59e0b}.state.upcoming{stroke-opacity:.35}.state.provisional_estimate{stroke:#8b5cf6;stroke-width:2}.quarter-selection{fill:none;stroke:var(--primary-color,#03a9f4);stroke-width:3}.axis-title{font-weight:700}.quarter-slot{cursor:pointer}.quarter-slot:focus{outline:none}.quarter-selector{display:grid;grid-template-columns:auto minmax(220px,1fr) auto;gap:8px;margin:12px 0}.chart-key{font-size:.78rem;color:var(--secondary-text-color);margin:8px 0}.selected-quarter{border:1px solid var(--line);padding:12px;border-radius:10px;margin-top:12px}table{width:100%;border-collapse:collapse;overflow:auto;display:block}th,td{padding:9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}.chip{display:inline-block;padding:4px 8px;border-radius:12px;color:white}.b1{background:${BLOCK_COLORS[1]}}.b2{background:${BLOCK_COLORS[2]}}.b3{background:${BLOCK_COLORS[3]}}.b4{background:${BLOCK_COLORS[4]}}.b5{background:${BLOCK_COLORS[5]}}.b0{background:#64748b}.timeline{display:flex;overflow-x:auto;gap:3px}.hour{min-width:72px;padding:10px 6px;color:white;display:flex;flex-direction:column;border-radius:7px;text-align:left;border:0}.hour.selected{outline:3px solid var(--primary-color,#03a9f4);outline-offset:-3px}.hour small{font-size:.67rem}.legend{display:flex;gap:8px;margin:15px 0}.chart-scroll{width:100%;max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain;-webkit-overflow-scrolling:touch}.chart-scroll svg{display:block;width:max(100%,1120px);min-width:1120px}.chart-legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:8px 0;font-size:.78rem;color:var(--secondary-text-color)}.chart-legend span{display:inline-flex;align-items:center;gap:6px}.swatch{display:inline-block;width:24px;height:0;border-top:3px solid}.swatch.import,.swatch.energy-actual{border-color:${CHART_SERIES.import.color}}.swatch.export{border-color:${CHART_SERIES.export.color}}.swatch.smooth{border-color:${CHART_SERIES.smooth.color}}.swatch.future{border-color:${CHART_SERIES.future.color};border-top-style:dashed}.swatch.energy-projection{border-color:${CHART_SERIES.energyProjection.color};border-top-style:dashed}.swatch.contract{border-color:${CHART_SERIES.contract.color};border-top-style:dashed}.swatch.contract-safety{border-color:${CHART_SERIES.contractSafety.color};border-top-style:dotted}.swatch.simulation{border-color:${CHART_SERIES.simulation.color};border-top-style:dashed}.swatch.operational{border-color:${CHART_SERIES.operational.color};border-top-style:dashed}.forecast-anchor{fill:var(--card);stroke:${CHART_SERIES.future.color};stroke-width:4}.time-label{font-size:12px}.axis-title{font-size:13px}@media(max-width:700px){main{padding:8px}.brand p{display:none}.herohead{align-items:flex-start}.count{font-size:1.6rem}.direction{flex-direction:column}.direction>div{width:100%}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.transition-list>div{grid-template-columns:1fr}.card{padding:12px}nav{overflow-x:auto}nav button{white-space:nowrap}.meter{max-width:45%}.reference-label{font-size:10px}.quarter-selector{grid-template-columns:1fr 1fr}.quarter-selector select{grid-column:1/-1;grid-row:1}.chart-legend{font-size:.78rem;gap:8px 12px}.chart-key{font-size:.78rem;line-height:1.4}.time-label{font-size:13px}.axis-title{font-size:14px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}`;
  }
}

customElements.define("si-grid-monitor-panel", SIGridMonitorPanel);
