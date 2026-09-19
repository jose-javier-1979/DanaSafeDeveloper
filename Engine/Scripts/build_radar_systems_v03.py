from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from collections import deque
import json
import math

BASE = Path(__file__).resolve().parents[1]

SEQ = BASE / "Data/Radar/AEMET/NationalSequence"
PROC = SEQ / "Processed"

MANIFEST_FILE = SEQ / "sequence_manifest.json"
LEGEND_FILE = (
    BASE /
    "Data/Radar/AEMET/WebAPI/leyenda_compo.json"
)

OUT_JSON = PROC / "radar_systems_v03.json"
OUT_IMG = PROC / "radar_systems_v03_preview.png"

manifest = json.loads(
    MANIFEST_FILE.read_text(encoding="utf-8")
)

legend = json.loads(
    LEGEND_FILE.read_text(encoding="utf-8")
)

WEST = manifest["bounds"]["west"]
EAST = manifest["bounds"]["east"]
SOUTH = manifest["bounds"]["south"]
NORTH = manifest["bounds"]["north"]


# -------------------------------------------------------
# PALETA OFICIAL
# -------------------------------------------------------

rgb_to_dbz = {}

for item in legend["Lista RGBA"]:

    rgba = tuple(
        int(v)
        for v in item["RGBA"]
    )

    level = int(
        item["Valores"][0]
    )

    rgb_to_dbz[rgba[:3]] = level


LEVELS = sorted(
    set(rgb_to_dbz.values())
)


# -------------------------------------------------------
# GPS / WEB MERCATOR
# -------------------------------------------------------

def lat_to_merc_y(lat):

    lat = max(
        min(lat, 85.05112878),
        -85.05112878
    )

    phi = math.radians(lat)

    return math.log(
        math.tan(
            math.pi / 4 +
            phi / 2
        )
    )


def merc_y_to_lat(y):

    return math.degrees(
        2 * math.atan(math.exp(y))
        -
        math.pi / 2
    )


MN = lat_to_merc_y(NORTH)
MS = lat_to_merc_y(SOUTH)


def pixel_to_lonlat(x, y, w, h):

    lon = (
        WEST
        +
        (x / w)
        *
        (EAST - WEST)
    )

    my = (
        MN
        +
        (y / h)
        *
        (MS - MN)
    )

    lat = merc_y_to_lat(my)

    return lon, lat


# -------------------------------------------------------
# COMPONENTES CONECTADOS
# -------------------------------------------------------

def connected_components(mask, w, h):

    seen = set()
    components = []

    for y in range(h):

        for x in range(w):

            if not mask[y][x]:
                continue

            if (x, y) in seen:
                continue

            q = deque([(x, y)])

            seen.add((x, y))

            pixels = []

            while q:

                cx, cy = q.popleft()

                pixels.append(
                    (cx, cy)
                )

                for ny in range(
                    max(0, cy - 1),
                    min(h, cy + 2)
                ):

                    for nx in range(
                        max(0, cx - 1),
                        min(w, cx + 2)
                    ):

                        if (
                            nx == cx
                            and ny == cy
                        ):
                            continue

                        if (
                            mask[ny][nx]
                            and
                            (nx, ny) not in seen
                        ):

                            seen.add(
                                (nx, ny)
                            )

                            q.append(
                                (nx, ny)
                            )

            components.append(
                pixels
            )

    return components


# -------------------------------------------------------
# DILATACION MUY PEQUEÑA
#
# Permite pequeñas discontinuidades reales del radar,
# pero no fusiona estructuras separadas decenas de píxeles.
# -------------------------------------------------------

def dilate_pixel_set(points, w, h, radius=2):

    result = set()

    for x, y in points:

        for dy in range(
            -radius,
            radius + 1
        ):

            for dx in range(
                -radius,
                radius + 1
            ):

                nx = x + dx
                ny = y + dy

                if (
                    0 <= nx < w
                    and
                    0 <= ny < h
                ):

                    result.add(
                        (nx, ny)
                    )

    return result


