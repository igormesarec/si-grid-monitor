# SI Grid Monitor — načini merjenja in razlaga

## Izbira vira

| Način | Podatek | Pomembna omejitev |
|---|---|---|
| **A** | En predznačen senzor moči omrežja W/kW | Preverite, ali pozitivno pomeni **odjem** ali **oddajo** |
| **B** | Ločen senzor moči odjema in oddaje W/kW | Senzorja morata prikazovati isto omrežno povezavo in dovolj usklajene čase |
| **C** | En nenegativen senzor moči odjema W/kW | Oddaja je **neznana**, ne izmerjena ničla |
| **D** | En ali dva števca skupne energije Wh/kWh | Iz razlik izračuna povprečno moč preteklega intervala, ne trenutne moči |

Pri načinu **D** lahko izberete števec, ki narašča samo ob odjemu, en predznačen neto števec (ob odjemu narašča ali pada — izbirna smer), ali ločena števca odjema in oddaje. Neto števec ne more dokazati dejanske ločene uvožene energije, če se smer toka med meritvama spreminja.

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

Pri načinu D so med testiranjem V0.9.5 opazili kratkotrajno nerealno izpeljano moč približno **402 kW**. To je predmet nadaljnje preveritve; navodila napake ne odpravijo.

Več podrobnosti v [angleškem priročniku](../index.md), posebej [Troubleshooting](../troubleshooting.md) in [Data quality](../data-quality.md).