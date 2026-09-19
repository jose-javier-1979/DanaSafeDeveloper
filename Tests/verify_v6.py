#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, math, sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
errors=[]
def fail(msg): errors.append(msg)
def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024), b''): h.update(c)
    return h.hexdigest()

# 1. Cloud-only iOS runtime and parallel V6 endpoint.
ios = ROOT/'DanaSafeDeveloper'
api=(ios/'DanaSafeAPIClient.swift').read_text()
model=(ios/'DanaSafeModel.swift').read_text()
content=(ios/'ContentView.swift').read_text()
plist=(ios/'Info.plist').read_text()
for token in ('localServerBaseURL','refreshFromLocalServer','serverHealth','NSLocalNetworkUsageDescription','NSAllowsLocalNetworking'):
    if token in api+model+content+plist: fail(f'Local runtime token remains: {token}')
if 'https://danasafe-radar-v6.firefritz.workers.dev' not in api: fail('V6 iOS endpoint missing')
for token in ('startRadarRefresh()', 'refreshStatus()', 'statusCode == 202'):
    if token not in api: fail(f'Async refresh compatibility missing: {token}')

# 2. Snapshot/model contract is additive and validates nowcast coherence.
models=(ios/'Models.swift').read_text()
for token in ('let nowcast: RadarNowcastFile?', 'RadarNowcastFile'):
    if token not in models: fail(f'V6 snapshot contract missing: {token}')
if 'nowcast.radarTimestamp != snapshot.radarTimestamp' not in model: fail('iOS nowcast/radar timestamp guard missing')
if 'nowcast = snapshot.nowcast' not in model: fail('iOS publish does not expose nowcast')

# 3. Xcode target includes all V6 units and bundled nowcast.
pbx=(ROOT/'DanaSafeDeveloper.xcodeproj/project.pbxproj').read_text()
for name in ('NowcastModels.swift','NowcastEvaluator.swift','NowcastView.swift','NotificationManager.swift','DanaSafeIntents.swift','radar_nowcast_v6.json'):
    if name not in pbx: fail(f'Xcode project missing {name}')

# 4. Backend is isolated from stable V5.
wr=json.loads((ROOT/'CloudflareV6/wrangler.jsonc').read_text())
if wr.get('name')!='danasafe-radar-v6': fail('V6 Worker name is not isolated')
r2=(wr.get('r2_buckets') or [{}])[0].get('bucket_name')
if r2!='danasafe-radar-v6': fail('V6 R2 bucket is not isolated')
if (wr.get('containers') or [{}])[0].get('image_build_context')!='..': fail('V6 container build context is not repository root')

# 5. Engine pipeline contains formal nowcast stage and atomic publication guard.
server=(ROOT/'CloudflareV6/container/server.py').read_text()
publish=(ROOT/'Engine/Scripts/publish_live_snapshot.py').read_text()
builder=(ROOT/'Engine/Scripts/build_nowcast_v6.py').read_text()
if 'build_nowcast_v6.py' not in server: fail('Cloudflare V6 container pipeline omits nowcast stage')
if "nowcast.get('radar_timestamp') != latest" not in publish: fail('Atomic snapshot lacks nowcast timestamp invariant')
if 'RadarNowcastEngineV1/NowcastEngine.swift' not in builder: fail('Nowcast source-port provenance missing')

# 6. Golden V5 radar products must remain byte-identical.
golden=ROOT/'Baseline/GOLDEN_PRODUCTS.sha256'
for line in golden.read_text().splitlines():
    if not line.strip(): continue
    expected, rel=line.split(None,1); p=ROOT/rel.strip()
    if not p.exists(): fail(f'Golden product missing: {rel.strip()}')
    elif sha256(p)!=expected: fail(f'Golden product changed: {rel.strip()}')