# -------------------------------------------------------
# PROCESADO DE LOS 10 FRAMES
# -------------------------------------------------------

frames_out = []

MIN_ROOT_AREA = 8
ROOT_DILATION = 2

print(
    "=== DANASAFE RADAR SYSTEMS 0.3 ==="
)

for frame_info in manifest["frames"]:

    frame_number = frame_info["frame"]

    clean_file = (
        PROC /
        f"frame_{frame_number:02d}_clean.png"
    )

    im = Image.open(
        clean_file
    ).convert("RGBA")

    w, h = im.size
    px = im.load()

    zgrid = [
        [None] * w
        for _ in range(h)
    ]

    for y in range(h):

        for x in range(w):

            r, g, b, a = px[x, y]

            if a == 0:
                continue

            z = rgb_to_dbz.get(
                (r, g, b)
            )

            if z is not None:
                zgrid[y][x] = z


    # ---------------------------------------------------
    # RAICES REALES Z >= 12
    # ---------------------------------------------------

    root_mask = [
        [
            zgrid[y][x] is not None
            and
            zgrid[y][x] >= 12

            for x in range(w)
        ]

        for y in range(h)
    ]

    roots = connected_components(
        root_mask,
        w,
        h
    )

    roots = [
        r for r in roots
        if len(r) >= MIN_ROOT_AREA
    ]


    # Precompute connected components once per dBZ level for this frame.
    # The previous implementation rebuilt the full mask and flood-filled the
    # ~1M-pixel image once for every root system and every level.  The
    # components depend only on the frame/level, not on the root; only the
    # overlap test is root-specific.  This preserves output byte-for-byte while
    # reducing the dominant runtime cost.
    level_components = {}

    for level in LEVELS:
        if level < 12:
            continue

        mask = [
            [
                zgrid[y][x] is not None
                and zgrid[y][x] >= level
                for x in range(w)
            ]
            for y in range(h)
        ]

        comps = connected_components(mask, w, h)
        level_components[level] = [
            (comp, set(comp))
            for comp in comps
        ]

    systems = []

    for root_index, root_pixels in enumerate(
        roots,
        start=1
    ):

        root_set = set(
            root_pixels
        )

        association_zone = (
            dilate_pixel_set(
                root_pixels,
                w,
                h,
                ROOT_DILATION
            )
        )

        xs = [
            p[0]
            for p in root_pixels
        ]

        ys = [
            p[1]
            for p in root_pixels
        ]

        root_area = len(
            root_pixels
        )


        # Centroide del sistema definido por Z12
        cx = sum(xs) / root_area
        cy = sum(ys) / root_area

        lon, lat = pixel_to_lonlat(
            cx,
            cy,
            w,
            h
        )


        level_data = {}

        zmax = 12

        # ---------------------------------------------------
        # COMPONENTES INTERIORES
        # ---------------------------------------------------

        for level in LEVELS:

            if level < 12:
                continue

            accepted = []

            for comp, comp_set in level_components[level]:

                overlap = (
                    len(
                        comp_set
                        &
                        association_zone
                    )
                )

                if overlap == 0:
                    continue

                fraction = (
                    overlap /
                    len(comp_set)
                )

                # La mayoría del componente debe pertenecer
                # al sistema raíz.
                if fraction >= 0.50:

                    accepted.append(
                        comp
                    )

            if accepted:

                total_area = sum(
                    len(c)
                    for c in accepted
                )

                level_data[str(level)] = {
                    "component_count": len(
                        accepted
                    ),
                    "area_px": total_area
                }

                zmax = max(
                    zmax,
                    level
                )


        system = {

            "id": (
                f"F{frame_number:02d}"
                f"_SYS_{root_index:03d}"
            ),

            "frame": frame_number,

            "timestamp": frame_info["fecha"],

            "root_level_dbz": 12,

            "root_area_px": root_area,

            "zmax_dbz": zmax,

            "centroid_px": {
                "x": round(cx, 2),
                "y": round(cy, 2)
            },

            "centroid": {
                "longitude": round(
                    lon,
                    6
                ),
                "latitude": round(
                    lat,
                    6
                )
            },

            "bbox_px": [
                min(xs),
                min(ys),
                max(xs),
                max(ys)
            ],

            "levels": level_data
        }

        systems.append(
            system
        )


    systems.sort(
        key=lambda s: (
            s["root_area_px"],
            s["zmax_dbz"]
        ),
        reverse=True
    )

    for i, system in enumerate(
        systems,
        start=1
    ):

        system["rank"] = i


    significant = [
        s
        for s in systems
        if (
            s["root_area_px"] >= 20
            or
            s["zmax_dbz"] >= 36
        )
    ]

    frames_out.append({
        "frame": frame_number,
        "timestamp": frame_info["fecha"],
        "systems": systems
    })

    print(
        f"Frame {frame_number:02d}: "
        f"{len(roots):3d} sistemas reales | "
        f"{len(significant):3d} significativos"
    )


