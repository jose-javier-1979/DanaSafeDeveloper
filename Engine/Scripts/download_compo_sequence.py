#!/usr/bin/env python3
import json
import os
import urllib.request
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = "https://www.aemet.es"
TIMELINE_URL = BASE + "/es/api-eltiempo/radar/timeline/compo/PB"
TIMELINE = Path("Data/Radar/AEMET/WebAPI/timeline_compo_PB.json")
OUT = Path("Data/Radar/AEMET/NationalSequence")
MADRID = ZoneInfo("Europe/Madrid")

OUT.mkdir(parents=True, exist_ok=True)
TIMELINE.parent.mkdir(parents=True, exist_ok=True)


def parse_aemet_date(raw: str) -> datetime:
    return datetime.fromisoformat(raw).astimezone(MADRID)


def fetch_timeline() -> object:
    req = urllib.request.Request(TIMELINE_URL, headers={"User-Agent": "DanaSafe/3.2 Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    TIMELINE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def main() -> int:
    checked_at = datetime.now(MADRID)
    data = fetch_timeline()
    root = data[0] if isinstance(data, list) else data
    elements = sorted(root["Elementos"], key=lambda e: parse_aemet_date(e["Fecha"]))
    if len(elements) < 10:
        raise RuntimeError(f"AEMET timeline has only {len(elements)} frames; DanaSafe requires 10")

    # V6 supports a pinned target supplied by the Worker/Container. This removes the
    # race where AEMET publishes a newer slot after the Worker selected its target.
    target_raw = os.environ.get("DANASAFE_TARGET_TIMESTAMP")
    if target_raw:
        target = parse_aemet_date(target_raw)
        target_index = next((i for i, e in enumerate(elements) if parse_aemet_date(e["Fecha"]) == target), None)
        if target_index is None:
            raise RuntimeError(f"Requested AEMET target is not present in timeline: {target_raw}")
        if target_index < 9:
            raise RuntimeError(f"Requested AEMET target has insufficient history for 10 frames: {target_raw}")
        frames = elements[target_index - 9: target_index + 1]
    else:
        frames = elements[-10:]
    parsed = [parse_aemet_date(e["Fecha"]) for e in frames]
    for previous, current in zip(parsed, parsed[1:]):
        if int((current - previous).total_seconds()) != 600:
            raise RuntimeError(f"AEMET latest sequence is not consecutive at 10-minute cadence: {previous} -> {current}")

    latest_available = parsed[-1]
    print("=== DANASAFE MANUAL AEMET REFRESH ===")
    print("Checked at:", checked_at.isoformat())
    print("Latest AEMET frame:", latest_available.isoformat())

    manifest = []
    for i, e in enumerate(frames, 1):
        fecha = e["Fecha"]
        filename = e["Nombre fichero"]
        url = BASE + "/es/api-eltiempo/radar/imagen-radar/compo/" + filename
        local_name = f"{i:02d}_{filename}"
        dst = OUT / local_name
        req = urllib.request.Request(url, headers={"User-Agent": "DanaSafe/3.2 Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read()
        if len(content) < 1000:
            raise RuntimeError(f"AEMET frame {filename} is unexpectedly small ({len(content)} bytes)")
        dst.write_bytes(content)
        manifest.append({
            "frame": i,
            "fecha": fecha,
            "filename": filename,
            "local_file": str(dst),
            "url": url,
        })
        print(f"{i:02d}  {fecha}  {filename}  {len(content)} bytes")

    payload = {
        "provider": "AEMET",
        "product": "Composicion radar",
        "region": "Penbal",
        "frame_interval_minutes": 10,
        "refresh": {
            "mode": "targeted" if target_raw else "manual",
            "checked_at": checked_at.isoformat(),
            "latest_aemet_slot": latest_available.isoformat(),
            "requested_target": target_raw,
        },
        "bounds": {"west": -16.08, "east": 12.14, "south": 27.22, "north": 51.30},
        "frames": manifest,
    }

    tmp = OUT / "sequence_manifest.json.tmp"
    final = OUT / "sequence_manifest.json"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(final)
    print("Latest AEMET manifest:", final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
