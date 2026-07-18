# Faas B — kokkuvõte: materjalivaliku kompaktsus + hinnasumma selgus

Töö tehtud harus `v1-parandused` (main jäi puutumata). Kõik testid läbivad:
`python -m unittest test_parandused` → **66 testi OK** (Faas A 62 + 4 uut).

Muudatused on ehitatud olemasolevale Clean Architecture kihistusele
(`ui → application → domain`). Uut äriloogikat ei lisatud otse `app.py`-sse:
hinnajaotuse loogika elab application-kihis (`application/quote_service.py`),
UI ainult kuvab selle. Lõikeleht (`print_sheet.py`), tööjärjekord
(`utils.py work_order_steps`) ja tööinfo arvutus (`build_best_result`/
`compute_quote`) jäid muutmata.

## Ülesanne 2 — Materjalivaliku kompaktsus

**Enne:** materjaligrupp valiti suurte kaartidega (`GROUP_CARD_CONTENT`, 6 kaarti
kõrgusega 205 px, kolmes tulbas), kus iga grupi kirjeldus ja näidismaterjalid
olid kogu aeg nähtaval. See võttis ekraanil väga palju ruumi.

**Nüüd:** materjalivalik on kompaktne mitmetasemeline valik ühes raamitud
konteineris:

- Üks tihe rida kolme selectbox'iga: **materjaligrupp → materjal → paksus**
  (`st.columns(3)`), all eraldi real **plaadiformaat**. Iga järgnev selectbox
  filtreerub eelmise põhjal ja on enne eelmise valikut keelatud.
- Grupi vahetus lähtestab allavoolu valikud (materjal, paksus, formaat) ja teeb
  vana arvutuse kehtetuks — uus `on_material_group_change` callback (varem tegi
  seda kaardinupp `choose_material_group`).
- Materjali **kirjeldused säilivad**, aga ei ole enam põhivaates kogu aeg
  nähtaval. Need on koondatud eraldi `st.expander`'isse „Materjali kirjeldus ja
  artiklid", mis kuvatakse **alles siis, kui materjal ja paksus on valitud**.
  Expander sisaldab grupi kirjeldust, grupi materjalide loetelu ning (kui formaat
  valitud) leitud artiklite värvi/variandi infot.

Andmestruktuuri (`materials.py` / `repositories/material_catalog.py`) ei muudetud
— tegemist oli ainult UI-kihi esitusmuudatusega.

## Ülesanne 3 — Pakkumise kokkuvõtte selgus

Lisatud pühas application-kihi funktsioon `build_price_summary(result)`, mis
jaotab hinna selgeteks eraldi väljadeks. UI (`ui.py render_sales_result`) kuvab
nüüd „Pakkumise kokkuvõttes" eraldi:

- **Tööraha (saagimine, ei sisalda materjali)** — põhitöö (saagimise) tasu.
- **Võimalikud lisatööd (täpsuslõikus)** — kuvatakse ainult siis, kui
  täpsuslõikus on valitud; väärtus on `precision_surcharge_eur`.
- **Materjali kogus (m²)** — kuvatakse materjali PINDALA koos märkega, et
  materjali €/m² hinda kalkulaator ei arvuta (vt allpool „Tööraha semantika").
- **Hind kokku (ilma materjalita)** — kogusumma; kui materjali hind oleks teada,
  muutuks pealdis „Hind kokku (sisaldab materjali)".

### „Tööraha" semantika — üheselt selge

Domeenikoodis (`domain/calculations.py`) on `work_fee_eur = billable_sec / 3600 ×
60 €/h` — see on **ainult saagimistöö (töö) tasu ega sisalda materjali
maksumust**. `material_cost_eur` on praegu 0, sest andmestikus
(`plastmaterjalid_sae_app.csv`) ei ole materjali €/m² hinnaveergu, ja
`total_estimated_cost_eur` = tööraha + materjal = tööraha.

Seetõttu:

- Pealdis ütleb otse **„Tööraha (saagimine, ei sisalda materjali)"**.
- Kokkusumma pealdis on **„Hind kokku (ilma materjalita)"**.
- Materjali all kuvatakse pindala (m²) ja märge: *„Materjali €/m² hinda
  kalkulaator ei arvuta — küsi materjali maksumus eraldi hinnapakkumisega."*

Nii ei jää kasutajale väärarusaama, nagu sisaldaks summa materjali kulu.

Täpsuslõikuse lisatasu (`precision_surcharge_eur`) on domeenis juba
`work_fee_eur` sees; `build_price_summary` eraldab selle omaette reaks nii, et
põhitööraha + lisatööd = kogu tööraha (topeltarvestust ei teki).

## Valideerimine

- `python -m unittest test_parandused` → **66 OK**.
- Uued testid:
  - `test_price_summary_separates_work_material_and_total` — tavatöös tööraha ==
    põhitööraha == kokku, materjal kuvatakse pindalana, kokku ei sisalda
    materjali (application-kiht, Streamlitit käivitamata).
  - `test_price_summary_shows_precision_extra_work_separately` — täpsuslõikus
    annab omaette positiivse lisatöö rea; põhitööraha + lisatöö = tööraha.
  - `test_summary_shows_separate_work_material_and_total` — UI näitab eraldi
    töö-, materjali- ja kokku-välju ning materjali märget.
  - `test_material_description_hidden_until_material_selected` — kirjelduse
    infosektsioon puudub enne materjali/paksuse valikut ja ilmub pärast.
- Olemasolevad lõikelehe ja tööjärjekorra testid läbivad muutumatult
  (`build_printable_cut_sheet`, `work_order_steps`).
