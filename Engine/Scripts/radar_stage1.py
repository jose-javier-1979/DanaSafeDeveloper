from PIL import Image, ImageDraw
from pathlib import Path
from collections import deque
import math
import json

BASE = Path(__file__).resolve().parents[1]
RADAR_DIR = BASE / "Data" / "Radar" / "AEMET"

SRC = RADAR_DIR / "radar_mu_actual.gif"
OUT_CLEAN = RADAR_DIR / "stage1_clean.png"
OUT_COMPONENTS = RADAR_DIR / "stage1_components.png"
OUT_JSON = RADAR_DIR / "stage1_components.json"

# Paleta AEMET obtenida directamente del GIF
DBZ_BY_INDEX = {
    16: 12,
    23: 18,
    26: 24,
     6: 30,
     7: 36,
     8: 42,
    10: 48,   # ambiguo: también cartografía amarilla
     9: 54,
     4: 60,
     3: 66,
     5: 72
}

CERTAIN_INDICES = set(DBZ_BY_INDEX.keys()) - {10}

im = Image.open(SRC)
palette = im.getpalette()

w, h = im.size
radar_h = 490

cx = w / 2
cy = radar_h / 2
radius = min(w, radar_h) * 0.495

def inside_radar(x, y):
    return (
        y < radar_h and
        math.hypot(x - cx, y - cy) <= radius
    )

# ------------------------------------------------------------
# 1) EXTRACCIÓN CORRECTA DE dBZ
# ------------------------------------------------------------

dbz_grid = [[None for _ in range(w)] for _ in range(radar_h)]

for y in range(radar_h):
    for x in range(w):
        if not inside_radar(x, y):
            continue

        idx = im.getpixel((x, y))

        if idx in DBZ_BY_INDEX:
            dbz_grid[y][x] = DBZ_BY_INDEX[idx]


# ------------------------------------------------------------
# 2) ELIMINACIÓN DE FALSOS AMARILLOS / CARTOGRAFÍA
# ------------------------------------------------------------

# Para distinguir 48 dBZ real de líneas amarillas del mapa:
# - detectamos componentes amarillas
# - calculamos área, bbox y forma
# - exigimos contacto importante con precipitación inequívoca

yellow_mask = [[False for _ in range(w)] for _ in range(radar_h)]

for y in range(radar_h):
    for x in range(w):
        if inside_radar(x, y) and im.getpixel((x, y)) == 10:
            yellow_mask[y][x] = True

visited = [[False for _ in range(w)] for _ in range(radar_h)]

def neighbours4(x, y):
    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < radar_h:
            yield nx, ny

def has_certain_precip_near(x, y, r=2):
    for yy in range(max(0, y-r), min(radar_h, y+r+1)):
        for xx in range(max(0, x-r), min(w, x+r+1)):
            if im.getpixel((xx, yy)) in CERTAIN_INDICES:
                return True
    return False

yellow_components = []

for y0 in range(radar_h):
    for x0 in range(w):
        if not yellow_mask[y0][x0] or visited[y0][x0]:
            continue

        q = deque([(x0, y0)])
        visited[y0][x0] = True
        pts = []

        while q:
            x, y = q.popleft()
            pts.append((x, y))

            for nx, ny in neighbours4(x, y):
                if yellow_mask[ny][nx] and not visited[ny][nx]:
                    visited[ny][nx] = True
                    q.append((nx, ny))

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        area = len(pts)
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)

        bw = xmax - xmin + 1
        bh = ymax - ymin + 1
        bbox_area = bw * bh

        fill_ratio = area / bbox_area if bbox_area else 0
        elongation = max(bw, bh) / max(1, min(bw, bh))

        near_count = sum(
            1 for x, y in pts
            if has_certain_precip_near(x, y, r=2)
        )

        contact_ratio = near_count / area if area else 0

        # Regla inicial conservadora:
        # líneas cartográficas suelen ser largas, finas y poco compactas.
        valid = (
            area >= 3
            and contact_ratio >= 0.55
            and (
                fill_ratio >= 0.20
                or elongation <= 6.0
            )
        )

        yellow_components.append({
            "points": pts,
            "area": area,
            "bbox": [xmin, ymin, xmax, ymax],
            "fill_ratio": fill_ratio,
            "elongation": elongation,
            "contact_ratio": contact_ratio,
            "valid_48dbz": valid
        })

