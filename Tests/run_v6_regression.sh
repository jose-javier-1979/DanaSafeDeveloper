#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT/Engine"
python3 Scripts/process_compo_sequence.py
python3 Scripts/build_radar_systems_v03.py
python3 Scripts/track_radar_sequence.py
python3 Scripts/preview_reliable_tracks.py
python3 Scripts/sync_latest_frame.py
python3 Scripts/national_marching_squares.py
python3 Scripts/build_nowcast_v6.py
python3 Scripts/publish_live_snapshot.py
cd "$ROOT"
cp Engine/Data/Radar/AEMET/NationalSequence/Processed/radar_nowcast_v6.json DanaSafeDeveloper/radar_nowcast_v6.json
python3 Tests/verify_baseline.py
python3 Tests/verify_v6.py
