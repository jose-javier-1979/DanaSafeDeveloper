#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENGINE="$ROOT/Engine"

cd "$ENGINE"
python Scripts/process_compo_sequence.py
python Scripts/build_radar_systems_v03.py
python Scripts/track_radar_sequence.py
python Scripts/preview_reliable_tracks.py
python Scripts/sync_latest_frame.py
python Scripts/national_marching_squares.py
python Scripts/publish_live_snapshot.py

cd "$ROOT"
python Tests/verify_baseline.py

python - <<'PY'
from pathlib import Path
import json
root = Path.cwd()
p = root / 'Engine/Data/Published/danasafe_live_snapshot.json'
s = json.loads(p.read_text())
assert len(s['radar']['frames']) == 10
assert s['radar']['frames'][-1]['timestamp'] == s['radar_timestamp']
assert s['contours']['timestamp'] == s['radar_timestamp']
assert s['freshness']['radar_timestamp'] == s['radar_timestamp']
assert s['freshness']['hydrology_retrieved_at'] == s['hydrology']['retrieved_at']
assert s['freshness']['hydrology_refresh_coupled_to_radar'] is False
print('ATOMIC SNAPSHOT CONTRACT: PASS')
PY