# Borra todo amarillo y recupera sólo componentes válidas
for y in range(radar_h):
    for x in range(w):
        if dbz_grid[y][x] == 48:
            dbz_grid[y][x] = None

for comp in yellow_components:
    if comp["valid_48dbz"]:
        for x, y in comp["points"]:
            dbz_grid[y][x] = 48


# ------------------------------------------------------------
# IMAGEN LIMPIA
# ------------------------------------------------------------

clean = Image.new("RGBA", (w, radar_h), (0,0,0,0))
clean_px = clean.load()

index_by_dbz = {v:k for k,v in DBZ_BY_INDEX.items()}

dbz_counts = {}

for y in range(radar_h):
    for x in range(w):
        dbz = dbz_grid[y][x]

        if dbz is None:
            continue

        idx = index_by_dbz[dbz]

        r = palette[idx*3]
        g = palette[idx*3+1]
        b = palette[idx*3+2]

        clean_px[x,y] = (r,g,b,255)
        dbz_counts[dbz] = dbz_counts.get(dbz,0) + 1

clean.save(OUT_CLEAN)


# ------------------------------------------------------------
# 3) COMPONENTES + CENTROIDES
# ------------------------------------------------------------

# Detectamos componentes por nivel dBZ
component_image = clean.copy()
draw = ImageDraw.Draw(component_image)

components_output = []

for dbz in sorted(DBZ_BY_INDEX.values()):

    mask = [
        [dbz_grid[y][x] == dbz for x in range(w)]
        for y in range(radar_h)
    ]

    visited = [[False for _ in range(w)] for _ in range(radar_h)]

    component_id = 0

    for y0 in range(radar_h):
        for x0 in range(w):

            if not mask[y0][x0] or visited[y0][x0]:
                continue

            q = deque([(x0,y0)])
            visited[y0][x0] = True
            pts = []

            while q:
                x,y = q.popleft()
                pts.append((x,y))

                for nx,ny in neighbours4(x,y):
                    if mask[ny][nx] and not visited[ny][nx]:
                        visited[ny][nx] = True
                        q.append((nx,ny))

            area = len(pts)

            # Quitamos ruido minúsculo
            if area < 4:
                continue

            component_id += 1

            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]

            centroid_x = sum(xs) / area
            centroid_y = sum(ys) / area

            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)

            comp = {
                "dbz": dbz,
                "component_id": component_id,
                "area_px": area,
                "centroid_x": centroid_x,
                "centroid_y": centroid_y,
                "bbox": [xmin, ymin, xmax, ymax]
            }

            components_output.append(comp)

            # Dibujamos centroide
            r = 3
            draw.ellipse(
                [
                    centroid_x-r,
                    centroid_y-r,
                    centroid_x+r,
                    centroid_y+r
                ],
                outline="white",
                width=1
            )

            draw.text(
                (centroid_x + 4, centroid_y - 5),
                f"{dbz}:{component_id}",
                fill="white"
            )

component_image.save(OUT_COMPONENTS)

result = {
    "source": "AEMET",
    "radar": "MU",
    "dbz_counts": dbz_counts,
    "yellow_components": [
        {
            "area": c["area"],
            "bbox": c["bbox"],
            "fill_ratio": round(c["fill_ratio"],4),
            "elongation": round(c["elongation"],4),
            "contact_ratio": round(c["contact_ratio"],4),
            "valid_48dbz": c["valid_48dbz"]
        }
        for c in yellow_components
    ],
    "components": components_output
}

OUT_JSON.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("=== DANASAFE RADAR STAGE 1 ===")
print()

print("1) EXTRACCION dBZ")
for dbz in sorted(dbz_counts):
    print(f"{dbz:2d} dBZ : {dbz_counts[dbz]:6d} pixeles")

print()
print("2) AMARILLO / 48 dBZ")
print("Componentes amarillas:", len(yellow_components))
print(
    "Aceptadas como lluvia:",
    sum(1 for c in yellow_components if c["valid_48dbz"])
)
print(
    "Descartadas cartografia:",
    sum(1 for c in yellow_components if not c["valid_48dbz"])
)

print()
print("3) COMPONENTES")
print("Componentes meteorologicas:", len(components_output))

print()
print("Archivos:")
print(OUT_CLEAN)
print(OUT_COMPONENTS)
print(OUT_JSON)
