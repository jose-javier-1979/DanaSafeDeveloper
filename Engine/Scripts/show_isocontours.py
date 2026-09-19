from PIL import Image, ImageDraw
from pathlib import Path
import json

BASE = Path(__file__).resolve().parents[1]
RADAR = BASE / "Data" / "Radar" / "AEMET"

IMG = RADAR / "stage1_clean.png"
JSON_FILE = RADAR / "isocontours.json"
OUT = RADAR / "isocontours_preview.png"

im = Image.open(IMG).convert("RGBA")
draw = ImageDraw.Draw(im)

data = json.loads(
    JSON_FILE.read_text(encoding="utf-8")
)

# Para que sea legible no etiquetamos los 429 contornos.
# Dibujamos todos, pero sólo rotulamos los suficientemente grandes.
for level in data["levels"]:
    dbz = level["level_dbz"]

    for contour in level["contours"]:

        pts = [
            (p["x"], p["y"])
            for p in contour["points_px"]
        ]

        if len(pts) < 3:
            continue

        # Cerramos la isocurva
        draw.line(
            pts + [pts[0]],
            fill="white",
            width=1
        )

        # Sólo ponemos etiqueta en estructuras relevantes
        if contour["area_px"] >= 100:

            c = contour["centroid_px"]

            label = f"{dbz}"

            x = c["x"]
            y = c["y"]

            # pequeño fondo negro para lectura
            box = draw.textbbox((x, y), label)

            draw.rectangle(
                box,
                fill=(0, 0, 0, 210)
            )

            draw.text(
                (x, y),
                label,
                fill="white"
            )

im.save(OUT)

print("=== DANASAFE ISOCONTOURS PREVIEW ===")
print("Niveles:", data["levels_dbz"])
print(
    "Contornos:",
    sum(len(x["contours"]) for x in data["levels"])
)
print("Imagen:", OUT)
