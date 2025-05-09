from flask import Flask, request
from bs4 import BeautifulSoup
import requests
import sqlite3
from dataclasses import dataclass
from flask_cors import CORS

app = Flask(__name__)
CORS(app)   # Enable CORS for all routes

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


@app.post("/slovar/repozitorij")
def slovar_repozitorij():
    query = request.json["query"]
    page = request.json["page"]

    page_size = 50

    conn = sqlite3.connect("slovar.db")
    cursor = conn.cursor()

    offset = (page - 1) * page_size
    strani_query = f"""SELECT gradivo_id, naslov, leto, repozitorij_url, url as datoteka_url, GROUP_CONCAT(stevilka_strani_pdf) as stevilke_strani_pdf, GROUP_CONCAT(stevilka_strani_skupaj) as stevilke_strani_skupaj from datoteke JOIN strani ON datoteke.id = strani.datoteka_id JOIN gradiva on datoteke.gradivo_id = gradiva.id WHERE text like ? GROUP BY datoteka_id ORDER BY gradivo_id DESC LIMIT {page_size} OFFSET {offset}"""

    cursor.execute(strani_query, ("%" + query + "%",))
    strani = cursor.fetchall()

    results = []
    for stran in strani:
        avtorji_query = """SELECT ime, priimek FROM osebe JOIN gradiva_osebe ON osebe.id = gradiva_osebe.oseba_id WHERE gradivo_id = ?"""
        cursor.execute(avtorji_query, (stran[0],))
        avtorji = cursor.fetchall()

        organizacije_query = """SELECT ime_kratko FROM organizacije JOIN gradiva_organizacije ON organizacije.id = gradiva_organizacije.organizacija_id WHERE gradivo_id = ?"""
        cursor.execute(organizacije_query, (stran[0],))
        organizacije = cursor.fetchall()

        results.append(
            repozitorij_result(
                stran[1],
                stran[2],
                [a[0] + " " + a[1] for a in avtorji],
                [o[0] for o in organizacije],
                stran[3],
                stran[4],
                stran[5].split(","),
                stran[6].split(","),
            )
        )

    conn.close()

    return results


@app.post("/slovar/dis")
def slovar_dis():
    query = request.json["query"]

    response = requests.get(f"https://dis-slovarcek.ijs.si/search?search_query={query}")

    # Check if the request was successful
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

        results.append({"en": en, "sl": sl})

    return results
