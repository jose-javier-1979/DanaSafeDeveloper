from datetime import datetime
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "Data"

DATA.mkdir(parents=True, exist_ok=True)

state = {
    "system": "DanaSafe",
    "version": "0.1",
    "timestamp": datetime.now().astimezone().isoformat(),
    "sources": {
        "radar": {
            "source": "AEMET",
            "status": "pending"
        },
        "hydrology": {
            "source": "SAIH",
            "status": "pending"
        },
        "terrain": {
            "source": "IGN/CNIG",
            "status": "pending"
        },
        "sensors": {
            "source": "DanaSafe local network",
            "status": "pending"
        }
    },
    "prediction": {
        "flood_risk": None,
        "eta_minutes": None,
        "confidence": None
    }
}

outfile = DATA / "current_state.json"

with outfile.open("w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print("DANASAFE PIPELINE OK")
print("Archivo:", outfile)
print()
print(json.dumps(state, ensure_ascii=False, indent=2))
