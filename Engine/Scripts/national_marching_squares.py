from PIL import Image, ImageDraw
from pathlib import Path
from collections import defaultdict
import json
import math

BASE = Path(__file__).resolve().parents[1]
SRC = BASE / "Data" / "Radar" / "AEMET" / "NationalClean"
WEB = BASE / "Data" / "Radar" / "AEMET" / "WebAPI"

IMAGE_FILE = SRC / "compo_precip_only.png"
BOUNDS_FILE = SRC / "compo_actual_bounds.json"
META_FILE = SRC / "compo_actual_metadata.json"
LEGEND_FILE = WEB / "leyenda_compo.json"

OUT_JSON = SRC / "national_marching_contours.json"
OUT_PREVIEW = SRC / "national_marching_preview.png"

# ---------------------------------------------------------
# 1. CARGA DE DATOS
# ---------------------------------------------------------

im = Image.open(IMAGE_FILE).convert("RGBA")
w, h = im.size

bounds_raw = json.loads(
    BOUNDS_FILE.read_text(encoding="utf-8")
)

meta = json.loads(
    META_FILE.read_text(encoding="utf-8")
)

legend = json.loads(
    LEGEND_FILE.read_text(encoding="utf-8")
)

# bounds devueltos por AEMET:
# [lon,lat]
lons = [p[0] for p in bounds_raw]
lats = [p[1] for p in bounds_raw]

WEST = min(lons)
EAST = max(lons)
SOUTH = min(lats)
NORTH = max(lats)

print("=== DANASAFE NATIONAL MARCHING SQUARES ===")
print("Imagen:", IMAGE_FILE)
print("Tamaño:", (w, h))
print("Fecha:", meta.get("timestamp"))
print()
print("Bounds:")
print(" WEST :", WEST)
print(" EAST :", EAST)
print(" SOUTH:", SOUTH)
print(" NORTH:", NORTH)

# ---------------------------------------------------------
# 2. PALETA OFICIAL AEMET DESDE SU JSON
# ---------------------------------------------------------

RGB_LEVEL = {}

for item in legend["Lista RGBA"]:
    values = item["Valores"]
    rgba = tuple(int(v) for v in item["RGBA"])

    low = int(values[0])

    RGB_LEVEL[rgba[:3]] = low

LEVELS = sorted(set(RGB_LEVEL.values()))

print()
print("Niveles oficiales:", LEVELS)

# ---------------------------------------------------------
# 3. MATRIZ DE REFLECTIVIDAD
# ---------------------------------------------------------

pixels = im.load()

zgrid = [[None] * w for _ in range(h)]

radar_pixels = 0

for y in range(h):
    for x in range(w):

        r, g, b, a = pixels[x, y]

        z = RGB_LEVEL.get((r, g, b))

        if a > 0 and z is not None:
            zgrid[y][x] = z
            radar_pixels += 1

print("Píxeles radar:", radar_pixels)

# ---------------------------------------------------------
# 4. CONVERSIÓN PIXEL -> GPS
#
# La imagen se utiliza en Leaflet sobre Web Mercator.
# X es lineal en longitud.
# Y debe interpolarse en coordenada Mercator, NO
# directamente en latitud.
# ---------------------------------------------------------

def lat_to_mercator_y(lat):
    lat = max(min(lat, 85.05112878), -85.05112878)
    phi = math.radians(lat)
    return math.log(
        math.tan(math.pi / 4.0 + phi / 2.0)
    )

def mercator_y_to_lat(my):
    return math.degrees(
        2.0 * math.atan(math.exp(my)) - math.pi / 2.0
    )

MERC_NORTH = lat_to_mercator_y(NORTH)
MERC_SOUTH = lat_to_mercator_y(SOUTH)

def pixel_to_lonlat(x, y):

    fx = x / w
    fy = y / h

    lon = WEST + fx * (EAST - WEST)

    my = MERC_NORTH + fy * (
        MERC_SOUTH - MERC_NORTH
    )

    lat = mercator_y_to_lat(my)

    return lon, lat

