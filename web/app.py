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

    if enabled_slovarji.get("ijs"):
        tasks["ijs"] = loop.run_in_executor(None, ijs, query)

    if enabled_slovarji.get("google_translate"):
        tasks["google_translate"] = loop.run_in_executor(None, google_translate, query)

    if enabled_slovarji.get("repozitorij"):
        tasks["repozitorij"] = loop.run_in_executor(None, repozitorij, query, repozitorij_page)

    completed = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for key, value in zip(tasks.keys(), completed):
        results[key] = value

    return results


@app.route("/")
def index():

    # Privzete vrednosti za checkboxe
    enabled_slovarji = {"dis_slovarcek": True, "ltfe": False, "ijs": True, "google_translate": True, "repozitorij": False}

    return render_template("index.html", enabled_slovarji=enabled_slovarji)


@app.route("/search")
def search():

    query = request.args.get("query", "", type=str)
    repozitorij_page = request.args.get("repozitorij-page", 1, type=int)  # Za repozitorij

    # Ker uporabljamo navaden HTML form bodo checkboxi, ki niso checked izpuščeni iz requesta
    enabled_slovarji = {
        "dis_slovarcek": "dis-slovarcek" in request.args and request.args["dis-slovarcek"] == "on",
        "ltfe": "ltfe" in request.args and request.args["ltfe"] == "on",
        "ijs": "ijs" in request.args and request.args["ijs"] == "on",
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


if __name__ == "__main__":
    app.run(debug=True)
