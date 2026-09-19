from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json
import math

BASE = Path(__file__).resolve().parents[1]
PROC = BASE / "Data/Radar/AEMET/NationalSequence/Processed"

OBJECTS_FILE = PROC / "sequence_objects.json"

OUT_JSON = PROC / "radar_systems_v02.json"
OUT_IMG = PROC / "radar_systems_v02_preview.png"

data = json.loads(
    OBJECTS_FILE.read_text(encoding="utf-8")
)

# ---------------------------------------------------------
# CONFIGURACION INICIAL
# ---------------------------------------------------------

BASE_LEVEL = 12

# Unimos componentes Z12 próximos si probablemente forman
# una misma estructura amplia.
MERGE_DISTANCE_PX = 22

# Margen para asignar niveles internos a un sistema exterior.
BBOX_MARGIN_PX = 14

# Eliminamos únicamente ruido microscópico como sistema raíz.
# Los objetos pequeños de niveles internos siguen conservándose.
MIN_ROOT_AREA_PX = 8


def distance(a, b):
    dx = a["centroid_px"]["x"] - b["centroid_px"]["x"]
    dy = a["centroid_px"]["y"] - b["centroid_px"]["y"]
    return math.hypot(dx, dy)


def expanded_bbox(obj, margin):
    x1, y1, x2, y2 = obj["bbox_px"]
    return (
        x1 - margin,
        y1 - margin,
        x2 + margin,
        y2 + margin
    )


def point_in_bbox(x, y, bbox):
    x1, y1, x2, y2 = bbox
    return (
        x1 <= x <= x2
        and
        y1 <= y <= y2
    )


def bbox_union(objects):
    xs1 = [o["bbox_px"][0] for o in objects]
    ys1 = [o["bbox_px"][1] for o in objects]
    xs2 = [o["bbox_px"][2] for o in objects]
    ys2 = [o["bbox_px"][3] for o in objects]

    return [
        min(xs1),
        min(ys1),
        max(xs2),
        max(ys2)
    ]


def weighted_centroid(objects):
    total = sum(
        max(o["area_px"], 1)
        for o in objects
    )

    x = sum(
        o["centroid_px"]["x"] * max(o["area_px"], 1)
        for o in objects
    ) / total

    y = sum(
        o["centroid_px"]["y"] * max(o["area_px"], 1)
        for o in objects
    ) / total

    lon = sum(
        o["centroid"]["longitude"] * max(o["area_px"], 1)
        for o in objects
    ) / total

    lat = sum(
        o["centroid"]["latitude"] * max(o["area_px"], 1)
        for o in objects
    ) / total

    return {
        "px": {
            "x": round(x, 2),
            "y": round(y, 2)
        },
        "geo": {
            "longitude": round(lon, 6),
            "latitude": round(lat, 6)
        }
    }


# ---------------------------------------------------------
# UNION-FIND PARA COMPONENTES Z12 PROXIMOS
# ---------------------------------------------------------

def cluster_roots(roots):

    n = len(roots)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra = find(a)
        rb = find(b)

        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):

            a = roots[i]
            b = roots[j]

            # Si los bounding boxes casi se tocan o sus centroides
            # están próximos, los consideramos estructura continua.
            ba = expanded_bbox(a, BBOX_MARGIN_PX)
            bb = expanded_bbox(b, BBOX_MARGIN_PX)

            ax = a["centroid_px"]["x"]
            ay = a["centroid_px"]["y"]

            bx = b["centroid_px"]["x"]
            by = b["centroid_px"]["y"]

            overlap_like = (
                point_in_bbox(ax, ay, bb)
                or
                point_in_bbox(bx, by, ba)
            )

            close = distance(a, b) <= MERGE_DISTANCE_PX

            if overlap_like or close:
                union(i, j)

    groups = {}

    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(roots[i])

    return list(groups.values())


# ---------------------------------------------------------
# CONSTRUCCION FRAME A FRAME
# ---------------------------------------------------------

frames_out = []

