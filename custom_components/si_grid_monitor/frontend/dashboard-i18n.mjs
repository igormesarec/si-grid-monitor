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

export function dashboardLanguage(hass) {
  return String(hass?.language || hass?.locale?.language || "en").toLowerCase().split("-")[0];
}

export function localizeDashboard(root, language) {
  if (!root || language !== "sl") return;
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

export const DASHBOARD_TRANSLATIONS = {sl: SL};
