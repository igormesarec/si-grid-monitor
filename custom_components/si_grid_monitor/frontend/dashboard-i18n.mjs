/* Shared dashboard localization. Technical values, units and provenance stay unchanged. */
const SL = {
  "OVERVIEW": "PREGLED", "TODAY": "DANES", "PERIOD": "OBDOBJE",
  "BLOCKS": "BLOKI", "EXCEEDANCES": "PREKORAČITVE", "HISTORY": "ZGODOVINA",
  "TARIFF CALENDAR": "TARIFNI KOLEDAR", "Active meter": "Aktivni merilnik",
  "No configured meter": "Merilnik ni nastavljen",
  "Complete the SI Grid Monitor integration setup wizard first.": "Najprej dokončajte čarovnika za nastavitev integracije SI Grid Monitor.",
  "Previous": "Prejšnja", "Next": "Naslednja", "Today": "Danes", "Retry": "Poskusi znova",
  "From": "Od", "Through": "Do vključno", "Tariff block": "Časovni blok",
  "Data quality": "Kakovost podatkov", "Confirmed exceedance": "Potrjena prekoračitev",
  "Apply filters": "Uporabi filtre", "All": "Vse", "Yes": "Da", "No": "Ne",
  "Measured aligned": "Poravnano izmerjeno", "Counter derived": "Izvedeno iz števca",
  "Reconstructed": "Rekonstruirano", "Incomplete": "Nepopolno", "Unavailable": "Nedostopno",
  "PERMANENT 15-MINUTE ARCHIVE": "TRAJNI 15-MINUTNI ARHIV",
  "Oldest archived quarter": "Najstarejša arhivirana četrtina",
  "Newest archived quarter": "Najnovejša arhivirana četrtina",
  "Valid completed quarters": "Veljavne zaključene četrtine",
  "Incomplete / unavailable": "Nepopolne / nedostopne",
  "Missing expected intervals": "Manjkajoči pričakovani intervali",
  "Valid imported energy": "Veljavna uvožena energija",
  "Valid exported energy": "Veljavna izvožena energija",
  "Partial observed import": "Delno opažen uvoz", "Archive schema": "Shema arhiva",
  "Database size": "Velikost zbirke", "Retention": "Hramba",
  "Local quarter": "Lokalna četrtina", "UTC identity": "Identiteta UTC",
  "Block": "Blok", "Import / export": "Uvoz / izvoz",
  "Signed / import demand": "Podpisana / uvozna moč",
  "Target / utilization": "Meja / izkoriščenost", "Exceedance": "Prekoračitev",
  "Quality / coverage": "Kakovost / pokritost", "Source / epoch": "Vir / obdobje",
  "Tariff rule": "Tarifno pravilo", "Unknown": "Neznano", "Unconfirmed": "Nepotrjeno",
  "No archived quarters match these filters. Missing measurements are not displayed as zero energy.": "Nobena arhivirana četrtina ne ustreza filtrom. Manjkajoče meritve niso prikazane kot ničelna energija.",
  "Tariff calendar": "Tarifni koledar", "Working day": "Delovni dan",
  "Weekend": "Konec tedna", "Public holiday": "Praznik", "Higher season": "Višja sezona",
  "Lower season": "Nižja sezona", "Selected hour": "Izbrana ura",
  "Contracted target": "Dogovorjena meja", "Rule status": "Stanje pravila",
  "Rule version": "Različica pravila", "Season": "Sezona", "Day type": "Vrsta dneva",
  "Holiday": "Praznik", "None": "Brez", "UTC offset": "Odmik UTC", "DST fold": "Pregib DST",
  "Start (UTC)": "Začetek (UTC)", "Loading calendar…": "Nalaganje koledarja …",
  "Loading HISTORY…": "Nalaganje ZGODOVINE …", "HISTORY unavailable": "ZGODOVINA ni dostopna",
  "Connection error": "Napaka povezave", "The panel will retry automatically.": "Plošča bo samodejno poskusila znova.",
  "Current quarter": "Trenutna četrtina", "Current signed grid power": "Trenutna podpisana moč omrežja",
  "Import power": "Uvozna moč", "Export power": "Izvozna moč",
  "CAN ADD THIS QUARTER": "LAHKO DODATE V TEJ ČETRTINI",
  "MUST REDUCE THIS QUARTER": "MORATE ZMANJŠATI V TEJ ČETRTINI",
  "SUSTAINED CAN ADD": "TRAJNO LAHKO DODATE", "SUSTAINED MUST REDUCE": "TRAJNO MORATE ZMANJŠATI",
  "Forecast unavailable": "Napoved ni dostopna", "Current measurements unavailable": "Trenutne meritve niso dostopne",
  "Missing": "Manjka", "Upcoming": "Prihaja", "Live": "V ŽIVO", "In progress": "V TEKU",
  "Confirmed": "Potrjeno", "Provisional": "Začasno", "Simulation": "Simulacija",
  "Page": "Stran", "of": "od", "quarters": "četrtin", "Sort": "Razvrsti", "Order": "Vrstni red",
  "Date": "Datum", "Demand": "Moč", "Descending": "Padajoče", "Ascending": "Naraščajoče",
  "Hour": "Ura", "Day": "Dan", "Week": "Teden", "Month": "Mesec", "Year": "Leto",
  "Custom": "Po meri", "Current": "Trenutno", "Energy": "Energija", "Coverage": "Pokritost",
};

