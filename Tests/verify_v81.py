#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, plistlib, re, subprocess, sys, tempfile, shutil
ROOT=Path(__file__).resolve().parents[1]
errors=[]
def check(label, cond):
    if not cond: errors.append(label)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
ios=ROOT/'DanaSafeDeveloper'
pbx=(ROOT/'DanaSafeDeveloper.xcodeproj/project.pbxproj').read_text()
api=(ios/'DanaSafeAPIClient.swift').read_text()
model=(ios/'DanaSafeModel.swift').read_text()
view=(ios/'NowcastView.swift').read_text()
content=(ios/'ContentView.swift').read_text()
intents=(ios/'DanaSafeIntents.swift').read_text()
plist=plistlib.loads((ios/'Info.plist').read_bytes())
privacy=plistlib.loads((ios/'PrivacyInfo.xcprivacy').read_bytes())
check('marketing version', pbx.count('MARKETING_VERSION = 8.1;')==2)
check('build number', pbx.count('CURRENT_PROJECT_VERSION = 81;')==2)
check('bundle id', pbx.count('PRODUCT_BUNDLE_IDENTIFIER = com.firefritz.DanaSafeDeveloperV81;')==2)
check('Info version variable', plist.get('CFBundleShortVersionString')=='$(MARKETING_VERSION)')
check('Info build variable', plist.get('CFBundleVersion')=='$(CURRENT_PROJECT_VERSION)')
check('display name', plist.get('CFBundleDisplayName')=='DanaSafe')
check('location explanation', 'ubicación' in plist.get('NSLocationWhenInUseUsageDescription','').lower())
check('privacy tracking false', privacy.get('NSPrivacyTracking') is False)
check('privacy no collected data', privacy.get('NSPrivacyCollectedDataTypes')==[])
check('privacy no accessed required-reason APIs', privacy.get('NSPrivacyAccessedAPITypes')==[])
check('assets catalog', (ios/'Assets.xcassets').is_dir())
check('app icon image', (ios/'Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png').exists())
check('app icon project setting', pbx.count('ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;')==2)
check('accent project setting', pbx.count('ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME = AccentColor;')==2)
check('production endpoint', 'https://danasafe-radar.firefritz.workers.dev' in api)
check('no local network URL in iOS client', 'http://' not in api and 'localhost' not in api and '127.0.0.1' not in api)
check('sync refresh support', 'response.statusCode == 200' in api)
check('async refresh compatibility', 'response.statusCode == 202' in api and 'radar/refresh-status' in api and 'api.refreshStatus()' in model)
check('10-frame validation', 'snapshot.radar.frames.count == 10' in model)
check('nowcast timestamp validation', 'nowcast.radarTimestamp != snapshot.radarTimestamp' in model)
check('nowcast fallback model', 'NowcastBuilderV7.build(from: snapshot.radar)' in model)
check('nowcast fallback intents', 'NowcastBuilderV7.build(from: snapshot.radar)' in intents)
check('QPE UI', 'Section("Lluvia prevista")' in view and 'PrecipitationForecast.build' in view)
check('QPE intent', 'struct RainAmountIntent: AppIntent' in intents)
check('poll notification reevaluation', 'evaluateAndNotify(at: coordinate)' in view)
check('legal/privacy UI', 'Section("Uso responsable y privacidad")' in content)
check('UI test identifiers', all(x in view+content for x in ['nowcast.evaluateLocation','nowcast.refresh','nowcast.notifications','nowcast.help','tools.healthCheck','tools.refresh']))
check('unit tests non-template', 'quantitativePrecipitationFingerprints' in (ROOT/'DanaSafeDeveloperTests/DanaSafeDeveloperTests.swift').read_text())
check('UI tests non-template', 'testPrimaryNavigationAndNowcastHelp' in (ROOT/'DanaSafeDeveloperUITests/DanaSafeDeveloperUITests.swift').read_text())
check('no stale V7 user text', not re.search(r'DanaSafe 7|V7 nowcast trajectory|DanaSafe-iOS/7\.0|danasafe-v7-', '\n'.join([api,model,view,content,intents])))
for p in ios.glob('*.json'):
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'invalid JSON {p.name}: {e}')
# canonical nowcast, in a temporary Engine clone
radar=ROOT/'Engine/Data/Radar/AEMET/NationalSequence/Processed/radar_systems_v03.json'
check('canonical radar fixture exists', radar.exists())
if radar.exists():
    data=json.loads(radar.read_text())
    check('canonical radar has 10 frames', len(data.get('frames',[]))==10)
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)/'Engine'; shutil.copytree(ROOT/'Engine',tmp)
        subprocess.run([sys.executable,str(tmp/'Scripts/build_nowcast_v6.py')],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        out=json.loads((tmp/'Data/Radar/AEMET/NationalSequence/Processed/radar_nowcast_v6.json').read_text())
        check('canonical nowcast has 9 tracks', out.get('track_count')==9)
        check('canonical nowcast timestamp', out.get('radar_timestamp')==data['frames'][-1]['timestamp'])
# production worker manifest remains unchanged
manifest=ROOT/'WORKER_PRODUCTION_FROZEN_SHA256.txt'
check('production worker manifest exists', manifest.exists())
if manifest.exists():
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        digest,rel=line.split(None,1); f=ROOT/rel.strip().lstrip('*')
        check('frozen worker '+rel, f.exists() and sha(f)==digest)
if errors:
    print('DANASAFE 8.1 VERIFY: FAIL')
    for e in errors: print(' -',e)
    sys.exit(1)
print('DANASAFE 8.1 VERIFY: PASS')
print('metadata/privacy/assets/tests: PASS')
print('canonical nowcast: 9 tracks')
print('production Worker frozen manifest: PASS')
print('Xcode compile/UI execution: requires macOS + Xcode')
