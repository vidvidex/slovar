from flask import Flask, request, render_template
from bs4 import BeautifulSoup
import requests
from dataclasses import dataclass
from googletrans import Translator
import asyncio
import re
from typing import Dict, Any
import tomllib
from pathlib import Path
import psycopg2

app = Flask(__name__)
loop = asyncio.get_event_loop()


config_path = Path(__file__).parent / "config.toml"
with config_path.open("rb") as f:
    config = tomllib.load(f)

DB_CONFIG = config["database"]
REQUEST_TIMEOUT = config["requests"]["timeout"]


@dataclass
class slovar_result:
    en: str
    sl: str


@dataclass
class repozitorij_result:
    naslov: str
    leto: int
    avtorji: list[str]
    organizacije: list[str]
    repozitorij_url: str
    datoteka_url: str
    stevilka_strani_skupaj: list[int]
    stevilka_strani_pdf: list[int]


def dis_slovarcek(query: str) -> list[slovar_result]:
    print("DIS Slovarček: ", query)

    response = requests.get(f"https://dis-slovarcek.ijs.si/search?search_query={query}", timeout=REQUEST_TIMEOUT)

    if response.status_code != 200:
        print(
            "Error accessing https://dis-slovarcek.ijs.si. Status code:",
            response.status_code,
        )
        return

    soup = BeautifulSoup(response.content, "html.parser")
    result_containers = soup.find_all(id="all-search-results")

    results = []
    for result_container in result_containers:
        result = result_container.find(class_="accordion")

        en = result.find(class_="search-result-left").text.strip()
        sl = result.find(class_="search-result-right").text.strip()

        results.append(slovar_result(en, sl))

    return results


