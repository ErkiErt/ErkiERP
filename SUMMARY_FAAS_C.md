# Faas C — kokkuvõte: pakkimisjuhis tööjuhisesse

Töö tehtud harus `v1-pakkimine` (main jäi puutumata). Kõik testid läbivad:
`python -m unittest test_parandused` → **83 testi OK** (66 vana + 17 uut).

Muudatused on ehitatud olemasolevale Clean Architecture kihistusele
(`ui → application → domain`):

- **`domain/packing.py`** (uus) — puhas pakkimisloogika: kastikataloog,
  kastivalik, riba-pakkimise reeglid, poolik-euraaluse soovitus. Ei sõltu
  Streamlitist ega esitluskihist.
- **`application/packing_service.py`** (uus) — use-case kiht: võtab
  lõiketulemuse (`result`) ja tagastab pakkimisplaani.
- **`utils.py`** — uus `packing_instruction_lines(result)`, mis sõnastab plaani
  eestikeelseteks „Paki toodang" ridadeks (kasutab olemasolevat `dimension_text`
  ja `sec_to_minsec`).
- **`ui.py`** ja **`print_sheet.py`** — mõlemasse lisatud uus alajaotus
  **„Paki toodang"** tööjärjekorra järele. Kehtib nii täisplaadi kui jäägi
  harule (loogika on ühine, sest `packing_instruction_lines` töötab iga
  tulemuse peal).

**NB:** pakkimisaega/kulu EI lisatud kliendi „Pakkumise kokkuvõttesse" — see on
puhtalt sisemine tootmisjuhis. Hinnastuse loogikat (`quote_service`,
`build_price_summary`) ei muudetud.

## Kastikataloog (`domain/packing.py` → `BOX_CATALOG`)

Lainepapikastid struktureeritud konstantidena (`Box`: nimi, sisemõõt L×W×H mm,
hind KM-ga, arvutatav ruumala). Neid saab hõlpsasti muuta ilma mujal koodi
katki tegemata.

Hinnad on Exceli **"Kek +KM"** veerust (KM-ga €), vt hinnaeeldused allpool.

| Kast (mm) | Hind (€, Kek +KM) | Ruumala (l) |
|-----------|-------------------|-------------|
| 200×150×120 | 1.22 | 3.6 |
| 350×250×200 | 1.0248 | 17.5 |
| 360×250×250 | 1.0248 | 22.5 |
| 400×300×220 | 1.22 | 26.4 |
| 440×310×270 | 1.5738 (arvutatud) | 36.8 |
| 590×380×250 | 1.7812 | 56.1 |
| 590×380×400 | 2.1228 | 89.7 |

## „Paki toodang" sisu

1. Pakkimismeetodi soovitus + hinnanguline aeg (kasti- VÕI riba-loogika,
   olenevalt detaili mõõtudest).
2. Valitud pakendi hind eraldi ridadel: kastid (kogus × ühikuhind = rida),
   poolik euraalus (kui rakendub) või EUR-alus (riba-alusepakkimisel), ning
   selge **„Pakendi hind kokku"** rida. Pakkekile hinda andmestikus ei ole,
   seega kilepakkimise/kimpude puhul on pakendi hind kokku 0.00 €.
3. „Markeeri kleepsud — paigalda kinnitus-/markeeringuetiketid pakendile."
4. Kui lõikest jäi taaskasutatav jääk: „Jääk: [pikkus] × [laius] mm — märgi
   jäägile mõõt." (kasutab `result['largest_usable_offcut']`). Kui jääki ei
   jäänud, rida jäetakse ära.

**NB:** pakendi hind on SISEMINE tootmisjuhis — seda EI lisata kliendi
„Pakkumise kokkuvõttesse".

## Pakendi hinna arvutus

- **Kasti hind** = kasti "Kek +KM" ühikuhind × kastide arv.
- **Poolik euraalus** (4.00 €) lisatakse, kui valitud kast on üks kolmest
  suurimast (poolik-euraaluse soovitus).
- **EUR-alus / täisalus** (6.00 €) lisatakse, kui riba pakitakse alusele
  (pikkus >1020 mm loogika).
- **Pakendi hind kokku** = kastid/kile + alus/poolikalus (kui rakendub).

## Mahutavusarvutuse ülevaatus (matemaatiline korrektsus)

Kastivalik kasutab nüüd kahe piiri miinimumi, et arvutus ei ületaks reaalset
mahtu:
- **Ruumala-hinnang:** `(80% kasti sisemahust) / detaili ruumala` (tihe
  pakkimine + 20% turvavaru).
- **Mõõdupõhine ülempiir** (`dimensional_capacity`): parim telgjoondatud
  ruudustik üle detaili 6 orientatsiooni — füüsiline maksimum.
