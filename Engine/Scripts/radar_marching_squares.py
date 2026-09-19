from PIL import Image, ImageDraw
from pathlib import Path
import json
import math

BASE = Path(__file__).resolve().parents[1]
RADAR = BASE / "Data" / "Radar" / "AEMET"

SRC_IMG = RADAR / "stage1_clean.png"
OUT_JSON = RADAR / "marching_contours.json"
OUT_IMG = RADAR / "marching_contours_preview.png"
STATE_FILE = BASE / "Data" / "DanaSafe_state.json"

RGB_DBZ = {
    (0, 0, 252): 12,
    (0, 148, 252): 18,
    (0, 252, 252): 24,
    (67, 131, 35): 30,
    (0, 192, 0): 36,
    (0, 255, 0): 42,
    (255, 255, 0): 48,
    (255, 187, 0): 54,
    (255, 127, 0): 60,
    (255, 0, 0): 66,
    (200, 0, 90): 72
}

LEVELS = sorted(set(RGB_DBZ.values()))

im = Image.open(SRC_IMG).convert("RGBA")
w, h = im.size
px = im.load()

grid = [[None] * w for _ in range(h)]

for y in range(h):
    for x in range(w):
        r, g, b, a = px[x, y]
        if a:
            grid[y][x] = RGB_DBZ.get((r, g, b))

def build_mask(level):
    return [
        [
            1 if grid[y][x] is not None and grid[y][x] >= level else 0
            for x in range(w)
        ]
        for y in range(h)
    ]

# Marching squares: segmentos dentro de cada celda 2x2
# puntos medios de aristas:
# top=(x+0.5,y)
# right=(x+1,y+0.5)
# bottom=(x+0.5,y+1)
# left=(x,y+0.5)

LOOKUP = {
    0: [],
    1: [("left", "bottom")],
    2: [("bottom", "right")],
    3: [("left", "right")],
    4: [("top", "right")],
    5: [("top", "left"), ("bottom", "right")],
    6: [("top", "bottom")],
    7: [("top", "left")],
    8: [("top", "left")],
    9: [("top", "bottom")],
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
        return (x + 1, y + 0.5)
    if edge == "bottom":
        return (x + 0.5, y + 1)
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

            case = tl * 8 + tr * 4 + br * 2 + bl

            for e1, e2 in LOOKUP[case]:
                p1 = edge_point(x, y, e1)
                p2 = edge_point(x, y, e2)
                segments.append((p1, p2))

    return segments

def key(p):
    return (round(p[0], 3), round(p[1], 3))

def chain_segments(segments):
    adjacency = {}

    for a, b in segments:
        ka = key(a)
        kb = key(b)

        adjacency.setdefault(ka, []).append(kb)
        adjacency.setdefault(kb, []).append(ka)

    visited_edges = set()
    polylines = []

    for start in list(adjacency.keys()):

        for nxt in adjacency[start]:

            edge = tuple(sorted((start, nxt)))
            if edge in visited_edges:
                continue

            line = [start]
            current = start
            previous = None

            while True:
                neighbours = adjacency.get(current, [])

                candidates = [
                    n for n in neighbours
                    if tuple(sorted((current, n))) not in visited_edges
                ]

                if not candidates:
                    break

                if previous is not None and len(candidates) > 1:
                    candidates = [n for n in candidates if n != previous] or candidates

                nxt2 = candidates[0]

                visited_edges.add(tuple(sorted((current, nxt2))))

                previous = current
                current = nxt2
                line.append(current)

                if current == start:
                    break

            if len(line) >= 6:
                polylines.append(line)

    return polylines

def simplify(line, min_dist=2.0):
    if not line:
        return []

    out = [line[0]]

    for p in line[1:]:
        q = out[-1]
        if math.hypot(p[0] - q[0], p[1] - q[1]) >= min_dist:
            out.append(p)

    if len(out) >= 3 and out[0] != out[-1]:
        out.append(out[0])

    return out

levels_output = []

for level in LEVELS:

    mask = build_mask(level)
    segments = marching_segments(mask)
    lines = chain_segments(segments)

    contours = []

    for i, line in enumerate(lines, start=1):

        simp = simplify(line, min_dist=2.0)

        if len(simp) < 6:
            continue

        xs = [p[0] for p in simp]
        ys = [p[1] for p in simp]

        contours.append({
            "id": f"{level}-{i}",
            "level_dbz": level,
            "point_count": len(simp),
            "bbox_px": [
                round(min(xs), 2),
                round(min(ys), 2),
                round(max(xs), 2),
                round(max(ys), 2)
            ],
            "points_px": [
                {"x": round(x, 2), "y": round(y, 2)}
                for x, y in simp
            ]
        })

    levels_output.append({
        "level_dbz": level,
        "contours": contours
    })

payload = {
    "schema": "DanaSafeMarchingContours",
    "version": "1.0.0",
    "method": "marching_squares",
    "levels_dbz": LEVELS,
    "levels": levels_output
}

OUT_JSON.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

# Actualizamos contrato
state = json.loads(
    STATE_FILE.read_text(encoding="utf-8")
)

state["radar_contours"] = payload

STATE_FILE.write_text(
    json.dumps(state, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

# VISUALIZACION
preview = im.copy()
draw = ImageDraw.Draw(preview)

for level_data in levels_output:
    level = level_data["level_dbz"]

    for c in level_data["contours"]:
        pts = [(p["x"], p["y"]) for p in c["points_px"]]

        if len(pts) >= 2:
            draw.line(
                pts,
                fill="white",
                width=1
            )

OUT_IMG_PATH = OUT_IMG
preview.save(OUT_IMG_PATH)

print("=== DANASAFE MARCHING SQUARES ===")

total = 0

for level_data in levels_output:
    level = level_data["level_dbz"]
    n = len(level_data["contours"])
    total += n
    print(f"{level:2d} dBZ -> {n:3d} contornos")

print()
print("Total:", total)
print("JSON:", OUT_JSON)
print("Preview:", OUT_IMG_PATH)
print("Contrato actualizado:", STATE_FILE)
