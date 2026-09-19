#!/usr/bin/env python3
from pathlib import Path
import hashlib, sys
root = Path(__file__).resolve().parents[1]
ios = root / "DanaSafeDeveloper"
checks=[]

def ok(name, cond):
    checks.append((name, bool(cond)))

content=(ios/'ContentView.swift').read_text()
model=(ios/'DanaSafeModel.swift').read_text()
api=(ios/'DanaSafeAPIClient.swift').read_text()
plist=(ios/'Info.plist').read_text()
project=(root/'DanaSafeDeveloper.xcodeproj/project.pbxproj').read_text()

forbidden=['localServerBaseURL','refreshFromLocalServer','checkHealth(baseURL:','serverHealth','Mac-IP:7117']
all_ios='\n'.join(p.read_text(errors='ignore') for p in ios.glob('*.swift'))
ok('no local runtime Swift symbols', not any(x in all_ios for x in forbidden))
ok('no local network permission', 'NSLocalNetworkUsageDescription' not in plist and 'NSAllowsLocalNetworking' not in plist)
ok('Cloudflare only runtime label', 'Cloudflare HTTPS only' in content and 'Local service", value: "DISABLED"' in content)
ok('only production HTTPS endpoint', 'https://danasafe-radar.firefritz.workers.dev' in api and 'http://' not in api)
ok('startup uses Cloudflare snapshot', 'await model.loadFromCloudflare()' in content)
ok('async refresh start supported', 'api.startRadarRefresh()' in model and 'statusCode == 202' in api)
ok('refresh-status polling supported', 'api.refreshStatus()' in model and 'radar/refresh-status' in api)
ok('valid newer snapshot is not rejected only for AEMET rollover', 'AEMET may advance by one slot' in model)
ok('monotonic snapshot guard', 'attempted to regress radar' in model)
ok('version 5.2.2 build 53', 'MARKETING_VERSION = 5.2.2;' in project and 'CURRENT_PROJECT_VERSION = 53;' in project)

# Golden meteorological products must remain identical to baseline manifest.
manifest = root/'Baseline/GOLDEN_PRODUCTS.sha256'
base = root/'Engine/Data/Radar/AEMET/NationalSequence/Processed'
if manifest.exists():
    good=True
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        h, rel = line.split(None,1)
        rel=rel.strip().lstrip('*')
        candidates=[root/rel, base/Path(rel).name]
        f=next((c for c in candidates if c.exists()),None)
        if f is None or hashlib.sha256(f.read_bytes()).hexdigest()!=h:
            good=False
            break
    ok('golden radar products unchanged', good)
else:
    ok('golden radar products unchanged', False)

for name,passed in checks:
    print(f"{'PASS' if passed else 'FAIL'}  {name}")
if not all(x[1] for x in checks): sys.exit(1)
print('DANASAFE 5.2.2 VERIFY: PASS')