def ltft(query: str) -> list[slovar_result]:
    print("LTFE: ", query)
    base_url = "http://slovar.ltfe.org/index/add"
    results = []

    def parse_results(full_url, source_lang):
        try:
            response = requests.get(full_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error accessing {full_url}: {e}")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        result_containers = soup.select(".wHead")

        for container in result_containers:
            try:
                if source_lang == "eng":
                    sl = container.select_one(".lang").get_text(strip=True)
                    en = container.contents[0].strip()
                else:
                    en = container.select_one(".lang").get_text(strip=True)
                    sl = container.contents[0].strip()

                results.append(slovar_result(en, sl))
            except Exception as e:
                print(f"Error parsing entry: {e}")

    parse_results(f"{base_url}/eng/?q={query}&type=all", source_lang="eng")
    parse_results(f"{base_url}/slo/?q={query}&type=all", source_lang="slo")

    return results


def sdrv(query: str) -> list[slovar_result]:
    print("SDRV: ", query)

    base_url = "https://slovar.vicos.si"

    session = requests.Session()

    # Get the CSRF token
    search_url = f"{base_url}/dictionary/search/"
    response = session.get(search_url, timeout=REQUEST_TIMEOUT)
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the CSRF token in the HTML
    csrf_token = soup.find("input", {"name": "csrfmiddlewaretoken"})["value"]

    # Prepare the data and headers for the POST request
    post_data = {"csrfmiddlewaretoken": csrf_token, "query": query}
    headers = {"Referer": search_url}

    # Send the POST request to search for the query
    search_response = session.post(search_url, data=post_data, headers=headers, timeout=REQUEST_TIMEOUT)
    if search_response.status_code != 200:
        print("Error accessing SDRV. Status code:", search_response.status_code)
        return []

    # Extract the list of terms from the search results
    soup = BeautifulSoup(search_response.text, "html.parser")
    h2s = soup.find_all("h2")  # Find all h2 elements

    # Najdi linke do vseh izrazov, ki jih vrne za naš query
    links = []
    for h2 in h2s:
        if h2.text.strip() == "Izrazi":  # Find the h2 with the text "Izrazi"
            ul = h2.find_next_sibling("ul")
            a_elements = ul.find_all("a")
            for link in a_elements:
                href = link.get("href")
                links.append(base_url + href)
            break

    # Za vsak link pošlji GET request in pridobi angleški in slovenski prevod
    results = []
    for link in links:
        response = requests.get(link, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            print("Error accessing SDRV term page. Status code:", response.status_code)
            continue
        soup = BeautifulSoup(response.text, "html.parser")

        en = soup.find("div", class_="phrase").get_text(strip=True)
        translations = soup.find_all("li", class_="translation")

        # Če je en od prevodov označen kot approved vrni le tega, drugače vrni vse
        approved_translations = [t for t in translations if "approved" in t["class"]]
        if approved_translations:
            sl = approved_translations[0].find("span", class_="name").get_text(strip=True)
            results.append(slovar_result(en, sl))
        else:
            for translation in translations:
                sl = translation.find("span", class_="name").get_text(strip=True)
                results.append(slovar_result(en, sl))
    return results


def ijs(query: str) -> list[slovar_result]:
    print("IJS: ", query)
    url = f"https://www.ijs.si/cgi-bin/rac-slovar?w={query}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT)

    if not response.ok:
        print(f"Error accessing {url}. Status code: {response.status_code}")
        return []

    # Na IJS ne znajo generirati pravilnega HTML-ja, zato ne moremo le uporabiti parserja od BeautifulSoup
    # Na srečo lahko parsamo HTML z regexom https://stackoverflow.com/a/1732454
    pattern = r"<dt>([^<]+)<dd>([^<]+)"
    pairs = re.findall(pattern, response.text)

    results = []
    for pair in pairs:
        en = pair[0].strip()
        sl = pair[1].strip()

        # Popravi šumnike
        sl = sl.replace('"c', "č")
        sl = sl.replace('"C', "Č")
        sl = sl.replace('"s', "š")
        sl = sl.replace('"S', "Š")
        sl = sl.replace('"z', "ž")
        sl = sl.replace('"Z', "Ž")

        results.append(slovar_result(en, sl))

    return results


def islovar(query: str) -> list[slovar_result]:
    print("islovar: ", query)

    url = f"http://islovar.org/islovar"
    post_data = {"SearchString": query, "id": "d661b6d7-6884-47a2-9f8b-a4070126395b"}
    response = requests.post(url, data=post_data, timeout=REQUEST_TIMEOUT)

    if not response.ok:
        print(f"Error accessing {url}. Status code: {response.status_code}")
        return []

    response_json = response.json()

    results = []
    for term in response_json:
        term = term["term"]
        sl = term["Name"]
        en = ", ".join([t["Name"] for t in term["Terms"]])

        results.append(slovar_result(en, sl))

    return results


def ezs_glosar(query: str) -> list[slovar_result]:
    print("EZS Glosar: ", query)

    url = f"https://eglosar.si/"
    post_data = {"q": query, "qHidden": query}
    response = requests.post(url, data=post_data, timeout=REQUEST_TIMEOUT)

    if not response.ok:
        print(f"Error accessing {url}. Status code: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    articles = soup.find_all("article", class_="ezs-main-results-item")

    results = []

    for article in articles:
        sl = article.find("td", class_="ezs-result-title").get_text(strip=True)

        rows = article.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if cols and cols[0].get_text(strip=True) == "EN":
                english_cell = cols[1]
                first_line = english_cell.stripped_strings
                en = next(first_line, "").strip()
                results.append(slovar_result(en=en, sl=sl))
                break

    return results


def google_translate(query: str) -> list[slovar_result]:
    print("Google Translate: ", query)
    translator = Translator()
    result = loop.run_until_complete(translator.translate(query, dest="sl"))
    return [slovar_result(query, result.text)]


def repozitorij(query: str, page: int) -> list[repozitorij_result]:
    print("Repozitorij: ", query, "page:", page)
    page_size = 50
    offset = (page - 1) * page_size

    connection = psycopg2.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Check if connection is successful
    if connection.closed != 0:
        print("Error connecting to the database.")
        return []

    strani_query = f"""
        SELECT gradivo_id, naslov, leto, repozitorij_url, url as datoteka_url,
            STRING_AGG(stevilka_strani_pdf::text, ',') as stevilke_strani_pdf,
            STRING_AGG(stevilka_strani_skupaj::text, ',') as stevilke_strani_skupaj
        FROM datoteke
        JOIN strani ON datoteke.id = strani.datoteka_id
        JOIN gradiva ON datoteke.gradivo_id = gradiva.id
        WHERE text_tsv @@ plainto_tsquery(%s)
        GROUP BY datoteka_id, gradivo_id, naslov, leto, repozitorij_url, url
        ORDER BY gradivo_id DESC
        LIMIT %s OFFSET %s
    """

    cursor.execute(strani_query, (query, page_size, offset))
    strani = cursor.fetchall()

    results = []
    for stran in strani:
        gradivo_id = stran[0]

        cursor.execute(
            """
            SELECT ime, priimek
            FROM osebe
            JOIN gradiva_osebe ON osebe.id = gradiva_osebe.oseba_id
            WHERE gradivo_id = %s
        """,
            (gradivo_id,),
        )
        avtorji = cursor.fetchall()

        cursor.execute(
            """
            SELECT ime_kratko
            FROM organizacije
            JOIN gradiva_organizacije ON organizacije.id = gradiva_organizacije.organizacija_id
            WHERE gradivo_id = %s
        """,
            (gradivo_id,),
        )
        organizacije = cursor.fetchall()

        results.append(
            repozitorij_result(
                naslov=stran[1],
                leto=stran[2],
                avtorji=[f"{a[0]} {a[1]}" for a in avtorji],
                organizacije=[o[0] for o in organizacije],
                repozitorij_url=stran[3],
                datoteka_url=stran[4],
                stevilka_strani_pdf=stran[5].split(","),
                stevilka_strani_skupaj=stran[6].split(","),
            )
        )

    cursor.close()
    connection.close()

    return results


async def najdi_rezultate(query: str, repozitorij_page: int, enabled_slovarji: Dict[str, bool]) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    results = {}

    tasks = {}

    if enabled_slovarji.get("dis_slovarcek"):
        tasks["dis_slovarcek"] = loop.run_in_executor(None, dis_slovarcek, query)

    if enabled_slovarji.get("ltfe"):
        tasks["ltfe"] = loop.run_in_executor(None, ltft, query)

    if enabled_slovarji.get("sdrv"):
        tasks["sdrv"] = loop.run_in_executor(None, sdrv, query)

    if enabled_slovarji.get("ijs"):
        tasks["ijs"] = loop.run_in_executor(None, ijs, query)

    if enabled_slovarji.get("islovar"):
        tasks["islovar"] = loop.run_in_executor(None, islovar, query)

    if enabled_slovarji.get("ezs_glosar"):
        tasks["ezs_glosar"] = loop.run_in_executor(None, ezs_glosar, query)

    if enabled_slovarji.get("google_translate"):
        tasks["google_translate"] = loop.run_in_executor(None, google_translate, query)

    if enabled_slovarji.get("repozitorij"):
        tasks["repozitorij"] = loop.run_in_executor(None, repozitorij, query, repozitorij_page)

    completed = await asyncio.gather(*tasks.values(), return_exceptions=False)

    for key, value in zip(tasks.keys(), completed):
        results[key] = value

    return results


@app.route("/")
def index():

    # Privzete vrednosti za checkboxe
    enabled_slovarji = {
        "dis_slovarcek": True,
        "ltfe": False,
        "sdrv": True,
        "ijs": True,
        "islovar": True,
        "ezs_glosar": True,
        "google_translate": True,
        "repozitorij": False,
    }

    return render_template("index.html", enabled_slovarji=enabled_slovarji)


@app.route("/search")
def search():

    query = request.args.get("query", "", type=str)
    repozitorij_page = request.args.get("repozitorij-page", 1, type=int)  # Za repozitorij

    # Ker uporabljamo navaden HTML form bodo checkboxi, ki niso checked izpuščeni iz requesta
    enabled_slovarji = {
        "dis_slovarcek": "dis-slovarcek" in request.args and request.args["dis-slovarcek"] == "on",
        "ltfe": "ltfe" in request.args and request.args["ltfe"] == "on",
        "sdrv": "sdrv" in request.args and request.args["sdrv"] == "on",
        "ijs": "ijs" in request.args and request.args["ijs"] == "on",
        "islovar": "islovar" in request.args and request.args["islovar"] == "on",
        "ezs_glosar": "ezs_glosar" in request.args and request.args["ezs_glosar"] == "on",
        "google_translate": "google-translate" in request.args and request.args["google-translate"] == "on",
        "repozitorij": "repozitorij" in request.args and request.args["repozitorij"] == "on",
    }

    # Requeste na vse slovarje izvedemo hkrati, da prihranimo čas
    results = asyncio.run(najdi_rezultate(query, repozitorij_page, enabled_slovarji))

    return render_template(
        "search.html",
        query=query,
        repozitorij_page=repozitorij_page,
        enabled_slovarji=enabled_slovarji,
        results=results,
    )


# V mapi migrations/ so .sql datoteke za migracije. Program si v tabeli migrations zapomni, katere migracije so že bile izvedene.
# Ob zagonu programa preveri, če so bile vse migracije izvedene. Če ne, jih izvede.
def run_migrations():

    connection = psycopg2.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Zagotovi, da tabela migrations obstaja
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS migrations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    connection.commit()

    # Najdi vse .sql datoteke v mapi migrations/
    migrations_path = Path(__file__).parent / "migrations"
    migration_files = sorted(migrations_path.glob("*.sql"))
    migration_names = [file.stem for file in migration_files]

    # Preveri, katere migracije so že bile izvedene in izvedi tiste, ki še niso
    for migration_name in migration_names:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM migrations WHERE name = %s)", (migration_name,))
        already_migrated = cursor.fetchone()[0]
        if already_migrated:
            print(f"Migration {migration_name} already executed.")
            continue
        print(f"Executing migration {migration_name}...")
        with open(f"{migrations_path}/{migration_name}.sql", "r") as file:
            sql = file.read()
            cursor.execute(sql)
            cursor.execute("INSERT INTO migrations (name) VALUES (%s)", (migration_name,))
            print(f"Migration {migration_name} executed.")
    connection.commit()
    cursor.close()
    connection.close()
    print("All migrations executed.")


if __name__ == "__main__":

    run_migrations()

    app.run(debug=True)
