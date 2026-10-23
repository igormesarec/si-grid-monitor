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

## Sedem zavihkov

**Overview:** trenutni interval, energija, moč, napovedi, varnostni opis. **Today:** pregled današnjih četrtin. **Period:** obdobja in primerjave. **Blocks:** analiza B1–B5. **Exceedances:** potrjene prekoračitve. **History:** arhiv 15-minutnih povzetkov. **Tariff Calendar:** razpored blokov in status pravil.

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
