# Erki Saagimise kalkulaator — kehtiv funktsionaalne kirjeldus

See dokument kirjeldab rakenduse praegust tööloogikat. Vanu vaheversioone ja enam mitte kehtivaid valikuid siin ei säilitata.

## Kasutusvoog

- Sisend algab valikust `Täisplaat` või `Jääk`.
- Täisplaadi korral valitakse materjaligrupp, materjal, paksus ja otse lõigatav plaadiformaat.
- Jäägi korral sisestatakse ühe füüsilise jäägi paksus, laius ja pikkus. Materjali kalkulaatoris eraldi ei valita, sest see liigub tootmisse Standard Booksi töökäsuga.
- Ühte sisestatud jääki ei korrata arvutuses automaatselt. Kui tellitud kogus sellesse ei mahu, kuvatakse jäägist saadav maksimaalne detailide arv.
- `Uus päring` puhastab sisendi ja tulemuse; varasemat päringut sisendisse ei eeltäideta.

## Materjalikataloog

- Valikud loetakse failist `plastmaterjalid_sae_app.csv`.
- Valikus on ainult täislehed, millel on usaldusväärne paksus ja formaat.
- Jäägiartikleid, rullmaterjali, vahtmaterjale, kummi, komposiite ja saagimiseks sobimatuid kõrvalartikleid ei kuvata.
- Õõnespaneeli grupis kuvatakse ainult Paneltimi PE-, PP- ja PP-C paneelid.
- Makroloni 2100 × 6000 mm kihtplastid ei kuulu täisplastlehtede valikusse.
- Praeguses versioonis kuvatakse arvutatava valikuna ainult formaadid, mille mõlemad küljed on kuni 3800 mm. Eellõiget vajavad pikad plaadid lisatakse tagasi siis, kui eellõige kuulub skeemi, lõigete arvu ja tööaja sisse.
- Materjalinimed on korrastatud praktilisteks gruppideks: kulumiskindel plast, konstruktsioonplast, fluoroplast, läbipaistev plast, eriotstarbelised plastid ja õõnespaneel.

## Masina- ja lõikereeglid

- Maksimaalne toetatud materjalipaksus on 95 mm.
- 5,6 mm lõikelaiust kasutatakse põhivalikuna; 3,1 mm lõikelaiuse suurim lubatud materjalipaksus ja kogu pakikõrgus on 25 mm. Õhukest ketast kasutatakse ainult siis, kui selle materjali- või ajavõit õigustab kettavahetust.
- Tasanduslõike varu on lõikelaius + 1 mm ja seda rakendatakse ainult tegelikult lõigataval teljel.
- Täispikka detailimõõtu ei lõigata ega vähendata tasandusvaru võrra.
- Minimaalne saega lõigatav riba on 4 mm. Alla 4 mm detail soovitatakse tellida freesist.
- 4–6 mm pikisuunaline riba eeldab vähemalt 2 mm materjalipaksust. Selle seadistus, ribastamine ja käsitlus arvestatakse 2× ajaga.
- Alates 80 mm materjalipaksusest arvestatakse seadistus, lõikamine ja käsitlus 2× ajaga. Kvaliteedikontrolli ning fikseeritud laastukotivahetuse aega selle teguriga ei korrutata.
- Käsitlusaeg on 20 sekundit valmis detaili kohta, kuid mitte vähem kui 90 sekundit kasutatud tooriku kohta. Operaator toob suure seeria puhul aluse või käru sae juurde ja tõstab detailid otse sellele; iga detailiga eraldi ei liiguta.

## Laastukottide vahetus

Lisatööaeg rakendub ainult vähemalt 2 m täispikkade ribade ribastamisel, kui ristlõikeid ei tehta.

