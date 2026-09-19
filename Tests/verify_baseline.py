#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import py_compile
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
errors = []

def fail(message):
    errors.append(message)

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

# 1. Exactly one canonical engine tree.
if not (ROOT / 'Engine').is_dir():
    fail('Missing canonical Engine/')
if (ROOT / 'CloudflareV51/container/Engine').exists():
    fail('Duplicate CloudflareV51/container/Engine must not exist')

# 2. Cloudflare build context must point at repository root.
try:
    wrangler = json.loads((ROOT / 'CloudflareV51/wrangler.jsonc').read_text())
    container = wrangler['containers'][0]
    if container.get('image') != './Dockerfile':
        fail('Unexpected container image path')
    if container.get('image_build_context') != '..':
        fail('Cloudflare image_build_context must be repository root (..)')
except Exception as exc:
    fail(f'Invalid wrangler.jsonc: {exc}')

dockerfile = (ROOT / 'CloudflareV51/Dockerfile').read_text()
for required in ('COPY Engine/requirements.txt', 'COPY Engine /app/Engine', 'COPY CloudflareV51/container/server.py'):
    if required not in dockerfile:
        fail(f'Dockerfile missing canonical source rule: {required}')

# 3. Python syntax.
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir = Path(tmpdir)
    for index, path in enumerate(sorted(ROOT.rglob('*.py'))):
        if '__pycache__' in path.parts:
            continue
        try:
            py_compile.compile(str(path), cfile=str(tmpdir / f'{index}.pyc'), doraise=True)
        except Exception as exc:
            fail(f'Python compile failed: {path.relative_to(ROOT)}: {exc}')

# 4. JSON syntax for project/config/data JSON files.
for path in sorted(ROOT.rglob('*.json')):
    if 'node_modules' in path.parts:
        continue
    try:
        json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        fail(f'JSON parse failed: {path.relative_to(ROOT)}: {exc}')

# 5. Endpoint contract and active implementation must agree on refresh.
contract = (ROOT / 'Cloudflare/ENDPOINT_CONTRACT_V5.md').read_text()
worker = (ROOT / 'CloudflareV51/src/index.ts').read_text()
api = (ROOT / 'DanaSafeDeveloper/DanaSafeAPIClient.swift').read_text()
for token in ('POST /radar/refresh', 'GET /radar/snapshot'):
    if token not in contract:
        fail(f'Contract missing {token}')
if 'path === "/radar/refresh"' not in worker:
    fail('Worker missing /radar/refresh')
if 'request(path: "radar/refresh", method: "POST"' not in api:
    fail('iOS API client missing POST radar/refresh')

# 6. iOS target should reject malformed radar cycles.
model = (ROOT / 'DanaSafeDeveloper/DanaSafeModel.swift').read_text()
for token in ('snapshot.radar.frames.count == 10', 'parsed.count == 10', 'snapshot.contours.timestamp == snapshot.radarTimestamp'):
    if token not in model:
        fail(f'iOS validation guard missing: {token}')

# 7. Xcode project references the eight expected Swift compilation units and four bundled fallbacks.
pbx = (ROOT / 'DanaSafeDeveloper.xcodeproj/project.pbxproj').read_text()
expected_swift = [
    'DanaSafeDeveloperApp.swift', 'ContentView.swift', 'DanaSafeModel.swift',
    'DanaSafeAPIClient.swift', 'Models.swift', 'LocationService.swift',
    'SearchService.swift', 'RadarStyle.swift'
]
expected_resources = [
    'radar_systems_v03.json', 'reliable_tracks.json',
    'national_marching_contours.json', 'saih_stations.json'
]
for name in expected_swift + expected_resources:
    if name not in pbx:
        fail(f'Xcode project missing expected file reference: {name}')

# 8. Golden products currently match the audited reference bytes.
golden = ROOT / 'Baseline/GOLDEN_PRODUCTS.sha256'
for line in golden.read_text().splitlines():
    if not line.strip():
        continue
    expected, rel = line.split(None, 1)
    rel = rel.strip()
    path = ROOT / rel
    if not path.exists():
        fail(f'Golden product missing: {rel}')
    elif sha256(path) != expected:
        fail(f'Golden product hash mismatch: {rel}')

if errors:
    print('BASELINE VERIFY: FAIL')
    for item in errors:
        print(' -', item)
    sys.exit(1)

print('BASELINE VERIFY: PASS')
print('Canonical Engine: OK')
print('Cloudflare build context: OK')
print('Python/JSON syntax: OK')
print('Endpoint contract alignment: OK')
print('iOS guards/Xcode references: OK')
print('Golden product hashes: OK')
