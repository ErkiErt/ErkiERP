# Faas A — kokkuvõte: veaparandus + arhitektuuri eraldamine

Töö tehtud harus `v1-parandused` (main jäi puutumata). Kõik testid läbivad:
`python -m unittest test_parandused` → **62 testi OK** (algne 50 + 12 uut).

## Ülesanne 1 — plaadi/jäägi valiku session_state viga

### Vea täpne kordusstsenaarium
Viga on tuvastatav nii:

1. Vali **Täisplaat** → materjaligrupp → materjal → paksus → plaadiformaat →
   sisesta detaili mõõdud ja kogus → vajuta **Arvuta pakkumine**. Tulemus
   (`best_result`) salvestub session_state'i ja kuvatakse.
2. Muuda nüüd **mõnda eelnevat valikusammu** — nt vali teine materjaligrupp,
   teine materjal, teine paksus või teine plaadiformaat.
3. **Viga:** vana pakkumine jäi ekraanile „ripakile" — nt kuvati endiselt PE500
   20 mm tulemust, kuigi kasutaja oli juba valinud teise grupi/paksuse. Arvutatud
   tulemus ei vastanud enam nähtaval olevale sisendile.

### Juurpõhjus
`app.py`-s tühjendas ainult `choose_stock_source` (täisplaat ↔ jääk vahetus)
varem arvutatud tulemuse. Grupi vahetus (`choose_material_group`) ega materjali/
paksuse/formaadi `selectbox`-id **ei teinud `best_result`-i kehtetuks**. Kuna
need vidinad on väljaspool `st.form`-i ja käivitavad kohese reruni, jäi vana
`best_result` alles ja kuvati uue sisendi taustal.

### Parandus (`app.py`)
- Lisatud abifunktsioon `invalidate_result()`, mis nullib `best_result` ja
  `last_query_id`.
- `choose_material_group` kutsub selle grupi tegelikul muutumisel.
- Kolmele materjalivaliku `selectbox`-ile (materjal, paksus, plaadiformaat)
  lisatud `on_change=invalidate_result`.

Nii muutub sõltuv tulemus automaatselt kehtetuks iga eelneva sammu muutmisel;
vana valik ei jää enam ripakile. Kogusest/mõõdust sõltuv ümberarvutus toimib
juba `st.form` kaudu (uus tulemus alles „Arvuta pakkumine" vajutusel).

### Uued regressioonitestid (`test_parandused.py`, klass `SelectionStateTests`)
Katab spetsis nõutud viis valikujärjestust + kehtetuks tegemise:
1. `test_sequence_1_material_thickness_plate_normal` — materjal → paksus → plaat.
2. `test_sequence_2_material_then_remnant` — jäägi valik laost.
3. `test_sequence_3_remnant_back_to_plate_clears_result` — jäägist loobumine
   tühjendab tulemuse ja mõõdud.
4. `test_sequence_4_changing_quantity_recomputes` — koguse muutmine arvutab ümber.
5. `test_sequence_5_changing_dimensions_recomputes` — mõõtude muutmine arvutab ümber.
6. `test_upstream_change_invalidates_stale_result` — grupi/materjali/paksuse/
   formaadi muutmine teeb tulemuse kehtetuks (subTest iga sammu kohta).

## Ülesanne 6+7 — arhitektuuri eraldamine (Clean Architecture)

Ümberkorraldus tehti ettevaatlikult, väikeste sammudena; iga sammu järel jooksid
kõik testid rohelisena. Avalike funktsioonide käitumist ei muudetud — vanad
tasapinnalised moodulid jäid alles **tagasiühilduvuse re-eksport-kihina**.

### Uus failistruktuur
```
domain/                     # puhas äriloogika, EI impordi streamlitit ega andmeallikat
  calculations.py           # kogu lõikegeomeetria, ajaarvutus, hinnastus, jäägiklassifikatsioon
                            # (endine core.py sisu muutumatuna)
application/                # use case'id (ui → application → domain)
  quote_service.py          # compute_quote(): parim lõikeplaan + hinnastuse alammäär + ketaste põhjendused
                            # single_stock_capacity(): jäägi mahutavus
repositories/               # andmejuurdepääs
  material_catalog.py       # materjalide CSV lugemine (endine materials.py)
  history_store.py          # ajaloo/päringute salvestus (endine history.py)
ui.py / print_sheet.py / utils.py   # esitus- ja Streamliti-lähedane kiht (säilinud)
app.py                      # Streamlit UI + session_state; kutsub application-teenust

# Tagasiühilduvuse re-eksport-kihid (et olemasolevad impordid/testid ei katkeks):
core.py       -> domain.calculations
materials.py  -> repositories.material_catalog
history.py    -> repositories.history_store
```

### Sõltuvussuund
`ui (app.py) → application (quote_service) → domain (calculations)`.
Domeen ei sõltu Streamlitist ega failiformaadist; andmelugemine on
repository-kihis. `app.py` kutsub arvutuse jaoks `compute_quote`, mitte enam
domeenifunktsioone otse.

### Uued kihi-testid (`test_parandused.py`, klass `ArchitectureLayerTests`)
- `test_domain_calculations_do_not_import_streamlit` — domeen ei too Streamlitit
  kaasa (kontrollitud eraldi protsessis).
- `test_domain_and_compat_core_expose_same_engine` — `core` re-ekspordib sama
  domeenifunktsiooni, mitte koopiat.
- `test_repositories_back_the_compat_material_module` — `materials` viitab
  repository funktsioonile ja kataloog laadub.
- `test_quote_service_computes_best_result_without_ui` — teenus arvutab tulemuse
  Streamlitit käivitamata.
- `test_quote_service_returns_none_when_detail_does_not_fit` — mittemahtuv detail.
- `test_quote_service_single_stock_capacity_matches_domain`.

## Ülesanne 5 — tugevad osad säilinud
- `build_printable_cut_sheet` (`print_sheet.py`) ja `work_order_steps`
  (`utils.py`) on muutumatud ja toimivad (kaetud olemasolevate + smoke-testiga).
- `build_best_result`/`build_orientation_result` arvutavad endiselt päris
  tööinfo ja lõikeskeemi, mitte hinnangut.
- Jäägisäästlik cross-first lõikestrateegia säilinud (`cut_strategy`).

## Valideerimine
- `python -m unittest test_parandused` → **62 OK**.
- Täisrakenduse smoke-test (täisplaat PE500 10 mm → arvuta → lõikeleht HTML):
  lõikeleht sisaldab SVG-skeemi ja tööjärjekorda, ilma eranditeta.
- Kontrollitud: `domain/`, `application/`, `repositories/` ei impordi Streamlitit.
