from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from collections import deque
import json
import math

BASE = Path(__file__).resolve().parents[1]
RADAR = BASE / "Data" / "Radar" / "AEMET"

SRC_JSON = RADAR / "stage1_components.json"
SRC_IMG  = RADAR / "stage1_clean.png"

OUT_IMG  = RADAR / "stage2_cells.png"
OUT_JSON = RADAR / "stage2_cells.json"

im = Image.open(SRC_IMG).convert("RGBA")
w, h = im.size

# ------------------------------------------------------------
# Reconstruimos máscara meteorológica desde los colores dBZ
# ------------------------------------------------------------

RGB_DBZ = {
    (0,0,252): 12,
    (0,148,252): 18,
    (0,252,252): 24,
    (67,131,35): 30,
    (0,192,0): 36,
    (0,255,0): 42,
    (255,255,0): 48,
    (255,187,0): 54,
    (255,127,0): 60,
    (255,0,0): 66,
    (200,0,90): 72
}

pixels = im.load()

dbz = [[None] * w for _ in range(h)]

for y in range(h):
    for x in range(w):
        r,g,b,a = pixels[x,y]
        if a:
            dbz[y][x] = RGB_DBZ.get((r,g,b))

# ------------------------------------------------------------
# AGRUPACIÓN ESPACIAL
#
# Permitimos unir ecos separados por pequeños huecos.
# Distancia inicial: 4 px.
# Esto NO altera los píxeles dBZ originales.
# Sólo sirve para determinar pertenencia a una célula.
# ------------------------------------------------------------

LINK_RADIUS = 4

mask = [[dbz[y][x] is not None for x in range(w)] for y in range(h)]

expanded = [[False]*w for _ in range(h)]

for y in range(h):
    for x in range(w):
        if not mask[y][x]:
            continue

        for dy in range(-LINK_RADIUS, LINK_RADIUS+1):
            for dx in range(-LINK_RADIUS, LINK_RADIUS+1):

                if dx*dx + dy*dy > LINK_RADIUS*LINK_RADIUS:
                    continue

                xx = x + dx
                yy = y + dy

                if 0 <= xx < w and 0 <= yy < h:
                    expanded[yy][xx] = True

# ------------------------------------------------------------
# COMPONENTES MADRE SOBRE LA MÁSCARA EXPANDIDA
# ------------------------------------------------------------

visited = [[False]*w for _ in range(h)]

def neighbours8(x,y):
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            if dx == 0 and dy == 0:
                continue
            xx = x+dx
            yy = y+dy
            if 0 <= xx < w and 0 <= yy < h:
                yield xx,yy

mother_components = []

for y0 in range(h):
    for x0 in range(w):

        if not expanded[y0][x0] or visited[y0][x0]:
            continue

        q = deque([(x0,y0)])
        visited[y0][x0] = True

        region = []

        while q:
            x,y = q.popleft()
            region.append((x,y))

            for xx,yy in neighbours8(x,y):
                if expanded[yy][xx] and not visited[yy][xx]:
                    visited[yy][xx] = True
                    q.append((xx,yy))

        # Recuperamos exclusivamente los píxeles meteorológicos reales
        real_pixels = [
            (x,y)
            for x,y in region
            if dbz[y][x] is not None
        ]

        if not real_pixels:
            continue

        # Eliminamos ecos diminutos para esta visualización
        if len(real_pixels) < 25:
            continue

        mother_components.append(real_pixels)

# Orden: mayor célula primero
mother_components.sort(key=len, reverse=True)

# ------------------------------------------------------------
# ESTADÍSTICAS DE CADA CÉLULA
# ------------------------------------------------------------

cells = []

for n, pts in enumerate(mother_components, start=1):

    area = len(pts)

    xs = [x for x,y in pts]
    ys = [y for x,y in pts]

    gx = sum(xs) / area
    gy = sum(ys) / area

    values = [dbz[y][x] for x,y in pts]

    zmax = max(values)
    zmean = sum(values) / area

    total_weight = sum(values)

    wx = sum(x * dbz[y][x] for x,y in pts) / total_weight
    wy = sum(y * dbz[y][x] for x,y in pts) / total_weight

    xmin,xmax = min(xs),max(xs)
    ymin,ymax = min(ys),max(ys)

    histogram = {}

    for z in values:
        histogram[str(z)] = histogram.get(str(z),0) + 1

    cells.append({
        "id": f"C{n}",
        "area_px": area,

        "centroid": {
            "x": round(gx,2),
            "y": round(gy,2)
        },

        "reflectivity_centroid": {
            "x": round(wx,2),
            "y": round(wy,2)
        },

        "zmax_dbz": zmax,
        "zmean_dbz": round(zmean,2),

        "bbox": [xmin,ymin,xmax,ymax],

        "dbz_histogram": histogram
    })

# ------------------------------------------------------------
# VISUALIZACIÓN
# ------------------------------------------------------------

out = im.copy()
draw = ImageDraw.Draw(out)

try:
    font = ImageFont.truetype(
        "/System/Library/Fonts/SFNS.ttf",
        13
    )
except:
    font = ImageFont.load_default()

for cell in cells:

    gx = cell["centroid"]["x"]
    gy = cell["centroid"]["y"]

    wx = cell["reflectivity_centroid"]["x"]
    wy = cell["reflectivity_centroid"]["y"]

    xmin,ymin,xmax,ymax = cell["bbox"]

    # Bounding box de la célula
    draw.rectangle(
        [xmin,ymin,xmax,ymax],
        outline="white",
        width=1
    )

    # Centro geométrico: círculo blanco
    r = 5
    draw.ellipse(
        [gx-r,gy-r,gx+r,gy+r],
        outline="white",
        width=2
    )

    # Centro ponderado por reflectividad: cruz
    s = 6
    draw.line(
        [wx-s,wy,wx+s,wy],
        fill="white",
        width=2
    )
    draw.line(
        [wx,wy-s,wx,wy+s],
        fill="white",
        width=2
    )

    # Línea entre ambos centros
    draw.line(
        [gx,gy,wx,wy],
        fill="white",
        width=1
    )

    label = (
        f'{cell["id"]}  '
        f'Zmax {cell["zmax_dbz"]} dBZ  '
        f'A {cell["area_px"]}'
    )

    tx = xmin
    ty = max(0,ymin-16)

    # Fondo para que pueda leerse
    bbox = draw.textbbox((tx,ty),label,font=font)

    draw.rectangle(
        bbox,
        fill=(0,0,0,210)
    )

    draw.text(
        (tx,ty),
        label,
        fill="white",
        font=font
    )

out.save(OUT_IMG)

OUT_JSON.write_text(
    json.dumps(
        {
            "link_radius_px": LINK_RADIUS,
            "minimum_area_px": 25,
            "cell_count": len(cells),
            "cells": cells
        },
        indent=2
    ),
    encoding="utf-8"
)

print("=== DANASAFE STAGE 2 ===")
print("Celdas meteorologicas:",len(cells))
print()

for c in cells[:20]:
    print(
        c["id"],
        "| area:",c["area_px"],
        "| Zmax:",c["zmax_dbz"],
        "| Zmean:",c["zmean_dbz"],
        "| centro:",
        (c["centroid"]["x"],c["centroid"]["y"]),
        "| nucleo Z:",
        (
            c["reflectivity_centroid"]["x"],
            c["reflectivity_centroid"]["y"]
        )
    )

print()
print("Imagen:",OUT_IMG)
print("JSON:",OUT_JSON)