# -------------------------------------------------------
# JSON
# -------------------------------------------------------

payload = {

    "schema": {
        "name": "DanaSafeRadarSystems",
        "version": "0.3.0"
    },

    "provider": "AEMET",

    "product": "Composicion radar",

    "projection": "EPSG:3857",

    "bounds": manifest["bounds"],

    "method": {
        "root_level_dbz": 12,
        "connectivity": 8,
        "root_dilation_px": ROOT_DILATION,
        "minimum_root_area_px": MIN_ROOT_AREA
    },

    "frames": frames_out
}

OUT_JSON.write_text(
    json.dumps(
        payload,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# -------------------------------------------------------
# PREVIEW ULTIMO FRAME
# -------------------------------------------------------

last = frames_out[-1]

background = (
    PROC /
    f"frame_{last['frame']:02d}_clean.png"
)

preview = Image.open(
    background
).convert("RGBA")

draw = ImageDraw.Draw(
    preview
)

try:

    font = ImageFont.truetype(
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        12
    )

except:

    font = ImageFont.load_default()


important = [
    s
    for s in last["systems"]
    if (
        s["root_area_px"] >= 20
        or
        s["zmax_dbz"] >= 36
    )
]


for s in important:

    x1, y1, x2, y2 = s["bbox_px"]

    # caja sólo como ayuda diagnóstica
    draw.rectangle(
        [
            x1,
            y1,
            x2,
            y2
        ],
        outline=(
            255,
            255,
            255,
            170
        ),
        width=1
    )

    x = s["centroid_px"]["x"]
    y = s["centroid_px"]["y"]

    draw.ellipse(
        [
            x - 3,
            y - 3,
            x + 3,
            y + 3
        ],
        fill=(
            255,
            255,
            255,
            255
        )
    )

    txt = (
        f"S{s['rank']} "
        f"Zmax {s['zmax_dbz']} "
        f"A12 {s['root_area_px']}px\n"
        f"{s['centroid']['latitude']:.2f}, "
        f"{s['centroid']['longitude']:.2f}"
    )

    draw.text(
        (
            x + 5,
            y + 4
        ),
        txt,
        fill=(
            255,
            255,
            255,
            255
        ),
        font=font
    )


preview.save(
    OUT_IMG
)


print()
print("=== ULTIMO FRAME ===")

for s in important:

    print(
        f"S{s['rank']:02d} "
        f"A12={s['root_area_px']:5d}px "
        f"Zmax={s['zmax_dbz']:2d} "
        f"GPS="
        f"{s['centroid']['latitude']:.3f},"
        f"{s['centroid']['longitude']:.3f}"
    )


print()
print("JSON:", OUT_JSON)
print("Preview:", OUT_IMG)

