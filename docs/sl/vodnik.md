# SI Grid Monitor — načini merjenja in razlaga

## Izbira vira

| Način | Podatek | Pomembna omejitev |
|---|---|---|
| **A** | En predznačen senzor moči omrežja W/kW | Preverite, ali pozitivno pomeni **odjem** ali **oddajo** |
| **B** | Ločen senzor moči odjema in oddaje W/kW | Senzorja morata prikazovati isto omrežno povezavo in dovolj usklajene čase |
| **C** | En nenegativen senzor moči odjema W/kW | Oddaja je **neznana**, ne izmerjena ničla |

V1.0 podpira samo A/B/C z živimi senzorji moči W/kW. Način D s kumulativnimi
števci Wh/kWh je bil poskusen v V0.9.5/V0.9.6 in v V1.0 ni izbira za novo
nastavitev.

## Osnovni izračuni

**Dovoljena energija v 15 minutah = dogovorjena moč × 0,25 h.**

Primer: **2,600 kW × 0,25 h = 0,650 kWh**. Če smo v celem intervalu uvozili **0,500 kWh**, je povprečna obračunska moč **2,000 kW**.

Intervalli se začnejo ob **:00, :15, :30 in :45**. Ne začnejo se ob trenutku namestitve integracije.

## Kaj pomenijo rezultati

- **CAN ADD THIS QUARTER**: ocena dodatnega stalnega odjema do konca trenutnih 15 minut.
- **MUST REDUCE THIS QUARTER**: ocenjena moč, ki bi jo bilo treba zmanjšati do konca intervala.
- **SUSTAINED CAN ADD**: previdnejša ocena za naslednjih 15/30/60/120 minut, ki vključuje prihodnje četrtine in njihove bloke, kadar so meritve dovolj popolne.
- **Incomplete / nepopolno**: manjkajo meritve ali rezultat ni dovolj potrjen.
- **Unknown / neznano**: vir te količine ne meri. Ne pomeni izmerjene vrednosti nič.

## Osem zavihkov

**Overview:** trenutni interval, energija, moč, napovedi, varnostni opis. **Today:** pregled današnjih četrtin. **Period:** obdobja in primerjave. **Blocks:** analiza B1–B5. **Exceedances:** potrjene prekoračitve. **History:** arhiv 15-minutnih povzetkov. **Contracts:** trenutne/prihodnje dodelitve, vrzeli, primerjava in revizijska sled. **Tariff Calendar:** razpored blokov, zgodovinska oziroma trenutno nastavljena ciljna vrednost in status pravil.

## Upravljanje pogodb

Datumski razponi so vključujoči in se ne smejo prekrivati. **Načrtuj
spremembo** ohrani prejšnji del dodelitve ter samodejno ustvari novo obdobje od
izbranega datuma. Z neobveznim končnim datumom nastane varna delitev na tri
dele. **Uredi podrobnosti** spreminja le izvor in datum evidence, **Popravi
dodelitev** je izrecen popravek datumov ali moči, **Odstrani** pa odstrani
dodelitev iz aktivnega razporeda po predogledu. Nobeno od teh dejanj ne spreminja
že arhiviranih meritev.

Ko pogodba manjka ali se izteka brez neposrednega naslednika, Home Assistant
prikaže stabilno opozorilo za izbrani merilnik. Naslednik, ki se začne naslednji
koledarski dan, opozorilo o izteku odpravi. Merjenje uvoza/oddaje se vedno
nadaljuje, vendar brez znane meje ni potrjene pogodbene prekoračitve.

Zavihek **Contracts** ločuje trenutni razpored, stare konfiguracijske posnetke,
nespremenljive cilje v arhiviranih četrtinah in uporabniške revizijske dogodke.
Starejši revizijski dogodki so dostopni po omejenih straneh. Posnetki iz časa
pred revizijskim sistemom niso prikazani kot izmišljeni dogodki uporabnika.
Skrbnik vidi en gumb **Odpri nastavitve integracije** in nato pri jasno imenovanem
izbranem merilniku izbere **Configure**.

Pri zgodovinskem koledarju pomeni **Kot zabeleženo** samo cilj, ki je dejansko
shranjen v arhivirani četrtini. Če je bil cilj shranjen kot neznan, ostane
neznan. Morebitna vrednost iz starega konfiguracijskega posnetka je prikazana
ločeno kot sklep iz zgodovinske konfiguracije, trenutni razpored pa kot tretja,
ločena primerjava.

## Nastavitve

Privzeto glajenje je **120 sekund**, časovno obzorje daljše napovedi **60 minut**, hramba arhiva **trajno**. Simulacija in uporaba začasnih pravil za 2028–2030 sta privzeto izklopljeni. Simulacijski prag ne spremeni uradnih pogodbenih omejitev, dokler simulacije ne omogočite; tudi takrat rezultati niso uradno potrjene prekoračitve.

## Omejitve in varnost

Vrednost **CAN ADD** se nanaša na matematično energijsko rezervo pri 15-minutnem obračunu. **Ni dovoljenje za večjo trenutno obremenitev** priključka, varovalk, faz, kablov ali inverterja.

## Nadgradnja starega načina D

V1.0 starega vnosa D ne zažene in ne razlaga Wh/kWh kot W/kW. Nastavitve,
kontrolna točka, obdobja vira in SQLite arhiv ostanejo ohranjeni. Home Assistant
prikaže opozorilo. Z dejanjem **Reconfigure** lahko isti vnos izrecno spremenite
na A/B/C; ID vnosa in arhivski prostor ostaneta enaka, nove meritve pa dobijo
novo obdobje vira. Če drug vnos že uporablja isti vir, je sprememba zavrnjena.

## Prihodnja funkcionalnost

Podpora kumulativnim števcem energije (samo odjem, predznačen neto števec ali
ločena števca odjema/oddaje) je rezervirana za prihodnje raziskave intervalov,
mej četrtin, ponastavitev, kvantizacije in obračunske natančnosti. Datum ponovne
uvedbe ni določen.

Več podrobnosti v [angleškem priročniku](../index.md), posebej [Troubleshooting](../troubleshooting.md) in [Data quality](../data-quality.md).
