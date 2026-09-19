#!/usr/bin/env python3
from pathlib import Path
import json
import os
import shutil
import tempfile

BASE = Path(__file__).resolve().parents[1]
SEQ = BASE / 'Data/Radar/AEMET/NationalSequence'
PROC = SEQ / 'Processed'
CLEAN = BASE / 'Data/Radar/AEMET/NationalClean'
MANIFEST = SEQ / 'sequence_manifest.json'

manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
frames = manifest.get('frames', [])
if not frames:
    raise RuntimeError('sequence_manifest.json has no frames')
latest = frames[-1]
frame_no = int(latest['frame'])
source_clean = PROC / f'frame_{frame_no:02d}_clean.png'
if not source_clean.exists():
    raise FileNotFoundError(source_clean)

CLEAN.mkdir(parents=True, exist_ok=True)

def atomic_bytes(dst: Path, data: bytes):
    fd, name = tempfile.mkstemp(prefix=dst.name + '.', suffix='.tmp', dir=dst.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, dst)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def atomic_json(dst: Path, payload):
    atomic_bytes(dst, json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'))

atomic_bytes(CLEAN / 'compo_precip_only.png', source_clean.read_bytes())
atomic_bytes(CLEAN / 'compo_actual.png', source_clean.read_bytes())

b = manifest['bounds']
bounds = [
    [b['west'], b['north']],
    [b['east'], b['north']],
    [b['east'], b['south']],
    [b['west'], b['south']],
]
atomic_json(CLEAN / 'compo_actual_bounds.json', bounds)
atomic_json(CLEAN / 'compo_actual_metadata.json', {
    'provider': manifest.get('provider', 'AEMET'),
    'product': manifest.get('product', 'Composicion radar'),
    'region': manifest.get('region', 'Penbal'),
    'timestamp': latest['fecha'],
    'filename': latest['filename'],
    'projection_hint': 'EPSG:3857',
    'source': 'DanaSafe processed latest sequence frame',
    'source_frame': frame_no,
})
print('Synced latest clean frame:', latest['fecha'], latest['filename'])
