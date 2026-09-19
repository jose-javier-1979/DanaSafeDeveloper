#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import json
import os
import tempfile

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'Data'
SEQ = DATA / 'Radar/AEMET/NationalSequence'
PROC = SEQ / 'Processed'
CLEAN = DATA / 'Radar/AEMET/NationalClean'
PUBLISHED = DATA / 'Published'
PUBLISHED.mkdir(parents=True, exist_ok=True)

paths = {
    'manifest': SEQ / 'sequence_manifest.json',
    'radar': PROC / 'radar_systems_v03.json',
    'tracks': PROC / 'reliable_tracks.json',
    'contours': CLEAN / 'national_marching_contours.json',
    'hydrology': DATA / 'saih_stations.json',
    'nowcast': PROC / 'radar_nowcast_v6.json',
}
for name, path in paths.items():
    if not path.exists():
        raise FileNotFoundError(f'{name}: {path}')


def load(name):
    return json.loads(paths[name].read_text(encoding='utf-8'))


manifest = load('manifest')
radar = load('radar')
tracks = load('tracks')
contours = load('contours')
hydrology = load('hydrology')
nowcast = load('nowcast')

manifest_frames = manifest.get('frames', [])
radar_frames = radar.get('frames', [])
if len(manifest_frames) != 10 or len(radar_frames) != 10:
    raise RuntimeError(f'Expected 10 radar frames, got manifest={len(manifest_frames)} radar={len(radar_frames)}')

manifest_times = [f['fecha'] for f in manifest_frames]
radar_times = [f['timestamp'] for f in radar_frames]
if manifest_times != radar_times:
    raise RuntimeError('Radar frames do not match the AEMET manifest timestamps from this refresh')

parsed_times = [datetime.fromisoformat(t) for t in manifest_times]
for previous, current in zip(parsed_times, parsed_times[1:]):
    if int((current - previous).total_seconds()) != 600:
        raise RuntimeError(f'Radar cycle is not consecutive at 10-minute cadence: {previous} -> {current}')

latest = manifest_times[-1]
if contours.get('timestamp') != latest:
    raise RuntimeError(f'Contours timestamp mismatch: {contours.get("timestamp")} != {latest}')
if nowcast.get('radar_timestamp') != latest:
    raise RuntimeError(f'Nowcast timestamp mismatch: {nowcast.get("radar_timestamp")} != {latest}')

track_times = set(manifest_times)
for t in tracks.get('tracks', []):
    s = t.get('start', {}).get('timestamp')
    e = t.get('end', {}).get('timestamp')
    if s not in track_times or e not in track_times:
        raise RuntimeError(f'Track {t.get("track_id")} belongs to another radar cycle: {s} -> {e}')

snapshot = {
    'schema': {'name': 'DanaSafeLiveSnapshot', 'version': '6.0.0'},
    'provider': 'AEMET',
    'generated_at': datetime.now().astimezone().isoformat(),
    'radar_timestamp': latest,
    'frame_interval_minutes': manifest.get('frame_interval_minutes', 10),
    'refresh': manifest.get('refresh', {}),
    'cycle': {
        'first_timestamp': manifest_times[0],
        'last_timestamp': latest,
        'frame_count': len(manifest_times),
        'source_filename': manifest_frames[-1].get('filename'),
    },
    'radar': radar,
    'tracks': tracks,
    'contours': contours,
    'hydrology': hydrology,
    'nowcast': nowcast,
    'freshness': {
        'radar_timestamp': latest,
        'hydrology_retrieved_at': hydrology.get('retrieved_at'),
        'hydrology_refresh_coupled_to_radar': False,
    },
}

dst = PUBLISHED / 'danasafe_live_snapshot.json'
fd, tmp = tempfile.mkstemp(prefix='danasafe_live_snapshot.', suffix='.tmp', dir=PUBLISHED)
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, separators=(',', ':'))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dst)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)

print('Published atomic DanaSafe snapshot:', latest)
print('Snapshot:', dst)
