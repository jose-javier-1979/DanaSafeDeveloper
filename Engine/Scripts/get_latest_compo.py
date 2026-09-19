from pathlib import Path
import json
import urllib.request
import urllib.parse

BASE = Path(__file__).resolve().parents[1]
WEB = BASE / "Data" / "Radar" / "AEMET" / "WebAPI"
OUT = BASE / "Data" / "Radar" / "AEMET" / "NationalClean"

OUT.mkdir(parents=True, exist_ok=True)

timeline_file = WEB / "timeline_compo_PB.json"

data = json.loads(
    timeline_file.read_text(encoding="utf-8")
)

obj = data[0]

print("Producto:", obj.get("Producto"))
print("Region:", obj.get("Region"))

# Buscamos la estructura real completa para localizar el último fichero.
print()
print("Claves:", list(obj.keys()))

# Algunas versiones del endpoint contienen lineaTiempo y lista de ficheros
# en estructuras separadas. Mostramos una vista corta para detectar nombres.
raw = timeline_file.read_text(encoding="utf-8")

for term in [
    "Nombre fichero",
    "fichero",
    "Fichero",
    "Elementos",
    "lineaTiempo"
]:
    if term in raw:
        print("Encontrado campo:", term)