- Alla 20 mm materjal: kotivahetuse lisaaega ei arvestata.
- 20–49,9 mm materjal: kuni 8 toorikut lisaaega ei ole; toorikute 9–16 korral lisandub 10 minutit, 17–24 korral 20 minutit jne.
- 50–95 mm materjal: iga kolme ribastatud tooriku kohta lisandub 10 minutit.
- Kotivahetuse aeg lisatakse põhitööajale pärast muude ajategurite rakendamist.

## Täpsuslõikus ±0,2 mm

- Täpsuslõikusele lisandub 30 minutit seadistusaega.
- Kuni 10 detaili ja alla 0,5 m² detaili korral on täpsuslõikuse hinnalisa 20 eurot.
- Kontrolliaeg on detaili pikema külje järgi 15, 25 või 35 sekundit.
- Kontrolliplaan: esimesed 25 kontrollühikut, kuni 100-ni iga 10., edasi iga 25. ning alati viimane kontrollühik.
- Koos lõigatud sama asukohaga ribasid kontrollitakse ühe ribapakina.

## Väljundid ja salvestamine

- Müügivaade näitab tellitud kogust, materjalivajadust, materjalikulu, tööaega ja tööraha.
- Tööraha arvutatakse fikseeritud hinnaga 60 eurot tunnis; tunnihinda eraldi ei kuvata.
- Hinnastusaeg sisaldab 5% arvestusvaru ning kogu tulemus ümardatakse järgmise 5 minuti täitumiseni. Eraldi minimaalset ajapuhvrit ei lisata. Operaatori arvutuslik tööaeg jääb muutmata.
- Sama materjali, mõõtude ja töörežiimi korral ei saa suurema detailikoguse koguhind olla väiksem kui ühegi väiksema koguse hind. Paigutuse või lõikelaiuse vahetusest tekkiv ajavõit jääb hinnasäästuks, kuid ei vii koguhinda tagasi.
- Ühe avaliku päringu ülempiir on 10 000 detaili, et ebarealistlik sisend ei koormaks hinnakalkulaatorit. Suurem seeria hinnatakse eraldi.
- Kuni 10 väikese detaili täppislõikuse 20 eurot on miinimumlisatasu. Kui 30 minuti täppisseadistus ja kvaliteedikontroll vajavad rohkem aega, ei kasutata 20 eurot hinnalaena.
- Lõikeleht sisaldab operaatori tööjärjekorda, materjali väljastust, kontrolliplaani ja lõikeskeemi. Müügihinda sellele ei lisata.
- Edukad päringud salvestatakse faili `data/arvutusparingud.csv`; lõpetatud tööd faili `data/saetoo_ajalugu.csv`.
- Vanema CSV-skeemi puuduvad veerud lisatakse laadimisel, et varasemad read jääksid loetavaks.
- Avalik režiim ei salvesta päringuid ning peidab töölogi ja ajaloo. Kohalik `KAIVITA_RAKENDUS.cmd` seab `ERKI_INTERNAL_MODE=1` ja avab sisemise töölogi.

## Käivitamine ja testitud keskkond

- Rakendus käivitatakse failiga `KAIVITA_RAKENDUS.cmd`.
- Soovitatud Python on 3.12.
- Lukustatud ja kontrollitud paketiversioonid on failis `requirements.txt`.

## Järgmised eraldi arendused

- eellõike optimeerija 4000–6000 mm plaatidele;
- Standard Booksi põhilaoseisu kirjutuskaitstud sidumine;
- mitme erineva jäägi ühine optimeerimine ja jäägiladu;
- jäägilao töövoog: enne täisplaati otsitakse sobiv jääk; kui jääki pole, eelistab lõikeskeem täisplaadi pikkuse säilitamist, töökäsul on nõutav materjalikulu ja alles jääv tükk ning tegelik erinevus saab pärast tööd parandatud;
- automaatne jäägiarvestus: arvutus lisab eeldatava jäägi andmebaasi, operaator saab eksimuse või teistsuguse tegeliku jäägi mõõdu hiljem kinnitada;
- mitme kasutaja veebiversioon ning turvaline keskne andmesalvestus.
