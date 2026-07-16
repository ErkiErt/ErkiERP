# Erki Saagimise kalkulaator

Streamliti rakendus plastlehtede saetöö kiireks pakkumiseks ning operaatori lõikelehe koostamiseks.

## Kohalik käivitamine

Windowsis käivita `KAIVITA_RAKENDUS.cmd`. Rakendus avaneb aadressil `http://localhost:8501`.

Käivitusfail seab siserežiimi, milles on nähtav töölogi ja kohalik ajalugu. Ilma keskkonnamuutujata `ERKI_INTERNAL_MODE=1` töötab rakendus avalik-turvalises režiimis: arvutamine ja lõikeleht on kasutatavad, kuid töölogi ega päringuid kettale ei salvestata.

## Kontroll

```powershell
python -m unittest -v test_parandused.py
```

Testid katavad muu hulgas kõik kasutajale nähtavad materjali-, paksuse- ja formaadivalikud, lõiketerade piirid, käsitlusaja, laastukottide vahetuse, täppislõikuse ning prinditava töökäsu.

## Streamlit Community Cloud

- Hoidla haru: `main`
- Rakenduse käivitusfail: `app.py`
- Soovitatud Python: `3.12`
- Vajalikud paketid: `requirements.txt`

Päringute ja tööde CSV-ajalugu luuakse jooksvalt kausta `data` ning seda ei lisata GitHubi. Avalikus Community Cloudi rakenduses on kohalik failisalvestus ajutine; püsiva mitme kasutaja tööajaloo jaoks tuleb lisada eraldi andmebaas.

Streamlit Community Cloudis ära määra `ERKI_INTERNAL_MODE=1`, kui rakendus on avalik. Nii ei kuvata ega salvestata avalike testijate töölogi.