const EN_KEYS = {
  "nav.overview": "OVERVIEW",
  "nav.today": "TODAY",
  "nav.period": "PERIOD",
  "nav.blocks": "BLOCKS",
  "nav.exceedances": "EXCEEDANCES",
  "nav.history": "HISTORY",
  "nav.calendar": "TARIFF CALENDAR",
  "error.connection": "Connection error: {message}. The panel will retry automatically.",
  "error.live_loading": "Loading live meter…",
  "error.day_unavailable": "Daily history unavailable",
  "error.day_loading": "Loading day…",
  "error.period_unavailable": "Period history unavailable",
  "error.period_loading": "Loading historical period…",
  "error.blocks_unavailable": "Block analysis unavailable",
  "error.blocks_loading": "Loading tariff-block analysis…",
  "error.exceedances_unavailable": "Exceedance analysis unavailable",
  "error.exceedances_loading": "Loading confirmed exceedances…",
  "error.history_unavailable": "HISTORY unavailable",
  "error.calendar_unavailable": "Tariff calendar unavailable",
  "error.calendar_loading": "Loading calendar…",
  "setup.no_meter": "No configured meter",
  "setup.no_meter_help": "Complete the SI Grid Monitor integration setup wizard first.",
  "history.loading": "Loading HISTORY…",
  "history.select_range": "Select a range to inspect the archive.",
  "history.empty": "No archived quarters match these filters. Missing measurements are not displayed as zero energy.",
  "history.scope": "Summary metrics cover the entire selected date range before row filters. The table and matching count use the active filters.",
  "history.page": "Page {page} of {pages} · {count} matching quarters",
  "history.epoch_help": "The source-epoch filter includes only archived rows explicitly linked to that configuration epoch. Missing rows are not assigned an epoch.",
  "history.epoch_option": "{source} · epoch {epoch} ({count})",
  "history.missing_filtered": "Not classifiable with active filters",
  "audit.description": "Audit only reads detailed timestamped states. It never uses hourly long-term statistics or changes archive quarters.",
  "audit.loading": "Auditing…",
  "audit.start": "Audit selected range",
  "audit.confirm": "I reviewed the dry run and authorize reconstruction",
  "audit.apply": "Apply eligible improvements",
  "audit.preview_limited": "Candidate preview is limited to 1,000 rows. Narrow the date range before applying.",
  "audit.safety": "Review the dry run. Applying creates a consistent SQLite backup and revision trail first. This action cannot be undone from the dashboard.",
  "common.unknown": "Unknown",
  "common.retry": "Retry",
  "common.yes": "Yes",
  "common.no": "No",
  "common.previous": "Previous",
  "common.next": "Next",
};

