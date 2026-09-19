#!/bin/sh
set -eu
BASE="${1:-https://danasafe-radar-v82-candidate.firefritz.workers.dev}"
echo "== Root =="; curl -fsS "$BASE/"; echo
echo "== Health before =="; curl -fsS "$BASE/health"; echo
echo "== AEMET latest =="; curl -fsS "$BASE/aemet/latest-image-info"; echo
echo "== Refresh =="; curl -fsS -X POST -H 'Cache-Control: no-store' "$BASE/radar/refresh" > /tmp/danasafe-v82-snapshot.json
echo "== History =="; curl -fsS "$BASE/radar/history?limit=5" > /tmp/danasafe-v82-history.json; cat /tmp/danasafe-v82-history.json; echo
python3 - <<'PY'
import json
s=json.load(open('/tmp/danasafe-v82-snapshot.json'))
h=json.load(open('/tmp/danasafe-v82-history.json'))
ts=s['radar_timestamp']
assert len(s['radar']['frames']) == 10
assert any(c.get('radar_timestamp') == ts for c in h.get('cycles', []))
print('snapshot/history:', ts, 'PASS')
PY