- **Mahutavus = max(1, min(ruumala, mõõdupõhine))**.

Näited testides: 100×100×50 mm → kasti 400×300×220 mahub 42 tk (ruumala piirab);
150×150×100 mm → sama kasti mahub 8 tk (mõõt piirab, ruumala annaks 9).

---

# EELDUSED JA LAHTISED TÄPSUSTUSED (vajavad kasutaja kinnitust)

Kõik alljärgnev on dokumenteeritud ka vastavates koodikommentaarides
(`domain/packing.py`). Palun kinnita või korrigeeri:

### 1. Kastide mahutavuse ligikaudsus (ruumala + turvavaru)
Täpne 3D-ladumisalgoritm ei kuulunud selle faasi ulatusse. Kasutame lihtsat
heuristikat:
- **Mõõdukontroll:** detail peab mahtuma kasti mistahes orientatsioonis (detaili
  3 külge sorteeritult ≤ kasti 3 sisemõõtu sorteeritult).
- **Mahutavus:** ruumala baasil — `kasutatav_maht / detaili_maht`, kus
  kasutatav maht on **80% kasti sisemahust** (vt turvavaru allpool).
- Kui detail mahub mõõtmeliselt, on mahutavus vähemalt 1 (isegi kui ruumala
  annaks 0, nt üksik paks detail).

### 2. Kasti sobitamise turvavaru = 20%
`BOX_PACKING_SAFETY_MARGIN = 0.20`. Spetsis lubatud vahemik oli 15–20%; valisin
konservatiivsema 20%, et ladumise ebaefektiivsust (õhuvahed, detailide jäik
kuju) mitte alahinnata. **Kui soovid 15%, muuda üht konstanti.**

### 3. Kasti 5 (440×310×270 kuni 320) kõrgus = 270 mm
Kõrgus on tegelikult 270–320 mm. Mahutavuse arvutuses kasutan turvalisemat
**270 mm**, et mahutavust mitte üle hinnata. Ruumalaks tuleb ~36.8 l (mitte
43.6 l).

### 4. Riba tuvastus = pikim külg ≥ 5× lühim külg
`STRIP_LENGTH_TO_WIDTH_RATIO = 5.0`. Lihtne mõõdupõhine heuristika, ilma keeruka
kujutuvastuseta (nagu spetsis lubatud). Alla selle suhte loetakse detail
kasti-loogika alla.

### 5. Alla-1000 mm ribade („lihtne pakkimine") aeg = 120 sek/ots
Reegel 1 (pikkus < 1000 mm JA laius < 20 mm JA väike kogus): ribad tõmmatakse
pakkekilega mõlemast otsast kokku, **alust ei kasutata**. Eraldi aega spetsis
ei antud → kasutasin sama loogikat kui reeglis 2 (**120 sek/ots, 2 otsa =
240 sek**). Väikese koguse piir ei olnud täpne → eeldasin **~20 tk**
(`STRIP_SIMPLE_MAX_COUNT = 20`).

### 6. 1020–1200 mm vahemik → alusepakkimine
Sellele vahemikule eraldi reeglit ei antud. Spetsi lubatud lihtsam lahendus:
**rakendan alusepakkimist (reegel 3) alates pikkusest >1020 mm**
(`STRIP_PALLET_MIN_LENGTH_MM = 1020.0`), mis katab ka 1020–1200 mm vahemiku.
Lineaarset interpoleerimist ei kasutatud.

### 7. Kimbu jagamine 600 mm kõrguse piirangu järgi
Reegel 2: kimp kuni 500 mm lai, kuni 600 mm kõrge (käsitsi tõstmise
ergonoomiline MAX kõrgus). Kimpude arv = `ceil(kogus / (ribasid_reas ×
ridasid))`, kus `ribasid_reas = 500 / riba_laius` ja `ridasid = 600 / paksus`.
Kui virn ületaks 600 mm, jaotub kogus automaatselt mitmeks kimbuks.

### 8. Alusepakkimise aeg = 10 sek
Reegel 3: alus on juba tootmiskoha juures → kiire. Tõlgendasin **10 sek ühe
aluse pakkimisoperatsiooni kohta**. Suure koguse korral lisab juhis tekstilise
märkuse ribade tiheda/korrastatud ladumise kohta (mitte täpset 3D-arvutust).
Aluste arvu eraldi ei arvuta (eeldan 1 alus / juhis).

### 9. Kasti täitmise (detaili sisestamise) aeg puudub
Spets andis ainult **kasti kokkupaneku aja: 30 sek/kast, üks kord kasti kohta**
(`BOX_ASSEMBLY_SEC = 30`). Detaili sisestamise aega ei antud, seega kasti
ajahinnang katab ainult kastide kokkupaneku (`30 sek × kastide arv`).