const SL_KEYS = {
  "nav.overview": "PREGLED",
  "nav.today": "DANES",
  "nav.period": "OBDOBJE",
  "nav.blocks": "BLOKI",
  "nav.exceedances": "PREKORAČITVE",
  "nav.history": "ZGODOVINA",
  "nav.calendar": "TARIFNI KOLEDAR",
  "error.connection": "Napaka povezave: {message}. Plošča bo samodejno poskusila znova.",
  "error.live_loading": "Nalaganje merilnika v živo …",
  "error.day_unavailable": "Dnevna zgodovina ni dostopna",
  "error.day_loading": "Nalaganje dneva …",
  "error.period_unavailable": "Zgodovina obdobja ni dostopna",
  "error.period_loading": "Nalaganje zgodovinskega obdobja …",
  "error.blocks_unavailable": "Analiza blokov ni dostopna",
  "error.blocks_loading": "Nalaganje analize časovnih blokov …",
  "error.exceedances_unavailable": "Analiza prekoračitev ni dostopna",
  "error.exceedances_loading": "Nalaganje potrjenih prekoračitev …",
  "error.history_unavailable": "ZGODOVINA ni dostopna",
  "error.calendar_unavailable": "Tarifni koledar ni dostopen",
  "error.calendar_loading": "Nalaganje koledarja …",
  "setup.no_meter": "Merilnik ni nastavljen",
  "setup.no_meter_help": "Najprej dokončajte čarovnika za nastavitev integracije SI Grid Monitor.",
  "history.loading": "Nalaganje ZGODOVINE …",
  "history.select_range": "Izberite obdobje za pregled arhiva.",
  "history.empty": "Nobena arhivirana četrtina ne ustreza filtrom. Manjkajoče meritve niso prikazane kot ničelna energija.",
  "history.scope": "Povzetek zajema celotno izbrano časovno obdobje pred filtri vrstic. Tabela in število zadetkov upoštevata aktivne filtre.",
  "history.page": "Stran {page} od {pages} · {count} ustreznih četrtin",
  "history.epoch_help": "Filter obdobja konfiguracije vira vključuje samo arhivirane vrstice, ki so izrecno povezane s tem obdobjem. Manjkajočim vrsticam obdobje ni pripisano.",
  "history.epoch_option": "{source} · obdobje {epoch} ({count})",
  "history.missing_filtered": "Z aktivnimi filtri ni mogoče razvrstiti",
  "audit.description": "Pregled bere samo podrobna časovno označena stanja. Ne uporablja urnih dolgoročnih statistik in ne spreminja arhivskih četrtin.",
  "audit.loading": "Pregledovanje …",
  "audit.start": "Preglej izbrano obdobje",
  "audit.confirm": "Pregledal/-a sem suhi preizkus in dovoljujem rekonstrukcijo",
  "audit.apply": "Uporabi upravičene izboljšave",
  "audit.preview_limited": "Predogled je omejen na 1.000 vrstic. Pred uporabo zožite časovno obdobje.",
  "audit.safety": "Preglejte suhi preizkus. Uporaba najprej ustvari dosledno varnostno kopijo SQLite in revizijsko sled. Dejanja na nadzorni plošči ni mogoče razveljaviti.",
  "common.unknown": "Neznano",
  "common.retry": "Poskusi znova",
  "common.yes": "Da",
  "common.no": "Ne",
  "common.previous": "Prejšnja",
  "common.next": "Naslednja",
};

export function dashboardLanguage(hass) {
  return String(hass?.language || hass?.locale?.language || "en").toLowerCase().split("-")[0];
}

export function translateDashboard(key, language = "en", parameters = {}) {
  const catalog = language === "sl" ? SL_KEYS : EN_KEYS;
  const template = catalog[key] ?? EN_KEYS[key] ?? key;
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_match, name) =>
    Object.prototype.hasOwnProperty.call(parameters, name) ? String(parameters[name]) : `{${name}}`
  );
}

export function localizeDashboard(root, language) {
  if (!root) return;
  root.querySelectorAll("[data-i18n]").forEach(element => {
    element.textContent = translateDashboard(element.dataset.i18n, language);
  });
  root.querySelectorAll("[data-i18n-aria]").forEach(element => {
    element.setAttribute("aria-label", translateDashboard(element.dataset.i18nAria, language));
  });
  if (language !== "sl") return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const original = node.nodeValue;
    const trimmed = original.trim();
    if (!trimmed) continue;
    const translated = SL[trimmed];
    if (!translated) continue;
    node.nodeValue = original.replace(trimmed, translated);
  }
  root.querySelectorAll("[aria-label]").forEach(element => {
    const label = element.getAttribute("aria-label");
    if (SL[label]) element.setAttribute("aria-label", SL[label]);
  });
}

export const DASHBOARD_TRANSLATIONS = {en: EN_KEYS, sl: {...SL, ...SL_KEYS}};
