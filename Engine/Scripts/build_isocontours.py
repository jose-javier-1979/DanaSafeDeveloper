from PIL import Image
from pathlib import Path
from collections import deque
import json
import math

BASE = Path(__file__).resolve().parents[1]
RADAR = BASE / "Data" / "Radar" / "AEMET"

SRC_IMG = RADAR / "stage1_clean.png"
STATE_FILE = BASE / "Data" / "DanaSafe_state.json"
OUT_JSON = RADAR / "isocontours.json"

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
        if a == 0:
            continue
        grid[y][x] = RGB_DBZ.get((r, g, b))

def neigh8(x, y):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            xx = x + dx
            yy = y + dy
            if 0 <= xx < w and 0 <= yy < h:
                yield xx, yy

def neigh4(x, y):
    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
        xx = x + dx
        yy = y + dy
        if 0 <= xx < w and 0 <= yy < h:
            yield xx, yy

def component_masks_for_level(level):
    """
    Isocurva acumulativa:
    incluye todos los píxeles con Z >= nivel.
    Esto genera contornos meteorológicamente más útiles.
    """
    mask = [[False] * w for _ in range(h)]

    for y in range(h):
        for x in range(w):
            z = grid[y][x]
            if z is not None and z >= level:
                mask[y][x] = True

    visited = [[False] * w for _ in range(h)]
    components = []

    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0][x0] or visited[y0][x0]:
                continue

            q = deque([(x0, y0)])
            visited[y0][x0] = True
            pts = []

            while q:
                x, y = q.popleft()
                pts.append((x, y))

                for xx, yy in neigh8(x, y):
                    if mask[yy][xx] and not visited[yy][xx]:
                        visited[yy][xx] = True
                        q.append((xx, yy))

            if len(pts) >= 6:
                components.append(pts)

    return components

def boundary_of_component(points):
    pts_set = set(points)
    boundary = []

    for x, y in points:
        is_boundary = False

        for xx, yy in neigh4(x, y):
            if (xx, yy) not in pts_set:
                is_boundary = True
                break

        if is_boundary:
            boundary.append((x, y))

    return boundary

def order_boundary(points):
    """
    Orden aproximado angular alrededor del centroide.
    Para el contrato v1 es suficiente.
    Luego podremos sustituirlo por marching squares.
    """
    if len(points) < 3:
        return points

    cx = sum(x for x, y in points) / len(points)
    cy = sum(y for x, y in points) / len(points)

    return sorted(
        points,
        key=lambda p: math.atan2(p[1] - cy, p[0] - cx)
    )

def simplify(points, min_dist=3.0):
    if not points:
        return []

    out = [points[0]]

    for p in points[1:]:
        q = out[-1]
        d = math.hypot(p[0] - q[0], p[1] - q[1])

        if d >= min_dist:
            out.append(p)

    if len(out) >= 3:
        q = out[-1]
        p = out[0]

        if math.hypot(p[0] - q[0], p[1] - q[1]) < min_dist:
            out.pop()

    return out

all_contours = []

for level in LEVELS:
    components = component_masks_for_level(level)

    level_contours = []

    for i, comp in enumerate(components, start=1):
        boundary = boundary_of_component(comp)

        if len(boundary) < 6:
            continue

        ordered = order_boundary(boundary)
        simplified = simplify(ordered, min_dist=3.0)

        xs = [x for x, y in comp]
        ys = [y for x, y in comp]

        contour = {
            "level_dbz": level,
            "component_id": i,
            "area_px": len(comp),

            "centroid_px": {
                "x": round(sum(xs) / len(xs), 2),
                "y": round(sum(ys) / len(ys), 2)
            },

            "bbox_px": [
                min(xs),
                min(ys),
                max(xs),
                max(ys)
            ],

            "points_px": [
                {"x": x, "y": y}
                for x, y in simplified
            ],

            "point_count": len(simplified)
        }

        level_contours.append(contour)

    all_contours.append({
        "level_dbz": level,
        "contours": level_contours
    })

payload = {
    "schema": "DanaSafeReflectivityContours",
    "version": "1.0.0",
    "levels_dbz": LEVELS,
    "levels": all_contours
}

OUT_JSON.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

state = json.loads(
    STATE_FILE.read_text(encoding="utf-8")
)

# Contornos globales del radar
state["radar_contours"] = payload

# De momento se dejan también referenciados desde cada sistema.
# La asociación exacta sistema<->contorno la haremos después
# de georreferenciar y refinar sistemas.
for system in state.get("radar_systems", []):
    system["contours_source"] = "radar_contours"

STATE_FILE.write_text(
    json.dumps(state, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("=== DANASAFE ISOCONTOURS ===")

total = 0

for level_data in all_contours:
    level = level_data["level_dbz"]
    n = len(level_data["contours"])
    total += n
    print(f"{level:2d} dBZ -> {n:3d} contornos")

print()
print("Total contornos:", total)
print("JSON:", OUT_JSON)
print("Contrato actualizado:", STATE_FILE)