### 10. Poolik euraalus = kolm suurimat kasti
Kui valitud kast on üks kolmest suurimast ruumala järgi (**590×380×400,
590×380×250, 440×310×270**), lisatakse juhis „Soovitatav tuua poolik euraalus".
Riba-alusepakkimisel on „poolik euraalus" alati asjakohane (alus on niikuinii
kasutusel), kuid soovitusrida on seotud spetsi järgi kasti-valikuga.

### 11. Kastide hinnad = Exceli "Kek +KM" veerg
Kasutaja täpsustus: „kek nimelise rea hindadega" → kasutame "Kek +KM" veergu
(mitte Tehpacki). Väärtused: 200×150×120=1.22, 350×250×200=1.0248,
360×250×250=1.0248, 400×300×220=1.22, 590×380×250=1.7812, 590×380×400=2.1228 €.

### 12. Kasti 440×310×270/320 "Kek +KM" hind = ARVUTATUD 1.5738 €
Algandmestikus oli selle kasti "Kek +KM" lahter **TÜHI**. Arvutasime selle
olemasolevast "Kek" hinnast (1.29 €), korrutades sama KM-teguriga, mis kehtib
teistel ridadel (Kek+KM / Kek ≈ 1.22, st ~22% KM): **1.29 × 1.22 ≈ 1.5738 €**.
See on eeldus — palun kinnita tegelik "Kek +KM" hind, kui see on teada.

### 13. Aluse hinnad: täisalus (EUR-alus) 6.00 €, poolik euraalus 4.00 €
`FULL_PALLET_PRICE_EUR = 6.00`, `HALF_PALLET_PRICE_EUR = 4.00`. Täisalus
lisatakse riba-alusepakkimisel (>1020 mm), poolik euraalus kolme suurima kasti
soovituse korral.

### 14. Pakkekile hinda ei ole → kilepakkimine 0.00 €
Pakkekile/kilelindi hinda andmestikus ei antud, seega lihtsa pakkimise ja
kimpude „Pakendi hind kokku" on 0.00 € (arvestame ainult teadaolevaid pakendi
hindu: kastid ja alused). Kui kile hind on teada, saab selle lisada.

### 15. Mahutavus = min(ruumala-hinnang, mõõdupõhine ülempiir)
Ruumala-hinnang võib üksi üle hinnata (nt paks detail, mida ei saa lõputult
virnastada). Lisasime mõõdupõhise ülempiiri (`dimensional_capacity`), et
mahutavus jääks füüsiliselt korrektseks. Endised eeldused (turvavaru 20% jne)
kehtivad edasi.

### 16. „Jääk" rida kasutab `largest_usable_offcut`
„Paki toodang" jäägirida kasutab olemasolevat domeeni välja
`result['largest_usable_offcut']` (taaskasutatav jääk, mis niikuinii riiulisse
läheb). Kui soovid, et rida ilmuks ka mitte-taaskasutatava jäägi korral, tuleb
väli vahetada `largest_any_offcut` vastu.

### 17. Kasti max pikkuse reegel: detail, mis ei mahu ühtegi kasti → alati riba
Kasutaja täpsustus: „ribad kasti ei lähe, kui need ei ole kasti max pikkusega
sobivad." Kui detaili pikim mõõt ületab kataloogi suurima kasti pikima
sisemõõdu, ei mahu detail ühtegi kasti → rakendub **alati** riba-loogika
(pikkuse-põhised reeglid), sõltumata pikkuse/laiuse suhtest
(`STRIP_LENGTH_TO_WIDTH_RATIO` heuristikast).

- **Läviväärtus arvutatakse dünaamiliselt** funktsiooniga
  `catalog_max_box_dimension_mm()` (praeguses `BOX_CATALOG`-is 590 mm), MITTE
  hardcode'itud — kataloogi muutmisel kohandub reegel automaatselt.
- `build_packing_plan` kontrollib: `too_long_for_any_box = longest_side >
  catalog_max_box_dimension_mm()`. Kui `is_strip(...)` VÕI `too_long_for_any_box`,
  siis kasutatakse `select_strip_packing`.
- Näide testis: detail 650 mm × 300 mm (suhe ≈2,17 < 5, seega ratio-heuristika
  üksi seda ribaks ei loeks) saab ikkagi riba-pakkimise soovituse, mitte kasti.

NB: varem langes selline detail juba `select_box` → `None` tagasiläbi
riba-loogikasse; see reegel muudab käitumise **selgesõnaliseks ja robustseks**
(ei sõltu kaudsest tagasilangemisest).
