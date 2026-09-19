#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, re, subprocess, sys, tempfile, shutil

ROOT = Path(__file__).resolve().parents[1]

def fail(msg):
    print('FAIL:', msg)
    raise SystemExit(1)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

# 1. Production endpoint frozen.
api = (ROOT / 'DanaSafeDeveloper/DanaSafeAPIClient.swift').read_text()
if 'https://danasafe-radar.firefritz.workers.dev' not in api:
    fail('production 6.4 endpoint missing')
if 'danasafe-radar-v61' in api or 'danasafe-radar-v6.' in api:
    fail('experimental worker leaked into active client')

# 2. V7 client-side fallback is wired in model and App Intents.
model = (ROOT / 'DanaSafeDeveloper/DanaSafeModel.swift').read_text()
intents = (ROOT / 'DanaSafeDeveloper/DanaSafeIntents.swift').read_text()
view = (ROOT / 'DanaSafeDeveloper/NowcastView.swift').read_text()
evaluator = (ROOT / 'DanaSafeDeveloper/NowcastEvaluator.swift').read_text()
for text, needle, label in [
    (model, 'NowcastBuilderV7.build(from: snapshot.radar)', 'model nowcast fallback'),
    (intents, 'NowcastBuilderV7.build(from: snapshot.radar)', 'Siri nowcast fallback'),
    (view, 'Button("Ayuda"', 'Help button'),
    (view, 'Task.sleep(for: .seconds(60))', 'live snapshot polling'),
    (evaluator, 'private static let maxAssociationKm = 90.0', 'association distance'),
    (evaluator, 'private static let maxSpeedKmh = 180.0', 'maximum speed'),
    (evaluator, 'private static let minSpeedKmh = 2.0', 'minimum speed'),
    (evaluator, 'private static let horizonMinutes = [15, 30, 45, 60, 90, 120]', 'forecast horizon'),
]:
    if needle not in text:
        fail(label + ' missing')

# 3. No stale nowcast is bundled into the iOS target.
if (ROOT / 'DanaSafeDeveloper/radar_nowcast_v6.json').exists():
    fail('stale bundled nowcast present')

# 4. App version / bundle id.
proj = (ROOT / 'DanaSafeDeveloper.xcodeproj/project.pbxproj').read_text()
if proj.count('MARKETING_VERSION = 7.0;') != 2:
    fail('MARKETING_VERSION not 7.0 in both configs')
if proj.count('CURRENT_PROJECT_VERSION = 70;') != 2:
    fail('build number not 70 in both configs')
if proj.count('PRODUCT_BUNDLE_IDENTIFIER = com.firefritz.DanaSafeDeveloperV7;') != 2:
    fail('V7 bundle id not set')

# 5. Canonical Python nowcast fixture remains valid and provides the reference semantics.
radar = ROOT / 'Engine/Data/Radar/AEMET/NationalSequence/Processed/radar_systems_v03.json'
if not radar.exists():
    fail('radar fixture missing')
data = json.loads(radar.read_text())
if len(data.get('frames', [])) != 10:
    fail('canonical fixture does not contain 10 frames')

# Run canonical builder in a temporary clone of Engine so the package is not mutated.
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td) / 'Engine'
    shutil.copytree(ROOT / 'Engine', tmp)
    subprocess.run([sys.executable, str(tmp / 'Scripts/build_nowcast_v6.py')], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    result = json.loads((tmp / 'Data/Radar/AEMET/NationalSequence/Processed/radar_nowcast_v6.json').read_text())
    if result.get('track_count') != 9:
        fail(f"canonical fixture expected 9 nowcast tracks, got {result.get('track_count')}")
    if result.get('radar_timestamp') != data['frames'][-1]['timestamp']:
        fail('canonical nowcast timestamp mismatch')

print('DANASAFE V7 VERIFY: PASS')
print('endpoint: production Worker 6.4 path')
print('canonical nowcast fixture: 9 tracks')
print('Help: active')
print('live snapshot polling: 60 s')