# ---------------------------------------------------------
# 5. MARCHING SQUARES
# ---------------------------------------------------------

def build_mask(level):

    return [
        [
            1
            if zgrid[y][x] is not None
            and zgrid[y][x] >= level
            else 0

            for x in range(w)
        ]
        for y in range(h)
    ]

# Convención de esquinas:
#
# TL --- TOP --- TR
# |               |
# LEFT          RIGHT
# |               |
# BL -- BOTTOM -- BR
#
# case = TL*8 + TR*4 + BR*2 + BL

LOOKUP = {
    0:  [],
    1:  [("left", "bottom")],
    2:  [("bottom", "right")],
    3:  [("left", "right")],
    4:  [("top", "right")],

    # casos ambiguos 5 y 10
    5:  [("top", "left"), ("bottom", "right")],

    6:  [("top", "bottom")],
    7:  [("top", "left")],
    8:  [("top", "left")],
    9:  [("top", "bottom")],

    10: [("top", "right"), ("left", "bottom")],

    11: [("top", "right")],
    12: [("left", "right")],
    13: [("bottom", "right")],
    14: [("left", "bottom")],
    15: []
}

def edge_point(x, y, edge):

    if edge == "top":
        return (x + 0.5, y)

    if edge == "right":
        return (x + 1.0, y + 0.5)

    if edge == "bottom":
        return (x + 0.5, y + 1.0)

    if edge == "left":
        return (x, y + 0.5)

def marching_segments(mask):

    segments = []

    for y in range(h - 1):

        for x in range(w - 1):

            tl = mask[y][x]
            tr = mask[y][x + 1]
            br = mask[y + 1][x + 1]
            bl = mask[y + 1][x]

            case = (
                tl * 8 +
                tr * 4 +
                br * 2 +
                bl
            )

            for e1, e2 in LOOKUP[case]:

                segments.append(
                    (
                        edge_point(x, y, e1),
                        edge_point(x, y, e2)
                    )
                )

    return segments

# ---------------------------------------------------------
# 6. ENSAMBLAR SEGMENTOS EN POLILÍNEAS
# ---------------------------------------------------------

def point_key(p):
    return (
        round(p[0] * 2) / 2,
        round(p[1] * 2) / 2
    )

def edge_key(a, b):
    return tuple(sorted((a, b)))

def chain_segments(segments):

    adjacency = defaultdict(list)

    for a, b in segments:

        a = point_key(a)
        b = point_key(b)

        adjacency[a].append(b)
        adjacency[b].append(a)

    used = set()
    lines = []

    for start in list(adjacency.keys()):

        for first in adjacency[start]:

            ek = edge_key(start, first)

            if ek in used:
                continue

            line = [start]

            previous = None
            current = start

            while True:

                candidates = []

                for nxt in adjacency[current]:

                    e = edge_key(current, nxt)

                    if e not in used:
                        candidates.append(nxt)

                if not candidates:
                    break

                if previous is not None and len(candidates) > 1:

                    alternatives = [
                        n for n in candidates
                        if n != previous
                    ]

                    if alternatives:
                        candidates = alternatives

                nxt = candidates[0]

                used.add(
                    edge_key(current, nxt)
                )

                previous = current
                current = nxt

                line.append(current)

                if current == start:
                    break

            if len(line) >= 4:
                lines.append(line)

    return lines

# ---------------------------------------------------------
# 7. SIMPLIFICACIÓN RDP
# ---------------------------------------------------------

def perpendicular_distance(p, a, b):

    if a == b:
        return math.hypot(
            p[0] - a[0],
            p[1] - a[1]
        )

    x, y = p
    x1, y1 = a
    x2, y2 = b

    num = abs(
        (y2 - y1) * x
        - (x2 - x1) * y
        + x2 * y1
        - y2 * x1
    )

    den = math.hypot(
        y2 - y1,
        x2 - x1
    )

    return num / den