for frame in data["frames"]:

    objects = frame["objects"]

    roots = [
        o for o in objects
        if (
            o["level_dbz"] == BASE_LEVEL
            and
            o["area_px"] >= MIN_ROOT_AREA_PX
        )
    ]

    root_groups = cluster_roots(roots)

    systems = []

    for idx, root_group in enumerate(root_groups, start=1):

        root_bbox = bbox_union(root_group)

        expanded = (
            root_bbox[0] - BBOX_MARGIN_PX,
            root_bbox[1] - BBOX_MARGIN_PX,
            root_bbox[2] + BBOX_MARGIN_PX,
            root_bbox[3] + BBOX_MARGIN_PX
        )

        members = list(root_group)

        root_centroid = weighted_centroid(root_group)

        rx = root_centroid["px"]["x"]
        ry = root_centroid["px"]["y"]

        # Añadimos niveles internos
        for obj in objects:

            if obj["level_dbz"] <= BASE_LEVEL:
                continue

            x = obj["centroid_px"]["x"]
            y = obj["centroid_px"]["y"]

            if point_in_bbox(x, y, expanded):
                members.append(obj)

        members = list({
            m["id"]: m
            for m in members
        }.values())

        centroid = weighted_centroid(members)
        bbox = bbox_union(members)

        levels = {}

        for m in members:
            z = str(m["level_dbz"])
            levels.setdefault(z, []).append(m["id"])

        zmax = max(
            m["level_dbz"]
            for m in members
        )

        area_by_level = {}

        for m in members:
            z = str(m["level_dbz"])
            area_by_level[z] = (
                area_by_level.get(z, 0)
                +
                m["area_px"]
            )

        system = {
            "id": f"F{frame['frame']:02d}_SYS_{idx:03d}",
            "frame": frame["frame"],
            "timestamp": frame["timestamp"],

            "centroid_px": centroid["px"],
            "centroid": centroid["geo"],

            "bbox_px": bbox,

            "zmax_dbz": zmax,

            "levels_present": sorted(
                int(z)
                for z in levels
            ),

            "area_by_level_px": area_by_level,

            "root_area_px": sum(
                o["area_px"]
                for o in root_group
            ),

            "member_count": len(members),

            "members_by_level": levels
        }

        systems.append(system)

    # Ordenamos por tamaño exterior
    systems.sort(
        key=lambda s: s["root_area_px"],
        reverse=True
    )

    # Renumeración por importancia dentro del frame
    for i, s in enumerate(systems, start=1):
        s["rank"] = i

    frames_out.append({
        "frame": frame["frame"],
        "timestamp": frame["timestamp"],
        "systems": systems
    })

    print(
        f"Frame {frame['frame']:02d}: "
        f"{len(objects):3d} objetos -> "
        f"{len(systems):3d} sistemas"
    )


# ---------------------------------------------------------
# SALIDA JSON
# ---------------------------------------------------------

result = {
    "schema": {
        "name": "DanaSafeRadarSystems",
        "version": "0.2.0"
    },

    "provider": data.get("provider"),
    "product": data.get("product"),
    "projection": data.get("projection"),
    "bounds": data.get("bounds"),

    "method": {
        "root_level_dbz": BASE_LEVEL,
        "merge_distance_px": MERGE_DISTANCE_PX,
        "bbox_margin_px": BBOX_MARGIN_PX,
        "minimum_root_area_px": MIN_ROOT_AREA_PX
    },

    "frames": frames_out
}

OUT_JSON.write_text(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# ---------------------------------------------------------
# PREVIEW DEL ULTIMO FRAME
# ---------------------------------------------------------

last = frames_out[-1]

background = (
    PROC /
    f"frame_{last['frame']:02d}_clean.png"
)

img = Image.open(background).convert("RGBA")
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype(
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        12
    )
except:
    font = ImageFont.load_default()


# Sólo los sistemas principales para no saturar
important = [
    s for s in last["systems"]
    if (
        s["root_area_px"] >= 20
        or
        s["zmax_dbz"] >= 36
    )
]

for s in important:

    x1, y1, x2, y2 = s["bbox_px"]

    draw.rectangle(
        [x1, y1, x2, y2],
        outline=(255,255,255,220),
        width=1
    )

    x = s["centroid_px"]["x"]
    y = s["centroid_px"]["y"]

    draw.ellipse(
        [x-3, y-3, x+3, y+3],
        fill=(255,255,255,255)
    )

    txt = (
        f"S{s['rank']} "
        f"Zmax {s['zmax_dbz']} "
        f"A12 {s['root_area_px']}px\n"
        f"{s['centroid']['latitude']:.2f}, "
        f"{s['centroid']['longitude']:.2f}"
    )

    draw.text(
        (x + 5, y + 4),
        txt,
        fill=(255,255,255,255),
        font=font
    )

img.save(OUT_IMG)


# ---------------------------------------------------------
# RESUMEN
# ---------------------------------------------------------

print()
print("=== DANASAFE RADAR SYSTEMS 0.2 ===")

for frame in frames_out:
    systems = frame["systems"]

    significant = [
        s for s in systems
        if (
            s["root_area_px"] >= 20
            or
            s["zmax_dbz"] >= 36
        )
    ]

    print(
        f"Frame {frame['frame']:02d}: "
        f"{len(systems):3d} sistemas totales | "
        f"{len(significant):3d} significativos"
    )

print()
print("JSON:", OUT_JSON)
print("Preview:", OUT_IMG)
