from PIL import Image
from pathlib import Path
from collections import deque
import json
import math

BASE = Path(__file__).resolve().parents[1]
SEQ = BASE / "Data" / "Radar" / "AEMET" / "NationalSequence"
LEGEND = BASE / "Data" / "Radar" / "AEMET" / "WebAPI" / "leyenda_compo.json"

MANIFEST = SEQ / "sequence_manifest.json"
OUT = SEQ / "Processed"
OUT.mkdir(exist_ok=True)

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
legend = json.loads(LEGEND.read_text(encoding="utf-8"))

WEST = manifest["bounds"]["west"]
EAST = manifest["bounds"]["east"]
SOUTH = manifest["bounds"]["south"]
NORTH = manifest["bounds"]["north"]

rgb_to_dbz = {}

for item in legend["Lista RGBA"]:
    rgba = tuple(int(v) for v in item["RGBA"])
    dbz = int(item["Valores"][0])
    rgb_to_dbz[rgba[:3]] = dbz

LEVELS = sorted(set(rgb_to_dbz.values()))

def lat_to_merc_y(lat):
    lat = max(min(lat, 85.05112878), -85.05112878)
    phi = math.radians(lat)
    return math.log(math.tan(math.pi / 4 + phi / 2))

def merc_y_to_lat(y):
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)

M_N = lat_to_merc_y(NORTH)
M_S = lat_to_merc_y(SOUTH)

def pixel_to_lonlat(x, y, w, h):
    lon = WEST + (x / w) * (EAST - WEST)
    my = M_N + (y / h) * (M_S - M_N)
    lat = merc_y_to_lat(my)
    return lon, lat

def connected_components(mask, w, h):
    seen = set()
    comps = []

    for y in range(h):
        for x in range(w):
            if not mask[y][x] or (x, y) in seen:
                continue

            q = deque([(x, y)])
            seen.add((x, y))
            pts = []

            while q:
                cx, cy = q.popleft()
                pts.append((cx, cy))

                for nx in range(max(0, cx - 1), min(w, cx + 2)):
                    for ny in range(max(0, cy - 1), min(h, cy + 2)):
                        if nx == cx and ny == cy:
                            continue
                        if mask[ny][nx] and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            q.append((nx, ny))

            comps.append(pts)

    return comps

frames_out = []

print("=== DANASAFE SEQUENCE OBJECT EXTRACTION ===")

for frame in manifest["frames"]:

    path = BASE / frame["local_file"]

    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()

    zgrid = [[None] * w for _ in range(h)]

    clean = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    clean_px = clean.load()

    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            z = rgb_to_dbz.get((r, g, b))

            if z is not None:
                zgrid[y][x] = z
                clean_px[x, y] = (r, g, b, 255)

    objects_all = []

    for level in LEVELS:

        mask = [
            [
                zgrid[y][x] is not None and zgrid[y][x] >= level
                for x in range(w)
            ]
            for y in range(h)
        ]

        comps = connected_components(mask, w, h)

        # Evitamos ruido mínimo para tracking.
        comps = [c for c in comps if len(c) >= 4]

        for idx, pts in enumerate(comps, 1):

            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]

            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)

            lon, lat = pixel_to_lonlat(cx, cy, w, h)

            objects_all.append({
                "id": f"F{frame['frame']:02d}_Z{level}_{idx}",
                "frame": frame["frame"],
                "timestamp": frame["fecha"],
                "level_dbz": level,
                "area_px": len(pts),
                "centroid_px": {
                    "x": round(cx, 2),
                    "y": round(cy, 2)
                },
                "centroid": {
                    "longitude": round(lon, 6),
                    "latitude": round(lat, 6)
                },
                "bbox_px": [
                    min(xs),
                    min(ys),
                    max(xs),
                    max(ys)
                ]
            })

    clean_name = OUT / f"frame_{frame['frame']:02d}_clean.png"
    clean.save(clean_name)

    frame_record = {
        "frame": frame["frame"],
        "timestamp": frame["fecha"],
        "source": frame["filename"],
        "objects": objects_all
    }

    frames_out.append(frame_record)

    print(
        f"Frame {frame['frame']:02d} "
        f"{frame['fecha']} "
        f"objetos={len(objects_all)}"
    )

result = {
    "schema": {
        "name": "DanaSafeRadarSequenceObjects",
        "version": "1.0.0"
    },
    "provider": "AEMET",
    "product": "Composicion radar",
    "projection": "EPSG:3857",
    "bounds": manifest["bounds"],
    "frame_interval_minutes": manifest["frame_interval_minutes"],
    "frames": frames_out
}

out_json = OUT / "sequence_objects.json"

out_json.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print()
print("=== RESULTADO ===")
print("JSON:", out_json)
print("Frames:", len(frames_out))
print(
    "Objetos totales:",
    sum(len(f["objects"]) for f in frames_out)
)
