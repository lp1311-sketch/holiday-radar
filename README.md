# Holiday Radar

Javna, više-korisnička aplikacija: GitHub Pages poslužuje stranicu, Supabase čuva privatne pretplate, a GitHub Actions periodično pretražuje javne RSS izvore i šalje e-mail obavijesti. Posjetiteljima ne treba GitHub račun.

## Realna ograničenja

Worker koristi lokalizirane Google News RSS i Bing News RSS upite te dodatne javne feedove Travelzoo i Travel-Dealz za uredničke putne objave. To nisu inventari soba ni pouzdani feedovi rezervacijskih cijena. Sustav šalje **moguće tragove**, ne potvrđene ponude. Konačnu cijenu za sve putnike, raspoloživost, datume, poreze, obroke, udaljenost i uvjete treba provjeriti na izvornom linku. Destinacija/država, vrsta smještaja, prehrana i sadržaji ulaze u upit ili ocjenu teksta. Datumi boravka, broj gostiju, budžet, udaljenost, ocjene i otkazivanje samo su spremljeni kontekst — RSS ne omogućuje pouzdanu provjeru tih uvjeta pa ih sustav ne smije prikazivati kao zadovoljene. Ne postoji univerzalni besplatni izvor koji pokriva sve portale.

## Unaprijeđena obrada RSS-a

- Google News pretrage prilagođavaju jezik i izdanje odabranoj državi (do dvije lokalne varijante po pretplati); Bing RSS dobiva odgovarajuće parametre tržišta/jezika. Dodana je i engleska rezervna varijanta kad je korisna. Pridruženi su Travelzoo i Travel-Dealz javni urednički feedovi; dohvaćaju se jednom po pokretanju, a za pojedinog korisnika zadržavaju se samo stavke čiji naslov/opis spominje njegovu destinaciju i smještaj. Feedovi mogu biti nedostupni ili promijeniti format. Identični upiti keširaju se samo unutar jednog Actions pokretanja kako se RSS poslužitelji ne bi nepotrebno pozivali za korisnike s istim kriterijima.
- Parser čita RSS 2.0 i Atom, izdvaja naziv izdavača, njegovu web-stranicu i datum objave te deduplicira dio rezultata koji se pojave u oba feeda. Ako RSS metapodaci to dopuštaju, prednost dobiva izravna poveznica izdavača; Google News poveznica ostaje dostupna kao alternativni trag.
- Upiti traže novije članke, a RSS objave starije od 30 dana se preskaču (dobni prag je prag članka, ne rok važenja ponude). Objave bez datuma ostaju označene kao nepoznate, ne kao svježe. Na privremene HTTP greške i ograničenja zahtjeva worker pokušava ponovno uz kratko čekanje.
- E-mail prikazuje izdavača, datum, RSS kanal(e), spomenutu cijenu samo kao tekstualni trag i objašnjenje signala. Oznaka „jači/srednji/slab trag” opisuje količinu dostupnih pokazatelja (svježina, podudaranje destinacije, kontekst smještaja, izdavač), **ne** vjerodostojnost cijene ni potvrdu raspoloživosti.
- Cijena se ne može izračunati iz novinskog naslova. Čak i kad se iznos pronađe, može se odnositi na osobu, noć, staru promociju ili nešto drugo; poruka to zato nikad ne prikazuje kao ukupnu cijenu putovanja.

Google News RSS poveznice ponekad su posredničke i njihov izvorni članak nije pouzdano moguće rekonstruirati. Sustav ne pokušava krhko „dekodirati” takve linkove: čuva rezultat kakav je feed dao te, ako postoji, zasebno navodi izdavača i njegovu web-stranicu — uz upozorenje da to nije nužno izravni članak.

