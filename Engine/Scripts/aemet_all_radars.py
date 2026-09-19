from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.parse
import subprocess
import json
import time

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "Data" / "Radar" / "AEMET" / "Regional"
OUT.mkdir(parents=True, exist_ok=True)

RADARS = {
    "am": "Almeria",
    "sa": "Asturias",
    "pm": "Illes Balears",
    "ba": "Barcelona",
    "cc": "Caceres",
    "co": "A Coruna",
    "ma": "Madrid",
    "ml": "Malaga",
    "mu": "Murcia",
    "vd": "Palencia",
    "ca": "Las Palmas",
    "se": "Sevilla",
    "va": "Valencia",
    "ss": "Vizcaya",
    "za": "Zaragoza"
}

apikey = subprocess.check_output(
    [
        "security",
        "find-generic-password",
        "-a",
        subprocess.check_output(["whoami"], text=True).strip(),
        "-s",
        "DanaSafe-AEMET",
        "-w"
    ],
    text=True
).strip()

results = []

for code, name in RADARS.items():

    endpoint = (
        "https://opendata.aemet.es/opendata/api/"
        f"red/radar/regional/{code}"
        "?api_key=" + urllib.parse.quote(apikey)
    )

    try:
        with urllib.request.urlopen(endpoint, timeout=30) as r:
            response = json.loads(
                r.read().decode("utf-8", errors="replace")
            )

        estado = response.get("estado")
        data_url = response.get("datos")

        if estado == 200 and data_url:

            with urllib.request.urlopen(data_url, timeout=30) as r:
                content = r.read()
                content_type = r.headers.get("Content-Type")

            radar_dir = OUT / code
            radar_dir.mkdir(exist_ok=True)

            stamp = datetime.now().astimezone().strftime(
                "%Y%m%d_%H%M%S"
            )

            historical = radar_dir / f"{code}_{stamp}.gif"
            latest = radar_dir / f"{code}_actual.gif"

            historical.write_bytes(content)
            latest.write_bytes(content)

            print(
                f"OK   {code.upper():2s} "
                f"{name:15s} "
                f"{len(content):7d} bytes"
            )

            results.append({
                "code": code,
                "name": name,
                "status": "online",
                "bytes": len(content),
                "content_type": content_type,
                "file": str(latest)
            })

        else:
            print(
                f"FAIL {code.upper():2s} "
                f"{name:15s} estado={estado}"
            )

            results.append({
                "code": code,
                "name": name,
                "status": "unavailable",
                "aemet_status": estado
            })

    except Exception as e:

        print(
            f"ERR  {code.upper():2s} "
            f"{name:15s} {e}"
        )

        results.append({
            "code": code,
            "name": name,
            "status": "error",
            "error": str(e)
        })

    time.sleep(0.25)

summary = {
    "generated_at":
        datetime.now().astimezone().isoformat(),
    "radars": results
}

summary_file = OUT / "radar_status.json"

summary_file.write_text(
    json.dumps(
        summary,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

online = [
    r for r in results
    if r["status"] == "online"
]

print()
print("=== DANASAFE RADAR NETWORK ===")
print("Radares consultados:", len(results))
print("Radares disponibles:", len(online))
print(
    "Codigos:",
    " ".join(
        r["code"].upper()
        for r in online
    )
)
print("Estado:", summary_file)
