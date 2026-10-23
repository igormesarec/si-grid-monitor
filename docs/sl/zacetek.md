# SI Grid Monitor — hiter začetek

**SI Grid Monitor** je integracija za Home Assistant, ki spremlja **15-minutne intervale odjema elektrike iz omrežja** ter jih primerja z dogovorjeno obračunsko močjo po časovnih blokih **B1–B5**.

To je pripomoček za spremljanje in odločanje, **ne** uradni števec dobavitelja ali električna zaščitna naprava.

Dokumentacija opisuje predlagano različico **V1.0.0 RC**. Trenutno združena
različica je V0.9.6; V1.0 še ni objavljena kot stabilna izdaja.

## Namestitev

1. V **HACS → Custom repositories** dodajte `https://github.com/igormesarec/si-grid-monitor` kot *Integration*.
2. Namestite integracijo in **ponovno zaženite Home Assistant**.
3. Odprite **Nastavitve → Naprave in storitve → Dodaj integracijo → SI Grid Monitor**.
4. Vnesite ime merilnega mesta in izberite [način A, B ali C](vodnik.md) z živim senzorjem moči W/kW.
5. Nastavite dejanske pogodbene moči B1–B5 ter datume njihove veljavnosti.
6. V stranskem meniju odprite **SI Grid Monitor** in preverite prvi popolni 15-minutni interval.

## Najpomembnejše

- **Uvoz / odjem (import):** elektrika, ki jo prevzamemo iz javnega omrežja.
- **Oddaja (export):** elektrika, ki jo oddamo v omrežje. Oddaja v drugem delu intervala **ne izniči** prej prevzetega odjema.
- **Moč kW:** trenutna hitrost porabe energije ali izračunano povprečje.
- **Energija kWh:** količina prevzete/oddane energije.
- **Obračunska moč:** povprečna uvozna moč v točno določenem 15-minutnem intervalu.
- **CAN ADD:** ocenjena dodatna moč glede na obračunsko energijsko omejitev, **ne** dovoljena obremenitev varovalk, faz ali električnih vodnikov.

Če integracijo dodate ob 22:07, lahko interval 22:00–22:15 ostane **nepopoln**, ker manjkajo prve minute. Počakajte na celoten naslednji interval.

Način D s kumulativnimi števci Wh/kWh v V1.0 ni podprt. Stari arhivi iz
V0.9.5/V0.9.6 ostanejo shranjeni; ob nadgradnji se stari vnos ne zažene in ga
lahko izrecno prekonfigurirate na A/B/C brez brisanja baze.

Podrobneje: [Vodnik](vodnik.md) · [Angleška dokumentacija](../index.md) · [Izračuni](../calculations.md).
