#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, plistlib, re, sys
ROOT=Path(__file__).resolve().parents[1]
errors=[]
def check(name, cond):
    if not cond: errors.append(name)
def sha(p):
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

ios=ROOT/'DanaSafeDeveloper'
api=(ios/'DanaSafeAPIClient.swift').read_text()
model=(ios/'DanaSafeModel.swift').read_text()
content=(ios/'ContentView.swift').read_text()
intents=(ios/'DanaSafeIntents.swift').read_text()
pbx=(ROOT/'DanaSafeDeveloper.xcodeproj/project.pbxproj').read_text()
plist=plistlib.loads((ios/'Info.plist').read_bytes())

check('production endpoint changed', 'https://danasafe-radar.firefritz.workers.dev' in api)
check('unexpected alternate worker endpoint', 'danasafe-radar-v6' not in api and 'danasafe-radar-v61' not in api)
check('local HTTP runtime found', 'http://' not in api)
check('local network entitlement/usage found', 'NSLocalNetworkUsageDescription' not in plist and 'NSAllowsLocalNetworking' not in plist)
check('async 202 flow missing', 'response.statusCode == 202' in api and 'api.refreshStatus()' in model and 'radar/refresh-status' in api)
check('snapshot regression guard missing', 'attempted to regress radar' in model)
check('10-frame validation missing', 'snapshot.radar.frames.count == 10' in model)
check('nowcast timestamp coherence missing', 'nowcast.radarTimestamp != snapshot.radarTimestamp' in model)
check('stale nowcast resource file remains', not (ios/'radar_nowcast_v6.json').exists())
check('stale nowcast remains in Xcode resources', 'radar_nowcast_v6.json' not in pbx)
check('legacy local server helper remains', not (ROOT/'Tools/local_danasafe_server.py').exists())
check('legacy local start helper remains', not (ROOT/'Tools/start_danasafe_dev.sh').exists())
check('wrong marketing version', plist.get('CFBundleShortVersionString')=='6.4' and 'MARKETING_VERSION = 6.4;' in pbx)
check('wrong build', plist.get('CFBundleVersion')=='64' and 'CURRENT_PROJECT_VERSION = 64;' in pbx)
check('hardcoded worker version heading remains', 'Cloudflare V5.2.1 · frozen validated backend' not in content)
check('dynamic worker version UI missing', 'model.cloudflareVersion' in content)
check('wrong user agent', 'DanaSafe-iOS/6.4-production-frozen' in api)
check('old app version text remains', 'DanaSafe 6.3' not in '\n'.join([api,model,content,intents,(ios/'NowcastView.swift').read_text()]))
check('experimental CloudflareV6 tree present', not (ROOT/'CloudflareV6').exists())

# Frozen worker manifest must match actual tree.
manifest=ROOT/'WORKER_PRODUCTION_FROZEN_SHA256.txt'
check('worker manifest missing', manifest.exists())
if manifest.exists():
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        digest, rel=line.split(None,1)
        p=ROOT/rel.strip().lstrip('*')
        if not p.exists() or sha(p)!=digest:
            errors.append(f'frozen worker mismatch: {rel}')

# JSON fixtures must parse.
for p in ios.glob('*.json'):
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'invalid JSON {p.name}: {e}')

if errors:
    print('DANASAFE 6.4 VERIFY: FAIL')
    for e in errors: print(' -', e)
    sys.exit(1)
print('DANASAFE 6.4 VERIFY: PASS')
