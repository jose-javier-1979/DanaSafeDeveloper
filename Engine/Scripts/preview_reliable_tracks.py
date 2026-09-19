from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json
import math

BASE = Path(__file__).resolve().parents[1]
PROC = BASE / "Data/Radar/AEMET/NationalSequence/Processed"

TRACKS_FILE = PROC / "radar_tracks.json"
OBJECTS_FILE = PROC / "sequence_objects.json"

OUT = PROC / "radar_tracking_reliable.png"
OUTJSON = PROC / "reliable_tracks.json"

tracks_data = json.loads(
    TRACKS_FILE.read_text(encoding="utf-8")
)

objects_data = json.loads(
    OBJECTS_FILE.read_text(encoding="utf-8")
)

# -----------------------------------------------------
# Índice objeto -> datos completos
# -----------------------------------------------------

objects = {}

for frame in objects_data["frames"]:
    for obj in frame["objects"]:
        objects[obj["id"]] = obj

# -----------------------------------------------------
# FILTRO DE FIABILIDAD
# -----------------------------------------------------

MAX_STEP_KMH = 120.0
MIN_FRAMES = 5

reliable = []

for t in tracks_data["tracks"]:

    if t["frames"] < MIN_FRAMES:
        continue

    speeds = [
        m["speed_kmh"]
        for m in t["movements"]
    ]

    if not speeds:
        continue

    if max(speeds) > MAX_STEP_KMH:
        continue

    objlist = [
        objects[o]
        for o in t["objects"]
        if o in objects
    ]

    if len(objlist) < MIN_FRAMES:
        continue

    reliable.append({
        "track": t,
        "objects": objlist
    })

print("=== DANASAFE RELIABLE TRACKS ===")
print("Tracks originales:", len(tracks_data["tracks"]))
print("Persistencia mínima:", MIN_FRAMES)
print("Máximo salto:", MAX_STEP_KMH, "km/h")
print("Tracks fiables:", len(reliable))

# -----------------------------------------------------
# ESTADÍSTICA
# -----------------------------------------------------

if reliable:

    means = sorted(
        r["track"]["mean_speed_kmh"]
        for r in reliable
    )

    print()
    print("Velocidad media mínima:", round(means[0],1))
    print("Velocidad media mediana:", round(means[len(means)//2],1))
    print("Velocidad media máxima:", round(means[-1],1))

# -----------------------------------------------------
# GUARDAR
# -----------------------------------------------------

out_data = {
    "schema": {
        "name": "DanaSafeReliableTracks",
        "version": "0.1.0"
    },
    "criteria": {
        "minimum_frames": MIN_FRAMES,
        "maximum_step_speed_kmh": MAX_STEP_KMH
    },
    "tracks": [
        r["track"]
        for r in reliable
    ]
}

OUTJSON.write_text(
    json.dumps(
        out_data,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

# -----------------------------------------------------
# IMAGEN
# -----------------------------------------------------

last_frame = max(
    f["frame"]
    for f in objects_data["frames"]
)

background = (
    PROC /
    f"frame_{last_frame:02d}_clean.png"
)

img = Image.open(background).convert("RGBA")
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype(
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        11
    )
except:
    font = ImageFont.load_default()

# Primero dibujamos todos los tracks fiables
for r in reliable:

    pts = r["objects"]

    xy = [
        (
            p["centroid_px"]["x"],
            p["centroid_px"]["y"]
        )
        for p in pts
    ]

    if len(xy) < 2:
        continue

    draw.line(
        xy,
        fill=(255,255,255,210),
        width=2
    )

    # Punto inicial
    x0, y0 = xy[0]

    draw.ellipse(
        [x0-2,y0-2,x0+2,y0+2],
        outline=(255,255,255,220),
        width=1
    )

    # Flecha final
    x1, y1 = xy[-2]
    x2, y2 = xy[-1]

    draw.line(
        [(x1,y1),(x2,y2)],
        fill=(255,255,255,255),
        width=3
    )

    angle = math.atan2(
        y2-y1,
        x2-x1
    )

    L = 8

    for da in (
        math.radians(150),
        math.radians(-150)
    ):
        ax = x2 + L * math.cos(angle + da)
        ay = y2 + L * math.sin(angle + da)

        draw.line(
            [(x2,y2),(ax,ay)],
            fill=(255,255,255,255),
            width=2
        )

# -----------------------------------------------------
# Sólo etiquetamos los sistemas más importantes
# -----------------------------------------------------

label_candidates = []

for r in reliable:

    pts = r["objects"]

    # Preferimos los que llegan al último frame
    if pts[-1]["frame"] != last_frame:
        continue

    last = pts[-1]

    # peso visual: área * intensidad * persistencia
    score = (
        last["area_px"]
        *
        max(last["level_dbz"], 12)
        *
        len(pts)
    )

    label_candidates.append(
        (score, r)
    )

label_candidates.sort(
    key=lambda x: x[0],
    reverse=True
)

for _, r in label_candidates[:12]:

    t = r["track"]
    p = r["objects"][-1]

    x = p["centroid_px"]["x"]
    y = p["centroid_px"]["y"]

    lat = p["centroid"]["latitude"]
    lon = p["centroid"]["longitude"]

    txt = (
        f"{t['track_id'][-3:]} "
        f"Z{p['level_dbz']} "
        f"{t['mean_speed_kmh']:.0f} km/h\n"
        f"{lat:.2f}, {lon:.2f}"
    )

    draw.text(
        (x+5,y+4),
        txt,
        font=font,
        fill=(255,255,255,255)
    )

img.save(OUT)

print()
print("JSON:", OUTJSON)
print("Imagen:", OUT)

