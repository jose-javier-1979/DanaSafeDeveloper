from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.parse
import json

BASE = Path(__file__).resolve().parents[1]

WEB = BASE / "Data" / "Radar" / "AEMET" / "WebAPI"
OUT = BASE / "Data" / "Radar" / "AEMET" / "NationalClean"

OUT.mkdir(parents=True, exist_ok=True)

timeline_file = WEB / "timeline_compo_PB.json"

data = json.loads(
    timeline_file.read_text(encoding="utf-8")
)

root = data[0]
elements = root["Elementos"]

# Ordenamos por fecha real
latest = max(
    elements,
    key=lambda e: datetime.fromisoformat(e["Fecha"])
)

fecha = latest["Fecha"]
filename = latest["Nombre fichero"]

print("=== ULTIMA COMPOSICION AEMET ===")
print("Fecha:", fecha)
print("Fichero:", filename)

encoded = urllib.parse.quote(filename, safe="")

bounds_url = (
    "https://www.aemet.es/es/api-eltiempo/"
    f"radar/bounds-radar/compo/{encoded}"
)

image_url = (
    "https://www.aemet.es/es/api-eltiempo/"
    f"radar/imagen-radar/compo/{encoded}"
)

bounds_file = OUT / "compo_actual_bounds.json"
image_file = OUT / "compo_actual.png"

print()
print("Descargando bounds...")

with urllib.request.urlopen(bounds_url, timeout=60) as r:
    bounds = r.read()

bounds_file.write_bytes(bounds)

print("OK:", bounds_file)

print()
print("Descargando imagen nacional...")

with urllib.request.urlopen(image_url, timeout=60) as r:
    image = r.read()
    content_type = r.headers.get("Content-Type")

image_file.write_bytes(image)

print("OK:", image_file)
print("Bytes:", len(image))
print("Content-Type:", content_type)

metadata = {
    "provider": "AEMET",
    "product": "compo",
    "region": "Penbal",
    "timestamp": fecha,
    "filename": filename,
    "projection_hint": "EPSG:3857",
    "image": str(image_file),
    "bounds": str(bounds_file)
}

(OUT / "compo_actual_metadata.json").write_text(
    json.dumps(metadata, indent=2),
    encoding="utf-8"
)

print()
print("=== BOUNDS ===")

try:
    b = json.loads(bounds.decode("utf-8"))
    print(json.dumps(b, indent=2))
except Exception:
    print(bounds.decode("utf-8", errors="replace"))

