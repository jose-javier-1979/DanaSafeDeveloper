#!/usr/bin/env python3
from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
worker = (ROOT / "CloudflareV82/src/index.ts").read_text(encoding="utf-8")
server = (ROOT / "CloudflareV82/container/server.py").read_text(encoding="utf-8")
candidate = (ROOT / "CloudflareV82/wrangler.jsonc").read_text(encoding="utf-8")
production = (ROOT / "CloudflareV82/wrangler.production.example.jsonc").read_text(encoding="utf-8")
errors = []

def check(label, cond):
    if not cond:
        errors.append(label)

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

# Independent topology check.
check("LIVE key preserved", 'const SNAPSHOT_KEY = "published/danasafe_live_snapshot.json";' in worker)
check("candidate binding exists", '"binding": "SNAPSHOTS"' in candidate)
check("candidate storage isolated", '"bucket_name": "danasafe-radar-v82-candidate"' in candidate)
check("production promotion targets existing archive bucket", '"bucket_name": "danasafe-radar-v51"' in production)
check("history data prefix", 'const HISTORY_PREFIX = "history/cycles";' in worker)
check("history index prefix", 'const HISTORY_INDEX_PREFIX = "history/index";' in worker)

# Production reference must not be silently edited.
freeze = ROOT / "WORKER_PRODUCTION_FROZEN_SHA256.txt"
check("freeze manifest present", freeze.exists())
if freeze.exists():
    for line in freeze.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(None, 1)
        path = ROOT / rel.strip().lstrip("*")
        check("frozen " + rel, path.exists() and sha256(path) == digest)

# A cycle must be self-contained and externally verifiable.
for suffix in ["/snapshot.json", "/manifest.json", "/raw/"]:
    check("cycle contains " + suffix, suffix in worker)
check("manifest indexes raw objects", "raw_objects: frameKeys" in worker)
check("manifest carries hashes and sizes", "raw_frames: frameRecords" in worker and "sha256: frame.sha256" in worker and "bytes: frame.raw.byteLength" in worker)
check("raw retrieval follows manifest", "manifest?.raw_frames?.[frameNumber - 1]?.r2_key" in worker)
check("raw response exposes R2 hash", 'headers.set("x-danasafe-sha256"' in worker)

# Idempotency and commit semantics.
check("index marker is idempotency source", "archiveIsComplete" in worker and "historyIndexKey" in worker)
check("index marker written after payload verification", worker.find("const verification = await Promise.all") < worker.find("await env.SNAPSHOTS.put(indexKey"))
check("index marker verified", "history commit marker verification failed" in worker)

# Newest-first, pageable listing; health cannot grow linearly with history.
check("reverse-time newest-first keys", "REVERSE_TIME_MAX - ms" in worker)
check("history cursor accepted", 'url.searchParams.get("cursor")' in worker)
check("history cursor returned", "next_cursor" in worker)
summary_start = worker.find("async function historySummary")
summary_end = worker.find("async function readArchiveObject", summary_start)
summary = worker[summary_start:summary_end]
check("health summary is O(1) R2 list", "limit: 1" in summary and ".head(" not in summary)

# Overlap safety: Worker reads immutable cycle-specific staging, not the mutable sequence manifest.
check("container creates timestamp-specific staging", "ARCHIVE_STAGING" in server and "safe_stage_name" in server)
check("staging created while pipeline lock held", "with LOCK:" in server and "stage_archive_cycle(produced_timestamp)" in server)
check("Worker requests target-specific staged manifest", "/archive/manifest?timestamp=" in worker)
check("Worker requests target-specific staged frames", "/archive/frame?timestamp=" in worker)
check("staged frame reads do not call current manifest", "staged_manifest(timestamp)" in server)

# Upgrade bootstrap and LIVE failure semantics.
refresh_start = worker.find('if (path === "/radar/refresh"')
refresh_end = worker.find('return json({ status: "not_found"', refresh_start)
refresh = worker[refresh_start:refresh_end]
check("same LIVE only fast-paths when archived", "await archiveIsComplete(env, latestTimestamp)" in refresh)
archive_pos = refresh.find("await archiveCycle")
live_pos = refresh.find("await persistLiveSnapshot")
check("archive precedes LIVE", archive_pos >= 0 and live_pos > archive_pos)
check("archive failures are not ignored", "catch" not in refresh[archive_pos:live_pos])
check("LIVE monotonic guard", "skipped-newer-live" in worker and "currentMs > incomingMs" in worker)

# Target pinning and raw integrity chain.
check("Worker passes selected target", "?target=" in worker and "runEngineRefresh(env, latestTimestamp)" in worker)
check("container exports target environment", "DANASAFE_TARGET_TIMESTAMP" in server)
check("subprocess receives pinned environment", "env=env" in server)
check("container hashes actual bytes", "hashlib.sha256(raw).hexdigest()" in server)
check("Worker retains source hash", "sha256: frame.sha256" in worker)

# Container remains scratch; durable history is R2 only.
check("container can still sleep", 'sleepAfter = "2m"' in worker)
check("R2 history prefix absent from container filesystem", "history/cycles" not in server)

if errors:
    print("DANASAFE 8.2 VERIFY 2: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)

print("DANASAFE 8.2 VERIFY 2: PASS")
print("frozen production reference: PASS")
print("candidate isolation: PASS")
print("recoverability + portable hashes: PASS")
print("newest-first pagination + O(1) health: PASS")
print("overlapping-refresh staging: PASS")
print("upgrade bootstrap + archive-before-live: PASS")