Javni feedovi koje worker dodatno pokušava dohvatiti: [Travelzoo feed](https://www.travelzoo.com/feed/) i [Travel-Dealz feed](https://travel-dealz.com/feed/). Njihova prisutnost u kodu ne jamči dostupnost, potpunost ni valjanost svake objave.

## Datoteke

- `index.html`, `styles.css`, `app.js`, `config.js` — zajednička web stranica i izmjenjivi filteri.
- `schema.sql` — privatne tablice, RLS i ograničenje učestalosti prijava.
- `supabase/functions/` — endpointi za prijavu, potvrdu, promjenu postavki i odjavu.
- `scripts/finder.py` — RSS pretraživanje, uklanjanje duplikata i slanje SMTP poruka.
- `.github/workflows/radar.yml` — raspored svakih šest sati i ručno pokretanje.

## 1. Supabase

Službeni CLI postupak: [Supabase Edge Functions quickstart](https://supabase.com/docs/guides/functions/quickstart).

1. Napravi Supabase projekt.
2. U SQL Editoru pokreni cijeli `schema.sql`.
3. U Project Settings → API uzmi Project URL i javni legacy `anon` JWT key.
4. Instaliraj Supabase CLI prema službenim uputama. U paketu je `supabase/config.toml`; iz korijena projekta prijavi se i poveži projekt s njegovim project refom.
5. Postavi tajnu `RATE_LIMIT_SECRET` za Edge Functions (duga nasumična vrijednost, najmanje 32 znaka), zatim objavi funkcije:

   ```bash
   supabase login
   supabase link --project-ref TVOJ_PROJECT_REF
   supabase secrets set RATE_LIMIT_SECRET='DUGA_NASUMICNA_VRIJEDNOST'
   supabase functions deploy subscribe
   supabase functions deploy confirm
   supabase functions deploy manage
   ```

Supabase URL i service-role ključ dostupni su funkcijama kao standardne Supabase varijable. Service-role ključ nikad ne stavljaj u javne datoteke.

## 2. Javna stranica

U `config.js` zamijeni `SUPABASE_URL` i `SUPABASE_ANON_KEY` stvarnim vrijednostima projekta. Anon ključ je predviđen za javni klijent; tablice su zaštićene RLS-om, a upis ide kroz Edge Functions. **Nikada ne stavljaj service-role ključ ili SMTP lozinku u `config.js`, HTML ili JavaScript.**

## 3. GitHub Pages

1. Napravi javni GitHub repozitorij i prenesi sadržaj ove mape u korijen grane `main`.
2. U Settings → Pages odaberi objavu iz grane `main`, mapa `/ (root)`.
3. Kopiraj HTTPS adresu objavljene stranice, uključujući putanju repozitorija, primjerice `https://korisnik.github.io/holiday-radar/`.

## 4. GitHub Actions Secrets

U Settings → Secrets and variables → Actions dodaj ove repository secrets:

| Naziv | Vrijednost |
|---|---|
| `SUPABASE_URL` | URL Supabase projekta |
| `SUPABASE_SERVICE_ROLE_KEY` | service-role/secret ključ — samo kao secret |
| `PUBLIC_SITE_URL` | puna HTTPS adresa GitHub Pages stranice |
| `MANAGE_TOKEN_SECRET` | duga, nasumična vrijednost; zadrži je nepromijenjenu kako bi privatne poveznice ostale valjane |
| `SMTP_HOST` | SMTP host, za web.de u pravilu `smtp.web.de` |
| `SMTP_PORT` | `587` za STARTTLS ili `465` za SMTP SSL |
| `SMTP_USER` | SMTP korisničko ime |
| `SMTP_PASSWORD` | SMTP/app lozinka koju pružatelj dopušta |
| `SMTP_FROM` | pošiljatelj, obično ista adresa kao `SMTP_USER` |

Nakon postavljanja Actionsa, workflow se može ručno pokrenuti preko Actions → Holiday Radar scan → Run workflow. Zakazano pokretanje je otprilike svakih šest sati; GitHub može odgoditi schedule, a kvote ovise o pravilima i računu.

## 5. Probni rad

1. Otvori web stranicu i unesi vlastitu adresu e-pošte i kriterije.
2. Prva potvrda može pričekati sljedeće pokretanje Actionsa.
3. Klikni potvrdu u e-mailu. Tek tada se pretplata aktivira.
4. Provjeri Actions logove ako slanje ili veza s bazom ne rade; skripta ne ispisuje adrese korisnika.

## Privatnost i sigurnost

- RLS je uključen, a javni anon klijent nema direktan pristup tablicama.
- Potvrdni i upravljački tokeni provjeravaju se preko SHA-256 sažetaka; upravljački token je deterministički HMAC potpisan tajnom pohranjenom u GitHub Secrets.
- E-mail se aktivira tek nakon potvrde; nepotvrđene pretplate uklanjaju se nakon 14 dana.
- SQL ograničava prijave na 5 po IP-u u 10 minuta i pohranjuje samo hash IP-a. Edge Function koristi `RATE_LIMIT_SECRET`.
- Service-role i SMTP podaci moraju ostati u GitHub Secrets/Supabase secrets.
- Prije javnog lansiranja dodaj politiku privatnosti, kontakt za zahtjeve brisanja i provjeri lokalne obveze zaštite osobnih podataka.

## Dodavanje izvora

U `scripts/finder.py` se Google/Bing RSS upiti definiraju u `feeds()`, a javni urednički feedovi u `PUBLIC_DEAL_FEEDS`. Novi javni feed dodaj u taj popis uz naziv i homepage izdavača. Provjeri licencu, kvotu i uvjete izvora. Nemoj dopuštati da korisnici unose proizvoljne URL-ove za dohvat: worker bi time mogao postati SSRF vektor. Nemoj zaobilaziti prijavu, paywall ili zaštite portala.

## Lokalna provjera

Uz Python i biblioteku `requests` pokreni:

```bash
python -m py_compile scripts/finder.py
python -m unittest discover -s tests -v
```

GitHub Actions priprema navedenu Python ovisnost pri svakom pokretanju.