def rdp(points, epsilon=1.25):

    if len(points) < 3:
        return points

    start = points[0]
    end = points[-1]

    max_dist = 0.0
    index = 0

    for i in range(1, len(points) - 1):

        d = perpendicular_distance(
            points[i],
            start,
            end
        )

        if d > max_dist:
            index = i
            max_dist = d

    if max_dist > epsilon:

        left = rdp(
            points[:index + 1],
            epsilon
        )

        right = rdp(
            points[index:],
            epsilon
        )

        return left[:-1] + right

    return [start, end]

# ---------------------------------------------------------
# 8. EXTRAER CONTORNOS POR NIVEL
# ---------------------------------------------------------

output_levels = []

preview = im.copy()
draw = ImageDraw.Draw(preview)

total_contours = 0

for level in LEVELS:

    mask = build_mask(level)

    segments = marching_segments(mask)

    raw_lines = chain_segments(segments)

    contours = []

    for raw in raw_lines:

        closed = (
            len(raw) >= 4 and
            raw[0] == raw[-1]
        )

        # Conservamos incluso núcleos pequeños intensos.
        # Sólo descartamos geometrías degeneradas.
        if len(raw) < 4:
            continue

        simplified = rdp(
            raw,
            epsilon=1.25
        )

        if closed and simplified[0] != simplified[-1]:
            simplified.append(
                simplified[0]
            )

        xs = [p[0] for p in raw]
        ys = [p[1] for p in raw]

        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)

        clon, clat = pixel_to_lonlat(
            cx,
            cy
        )

        geo = []

        for x, y in simplified:

            lon, lat = pixel_to_lonlat(
                x,
                y
            )

            geo.append([
                round(lon, 6),
                round(lat, 6)
            ])

        contour = {
            "id": f"{level}-{len(contours)+1}",
            "level_dbz": level,
            "closed": closed,

            "point_count_raw": len(raw),
            "point_count": len(simplified),

            "centroid_px": {
                "x": round(cx, 2),
                "y": round(cy, 2)
            },

            "centroid": {
                "longitude": round(clon, 6),
                "latitude": round(clat, 6)
            },

            "bbox_px": [
                round(min(xs), 2),
                round(min(ys), 2),
                round(max(xs), 2),
                round(max(ys), 2)
            ],

            # GeoJSON / MapKit-friendly:
            # [longitude, latitude]
            "coordinates": geo
        }

        contours.append(contour)

        # Preview
        if len(simplified) >= 2:

            draw.line(
                simplified,
                fill=(255, 255, 255, 255),
                width=1
            )

    output_levels.append({
        "level_dbz": level,
        "contours": contours
    })

    total_contours += len(contours)

    print(
        f"{level:3d} dBZ -> "
        f"{len(contours):4d} contornos "
        f"({len(segments):6d} segmentos)"
    )

# ---------------------------------------------------------
# 9. SALIDA
# ---------------------------------------------------------

payload = {
    "schema": {
        "name": "DanaSafeNationalRadarContours",
        "version": "1.0.0"
    },

    "provider": "AEMET",

    "product": "Composicion radar",

    "method": "marching_squares",

    "timestamp": meta.get("timestamp"),

    "source_filename": meta.get("filename"),

    "raster": {
        "width": w,
        "height": h,
        "projection": "EPSG:3857"
    },

    "geographic_bounds": {
        "west": WEST,
        "east": EAST,
        "south": SOUTH,
        "north": NORTH
    },

    "levels_dbz": LEVELS,

    "coordinate_order": [
        "longitude",
        "latitude"
    ],

    "levels": output_levels
}

OUT_JSON.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

preview.save(
    OUT_PREVIEW
)

print()
print("=== RESULTADO ===")
print("Contornos totales:", total_contours)
print("JSON:", OUT_JSON)
print("Preview:", OUT_PREVIEW)

