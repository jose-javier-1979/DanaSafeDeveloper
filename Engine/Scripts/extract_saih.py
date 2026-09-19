from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
import json
import re

BASE = Path(__file__).resolve().parents[1]
HTML_FILE = BASE / "Data" / "saih_aforos.html"
OUTPUT = BASE / "Data" / "saih_stations.json"
STATE_FILE = BASE / "Data" / "current_state.json"

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_td = []
        self.current_row = []
        self.rows = []
        self.current_href = None
        self.row_links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "tbody":
            self.in_tbody = True

        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.current_row = []
            self.row_links = []

        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.current_td = []

        elif tag == "a" and self.in_tr:
            href = attrs.get("href")
            if href:
                self.row_links.append(href)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            text = " ".join("".join(self.current_td).split())
            self.current_row.append(text)
            self.in_td = False

        elif tag == "tr" and self.in_tr:
            if len(self.current_row) >= 8:
                self.rows.append((self.current_row, list(self.row_links)))
            self.in_tr = False

        elif tag == "tbody":
            self.in_tbody = False

    def handle_data(self, data):
        if self.in_td:
            self.current_td.append(data)

def number(value):
    value = value.strip().replace(".", "").replace(",", ".")
    try:
        return float(value)
    except:
        return None

html = HTML_FILE.read_text(encoding="utf-8", errors="ignore")

parser = TableParser()
parser.feed(html)

stations = []

for row, links in parser.rows:
    if len(row) < 8:
        continue

    station = row[0]
    variable = row[1]

    if not station or station.upper() == "PUNTO":
        continue

    station_id = None

    for link in links:
        match = re.search(r"/aforos/(\d+)", link)
        if match:
            station_id = match.group(1)
            break

    status_raw = row[7].strip()

    if "FALLO" in status_raw.upper():
        status = "failure"
    else:
        status = "ok"

    item = {
        "id": station_id,
        "station": station,
        "variable": variable,
        "flow_m3s": number(row[2]),
        "thresholds_m3s": {
            "yellow": number(row[3]),
            "orange": number(row[4]),
            "red": number(row[5])
        },
        "time": row[6],
        "status": status,
        "source": "SAIH-CHJ",
        "observed": True
    }

    stations.append(item)

payload = {
    "source": "SAIH-CHJ",
    "retrieved_at": datetime.now().astimezone().isoformat(),
    "station_count": len(stations),
    "stations": stations
}

OUTPUT.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

with STATE_FILE.open("r", encoding="utf-8") as f:
    state = json.load(f)

state["timestamp"] = datetime.now().astimezone().isoformat()
state["sources"]["hydrology"] = {
    "source": "SAIH-CHJ",
    "status": "online",
    "station_count": len(stations),
    "data_file": "saih_stations.json"
}

STATE_FILE.write_text(
    json.dumps(state, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("DANASAFE SAIH EXTRACTOR OK")
print("Estaciones extraidas:", len(stations))
print("Archivo:", OUTPUT)
print()

targets = [
    "POYO",
    "FORATA",
    "HUERTO MULET",
    "VILAMARXANT",
    "AMADORIO",
    "GUADALEST",
    "SAX"
]

for target in targets:
    found = [
        s for s in stations
        if target in s["station"].upper()
    ]

    for s in found:
        print(
            s["station"],
            "|",
            s["flow_m3s"],
            "m3/s",
            "|",
            s["time"],
            "|",
            s["status"]
        )
