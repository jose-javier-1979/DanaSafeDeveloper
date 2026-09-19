from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json
import math

BASE = Path(__file__).resolve().parents[1]

SEQ = BASE / "Data" / "Radar" / "AEMET" / "NationalSequence"
PROC = SEQ / "Processed"

OBJECTS_FILE = PROC / "sequence_objects.json"

OUT_JSON = PROC / "radar_tracks.json"
OUT_IMG = PROC / "radar_tracking_preview.png"

data = json.loads(
    OBJECTS_FILE.read_text(encoding="utf-8")
)

frames = data["frames"]

INTERVAL_MIN = data["frame_interval_minutes"]

# ---------------------------------------------------------
# GEODESIA
# ---------------------------------------------------------

EARTH_KM = 6371.0088

def haversine_km(lat1, lon1, lat2, lon2):

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return EARTH_KM * c


def bearing_deg(lat1, lon1, lat2, lon2):

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)

    y = math.sin(dl) * math.cos(p2)

    x = (
        math.cos(p1) * math.sin(p2)
        -
        math.sin(p1)
        * math.cos(p2)
        * math.cos(dl)
    )

    b = math.degrees(
        math.atan2(y, x)
    )

    return (b + 360) % 360


# ---------------------------------------------------------
# GEOMETRIA
# ---------------------------------------------------------

def bbox_iou(a, b):

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0, ix2 - ix1 + 1)
    ih = max(0, iy2 - iy1 + 1)

    inter = iw * ih

    area_a = (
        max(0, ax2 - ax1 + 1)
        *
        max(0, ay2 - ay1 + 1)
    )

    area_b = (
        max(0, bx2 - bx1 + 1)
        *
        max(0, by2 - by1 + 1)
    )

    union = area_a + area_b - inter

    if union <= 0:
        return 0.0

    return inter / union


def pixel_distance(a, b):

    ax = a["centroid_px"]["x"]
    ay = a["centroid_px"]["y"]

    bx = b["centroid_px"]["x"]
    by = b["centroid_px"]["y"]

    return math.hypot(
        bx - ax,
        by - ay
    )


# ---------------------------------------------------------
# SCORE DE EMPAREJAMIENTO
# ---------------------------------------------------------

def match_score(a, b):

    if a["level_dbz"] != b["level_dbz"]:
        return None

    lat1 = a["centroid"]["latitude"]
    lon1 = a["centroid"]["longitude"]

    lat2 = b["centroid"]["latitude"]
    lon2 = b["centroid"]["longitude"]

    dkm = haversine_km(
        lat1, lon1,
        lat2, lon2
    )

    dpx = pixel_distance(a, b)

    # Límite amplio inicial.
    # Luego lo afinaremos con los resultados.
    if dkm > 80:
        return None

    if dpx > 35:
        return None

    area1 = max(a["area_px"], 1)
    area2 = max(b["area_px"], 1)

    area_ratio = min(
        area1,
        area2
    ) / max(
        area1,
        area2
    )

    iou = bbox_iou(
        a["bbox_px"],
        b["bbox_px"]
    )

    # Score menor = mejor
    score = (
        dkm * 1.0
        +
        dpx * 0.8
        +
        (1 - area_ratio) * 15
        -
        iou * 20
    )

    return {
        "score": score,
        "distance_km": dkm,
        "distance_px": dpx,
        "area_ratio": area_ratio,
        "bbox_iou": iou
    }


# ---------------------------------------------------------
# TRACKING
# ---------------------------------------------------------

tracks = {}
object_to_track = {}

next_track_id = 1

# Primer frame: cada objeto inicia track
for obj in frames[0]["objects"]:

    tid = f"TRACK_{next_track_id:05d}"
    next_track_id += 1

    tracks[tid] = [obj]
    object_to_track[obj["id"]] = tid


# Frames siguientes
for fi in range(len(frames) - 1):

    current = frames[fi]["objects"]
    nxt = frames[fi + 1]["objects"]

    candidates = []

    for a in current:

        for b in nxt:

            result = match_score(a, b)

            if result is None:
                continue

            candidates.append(
                (
                    result["score"],
                    a,
                    b,
                    result
                )
            )

    candidates.sort(
        key=lambda x: x[0]
    )

    used_a = set()
    used_b = set()

    accepted = 0

    for score, a, b, metrics in candidates:

        if a["id"] in used_a:
            continue

        if b["id"] in used_b:
            continue

        tid = object_to_track.get(
            a["id"]
        )

        if tid is None:
            continue

        tracks[tid].append(b)

        object_to_track[b["id"]] = tid

        used_a.add(a["id"])
        used_b.add(b["id"])

        accepted += 1

    # Objetos nuevos
    for b in nxt:

        if b["id"] not in used_b:

            tid = f"TRACK_{next_track_id:05d}"
            next_track_id += 1

            tracks[tid] = [b]
            object_to_track[b["id"]] = tid

    print(
        f"Frame {fi+1:02d}->{fi+2:02d}: "
        f"{accepted} asociaciones"
    )


# ---------------------------------------------------------
# CALCULAR CINEMATICA
# ---------------------------------------------------------

