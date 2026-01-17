# Slovar

Terminološki slovarji na enem mestu

## Podprti slovarji

- [DIS slovarček](https://dis-slovarcek.ijs.si/)
- [Slovar LTFE IKT](http://slovar.ltfe.org/)
- [Slovar Slovenskega društva za razpoznavanje vzorcev](https://slovar.vicos.si/)
- [Slovar IJS](https://www.ijs.si/cgi-bin/rac-slovar)
- [Islovar](http://islovar.org/islovar)
- [EZS Glosar](https://eglosar.si/)
- [Google Translate](https://translate.google.com/)
- [Repozitorij UL](https://repozitorij.uni-lj.si) (Iskanje bo vsebini objavljenih del v upanju, da je nekdo pred nami že našel dober prevod)
  - Vrne številke strani, na katerih se pojavi iskana beseda. Nato je potrebno ročno najti potencialen prevod
  - Trenutno vsebuje vsa objavljena gradiva (diplome, magistrske naloge, ...) za FRI, FE in FMF

## Zakaj?

![standards](https://imgs.xkcd.com/comics/standards.png)

[standards](https://xkcd.com/927)

## Lokalna uporaba (`slovar-web`)

- `config.toml` vsebuje konfiguracijo za lokalno (dev) uporabo

1. Poženi postgres

    ```bash
    docker compose up
    ```

2. Naloži knjižnice za slovar-web

    ```bash
    cd web
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3. Prižgi aplikacijo

    ```bash
    python app.py
    ```

4. Obišči [http://localhost:5000](http://localhost:5000)
