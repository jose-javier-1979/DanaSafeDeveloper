#!/bin/zsh
set -e
BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE"

echo "=================================================="
echo " DANASAFE V3.2 · MANUAL AEMET + ALGORITHM UPDATE"
echo "=================================================="
python3 Scripts/download_compo_sequence.py
python3 Scripts/process_compo_sequence.py
python3 Scripts/build_radar_systems_v03.py
python3 Scripts/track_radar_sequence.py
python3 Scripts/preview_reliable_tracks.py
python3 Scripts/sync_latest_frame.py
python3 Scripts/national_marching_squares.py
python3 Scripts/build_nowcast_v6.py
python3 Scripts/publish_live_snapshot.py

echo "=================================================="
echo " DANASAFE V3.2 UPDATE COMPLETED"
echo "=================================================="