# 7. Validate generated bundled nowcast and exact V1 core-port semantics on fixture.
radar=json.loads((ROOT/'Engine/Data/Radar/AEMET/NationalSequence/Processed/radar_systems_v03.json').read_text())
now=json.loads((ios/'radar_nowcast_v6.json').read_text())
if now.get('radar_timestamp') != radar['frames'][-1]['timestamp']: fail('Bundled nowcast timestamp mismatch')
if now.get('horizon_minutes') != 120: fail('Unexpected nowcast horizon')
if now.get('track_count') != len(now.get('tracks',[])): fail('Nowcast track_count mismatch')

MAX=90.0; K=111.32
def parse(s): return datetime.fromisoformat(s.replace('Z','+00:00'))
def xy(a,b):
    lm=math.radians((a['latitude']+b['latitude'])*.5)
    return ((b['longitude']-a['longitude'])*K*math.cos(lm),(b['latitude']-a['latitude'])*K)
def dist(a,b):
    x,y=xy(a,b); return math.hypot(x,y)
tracks=[]; serial=1
for frame in sorted(radar['frames'], key=lambda f:f['frame']):
    used=set()
    for t in tracks:
        prev=t['obs'][-1]
        if prev['frame'] != frame['frame']-1: continue
        cand=[]
        for s in frame.get('systems',[]):
            if s['id'] in used: continue
            d=dist(prev['centroid'],s['centroid'])
            if d>MAX: continue
            a1=max(prev.get('root_area_px',0),1); a2=max(s.get('root_area_px',0),1)
            ar=min(a1,a2)/max(a1,a2)
            zp=abs(prev.get('zmax_dbz',0)-s.get('zmax_dbz',0))/60.0
            score=d/MAX+(1-ar)*.45+zp*.25
            cand.append((score,s))
        cand.sort(key=lambda x:x[0])
        if cand and cand[0][0] < 1.0:
            t['obs'].append(cand[0][1]); used.add(cand[0][1]['id'])
    for s in frame.get('systems',[]):
        if s['id'] not in used:
            tracks.append({'id':f'T{serial:03d}','obs':[s]}); serial+=1

ref={}
for t in tracks:
    obs=t['obs'][-4:]
    if len(obs)<3: continue
    east=north=hours=0.0
    for a,b in zip(obs,obs[1:]):
        dt=(parse(b['timestamp'])-parse(a['timestamp'])).total_seconds()/3600
        if dt<=0: continue
        de,dn=xy(a['centroid'],b['centroid']); east+=de; north+=dn; hours+=dt
    if hours<=0: continue
    ve=east/hours; vn=north/hours; sp=math.hypot(ve,vn)
    if sp<2 or sp>180: continue
    br=math.degrees(math.atan2(ve,vn)); br=br+360 if br<0 else br
    ref[t['id']]={'frame_count':len(t['obs']),'speed':sp,'bearing':br,'ve':ve,'vn':vn}

actual={t['id']:t for t in now['tracks']}
if set(actual)!=set(ref): fail(f'Formal port track set differs from V1 semantics: actual={sorted(actual)} ref={sorted(ref)}')
for tid,r in ref.items():
    a=actual.get(tid)
    if not a: continue
    if a['frame_count']!=r['frame_count']: fail(f'{tid} frame_count differs')
    checks=(('speed_kmh','speed'),('bearing_deg','bearing'),('velocity_east_kmh','ve'),('velocity_north_kmh','vn'))
    for ak,rk in checks:
        if abs(a['motion'][ak]-r[rk]) > 0.01: fail(f'{tid} {ak} differs from V1 port')

if errors:
    print('DANASAFE V6 VERIFY: FAIL')
    for e in errors: print(' -',e)
    sys.exit(1)
print('DANASAFE V6 VERIFY: PASS')
print('V5.2.2 async client inherited: OK')
print('Cloud-only runtime: OK')
print('Parallel V6 Worker/R2 isolation: OK')
print('Snapshot V6 additive contract: OK')
print('RadarNowcastEngineV1 core-port equivalence: OK')
print('V5 golden radar products unchanged: OK')