track_records = []

for tid, points in tracks.items():

    if len(points) < 2:
        continue

    movements = []

    for a, b in zip(
        points[:-1],
        points[1:]
    ):

        lat1 = a["centroid"]["latitude"]
        lon1 = a["centroid"]["longitude"]

        lat2 = b["centroid"]["latitude"]
        lon2 = b["centroid"]["longitude"]

        dkm = haversine_km(
            lat1, lon1,
            lat2, lon2
        )

        hours = INTERVAL_MIN / 60.0

        speed = (
            dkm / hours
            if hours > 0
            else 0
        )

        bearing = bearing_deg(
            lat1, lon1,
            lat2, lon2
        )

        area_change = (
            b["area_px"] - a["area_px"]
        )

        movements.append({
            "from_frame": a["frame"],
            "to_frame": b["frame"],
            "distance_km": round(dkm, 3),
            "speed_kmh": round(speed, 2),
            "bearing_deg": round(bearing, 1),
            "area_change_px": area_change
        })

    mean_speed = sum(
        m["speed_kmh"]
        for m in movements
    ) / len(movements)

    track_records.append({
        "track_id": tid,
        "level_dbz": points[0]["level_dbz"],
        "frames": len(points),

        "start": {
            "frame": points[0]["frame"],
            "timestamp": points[0]["timestamp"],
            "centroid": points[0]["centroid"]
        },

        "end": {
            "frame": points[-1]["frame"],
            "timestamp": points[-1]["timestamp"],
            "centroid": points[-1]["centroid"]
        },

        "mean_speed_kmh": round(
            mean_speed,
            2
        ),

        "movements": movements,

        "objects": [
            p["id"]
            for p in points
        ]
    })


# ---------------------------------------------------------
# GUARDAR JSON
# ---------------------------------------------------------

result = {
    "schema": {
        "name": "DanaSafeRadarTracks",
        "version": "0.1.0"
    },

    "provider": "AEMET",

    "frame_interval_minutes": INTERVAL_MIN,

    "track_count": len(track_records),

    "tracks": track_records
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
# VISUALIZACION
# ---------------------------------------------------------

background_file = (
    PROC /
    f"frame_{frames[-1]['frame']:02d}_clean.png"
)

img = Image.open(
    background_file
).convert("RGBA")

draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype(
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        12
    )
except:
    font = ImageFont.load_default()


# Sólo dibujamos tracks relativamente persistentes
visual_tracks = [
    (tid, pts)
    for tid, pts in tracks.items()
    if len(pts) >= 4
]


for tid, pts in visual_tracks:

    xy = [
        (
            p["centroid_px"]["x"],
            p["centroid_px"]["y"]
        )
        for p in pts
    ]

    if len(xy) < 2:
        continue

    # trayectoria
    draw.line(
        xy,
        fill=(255,255,255,220),
        width=2
    )

    # centroides
    for x, y in xy:
        r = 2

        draw.ellipse(
            [
                x-r, y-r,
                x+r, y+r
            ],
            fill=(255,255,255,255)
        )

    # flecha final
    x1, y1 = xy[-2]
    x2, y2 = xy[-1]

    dx = x2 - x1
    dy = y2 - y1

    angle = math.atan2(
        dy,
        dx
    )

    arrow = 7

    a1 = angle + math.radians(150)
    a2 = angle - math.radians(150)

    p1 = (
        x2 + arrow * math.cos(a1),
        y2 + arrow * math.sin(a1)
    )

    p2 = (
        x2 + arrow * math.cos(a2),
        y2 + arrow * math.sin(a2)
    )

    draw.line(
        [p1, (x2,y2), p2],
        fill=(255,255,255,255),
        width=2
    )


# Etiquetamos sólo los tracks principales para no saturar
major = []

for tid, pts in visual_tracks:

    last = pts[-1]

    if last["area_px"] >= 30:

        lat = last["centroid"]["latitude"]
        lon = last["centroid"]["longitude"]

        rec = next(
            (
                r for r in track_records
                if r["track_id"] == tid
            ),
            None
        )

        if rec:
            major.append(
                (
                    last["area_px"],
                    tid,
                    pts,
                    rec
                )
            )


major.sort(reverse=True)

for _, tid, pts, rec in major[:20]:

    last = pts[-1]

    x = last["centroid_px"]["x"]
    y = last["centroid_px"]["y"]

    lat = last["centroid"]["latitude"]
    lon = last["centroid"]["longitude"]

    label = (
        f"{tid[-3:]} "
        f"Z{last['level_dbz']} "
        f"{rec['mean_speed_kmh']:.0f}km/h\n"
        f"{lat:.3f},{lon:.3f}"
    )

    draw.text(
        (x + 5, y + 5),
        label,
        font=font,
        fill=(255,255,255,255)
    )


img.save(
    OUT_IMG
)

print()
print("=== DANASAFE TRACKING ===")
print("Tracks con >=2 frames:", len(track_records))
print("Tracks visualizados >=4 frames:", len(visual_tracks))
print("JSON:", OUT_JSON)
print("Imagen:", OUT_IMG)

