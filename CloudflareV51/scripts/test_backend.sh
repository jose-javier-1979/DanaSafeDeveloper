#!/bin/sh
set -eu
BASE="${1:-https://danasafe-radar.firefritz.workers.dev}"
echo "== Root =="; curl -fsS "$BASE/"; echo
echo "== Health before =="; curl -fsS "$BASE/health"; echo
echo "== AEMET latest =="; curl -fsS "$BASE/aemet/latest-image-info"; echo
echo "== Refresh =="; curl -fsS -X POST -H 'Cache-Control: no-store' "$BASE/radar/refresh" > /tmp/danasafe-v51-snapshot.json
echo "Snapshot saved to /tmp/danasafe-v51-snapshot.json"
echo "== Health after =="; curl -fsS "$BASE/health"; echo
python3 - <<'PY'
import json
p=json.load(open('/tmp/danasafe-v51-snapshot.json'))
print('radar_timestamp:',p.get('radar_timestamp'))
print('frames:',len(p.get('radar',{}).get('frames',[])))
print('tracks:',len(p.get('tracks',{}).get('tracks',[])))
print('contour timestamp:',p.get('contours',{}).get('timestamp'))
PY
