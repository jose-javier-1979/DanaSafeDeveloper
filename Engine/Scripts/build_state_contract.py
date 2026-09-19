from pathlib import Path
from datetime import datetime
import json

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "Data"
RADAR = DATA / "Radar" / "AEMET"

SAIH_FILE = DATA / "saih_stations.json"
RADAR_FILE = RADAR / "stage2_cells.json"
OUT = DATA / "DanaSafe_state.json"

def load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

saih = load_json(SAIH_FILE)
radar = load_json(RADAR_FILE)

# ------------------------------------------------------------
# HIDROLOGIA
# ------------------------------------------------------------

stations = []

if saih:
    for s in saih.get("stations", []):
        stations.append({
            "id": s.get("id"),
            "name": s.get("station"),
            "variable": s.get("variable"),

            "location": {
                "latitude": None,
                "longitude": None,
                "elevation_m": None
            },

            "observation": {
                "flow_m3s": s.get("flow_m3s"),
                "time": s.get("time"),
                "status": s.get("status"),
                "observed": s.get("observed", True)
            },

            "thresholds": s.get("thresholds_m3s", {}),

            "basin": None,
            "subbasin": None,

            "source": {
                "provider": "SAIH-CHJ",
                "type": "observed"
            }
        })

# ------------------------------------------------------------
# RADAR
# ------------------------------------------------------------

radar_systems = []

if radar:
    for cell in radar.get("cells", []):

        radar_systems.append({
            "id": cell.get("id"),

            "radar": {
                "provider": "AEMET",
                "radar_code": "MU",
                "product": "PPI-Z",
                "period_minutes": 10
            },

            "geometry": {
                "area_px": cell.get("area_px"),
                "bbox_px": cell.get("bbox"),

                "centroid_px": cell.get("centroid"),

                "reflectivity_centroid_px":
                    cell.get("reflectivity_centroid")
            },

            "reflectivity": {
                "zmax_dbz": cell.get("zmax_dbz"),
                "zmean_dbz": cell.get("zmean_dbz"),
                "histogram": cell.get("dbz_histogram")
            },

            "contours": [],

            "motion": {
                "velocity_px_min": None,
                "direction_deg": None,
                "acceleration_px_min2": None
            },

            "geolocation": {
                "centroid": {
                    "latitude": None,
                    "longitude": None
                }
            },

            "terrain": {
                "mean_elevation_m": None,
                "max_elevation_m": None,
                "mean_slope_deg": None
            },

            "hydrological_context": {
                "affected_basins": [],
                "affected_subbasins": [],
                "downstream_station_ids": [],
                "downstream_reservoir_ids": []
            }
        })

# ------------------------------------------------------------
# CONTRATO MAESTRO
# ------------------------------------------------------------

state = {
    "schema": {
        "name": "DanaSafeState",
        "version": "1.0.0"
    },

    "generated_at": datetime.now().astimezone().isoformat(),

    "system": {
        "name": "DanaSafe",
        "status": "prototype"
    },

    "sources": {
        "radar": {
            "provider": "AEMET",
            "status": "online",
            "product": "PPI-Z",
            "radar_code": "MU",
            "update_interval_minutes": 10
        },

        "hydrology": {
            "provider": "SAIH-CHJ",
            "status": "online",
            "station_count": len(stations)
        },

        "reservoirs": {
            "provider": "SAIH / MITECO / embalses.net",
            "status": "pending"
        },

        "terrain": {
            "provider": "IGN/CNIG",
            "status": "pending"
        },

        "sensors": {
            "provider": "DanaSafe",
            "status": "pending"
        }
    },

    "radar_systems": radar_systems,

    "hydrology": {
        "stations": stations,
        "reservoirs": []
    },

    "terrain": {
        "basins": [],
        "subbasins": []
    },

    "urban_sensors": [],

    "prediction": {
        "flood_risk": [],
        "hydrological_eta": [],
        "confidence": None
    }
}

OUT.write_text(
    json.dumps(state, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("=== DANASAFE DATA CONTRACT ===")
print("Schema:", state["schema"]["version"])
print("Radar systems:", len(radar_systems))
print("SAIH stations:", len(stations))
print("Output:", OUT)

# Validacion minima
required = [
    "schema",
    "generated_at",
    "sources",
    "radar_systems",
    "hydrology",
    "terrain",
    "urban_sensors",
    "prediction"
]

missing = [k for k in required if k not in state]

if missing:
    print("ERROR: faltan campos:", missing)
    raise SystemExit(1)

print("VALIDACION: OK")
