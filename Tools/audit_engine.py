#!/usr/bin/env python3
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "Engine/Data/Radar/AEMET/NationalSequence/Processed/radar_systems_v03.json"
d = json.loads(p.read_text(encoding="utf-8"))
print("DanaSafe engine audit")
for frame in d.get("frames", []):
    systems = frame.get("systems", [])
    sig = [s for s in systems if s.get("root_area_px",0) >= 20 or s.get("zmax_dbz",0) >= 36]
    print(frame.get("frame"), frame.get("timestamp"), "real=", len(systems), "significant=", len(sig))
