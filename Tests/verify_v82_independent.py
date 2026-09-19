#!/usr/bin/env python3
from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]
worker = (ROOT / "CloudflareV51/src/index.ts").read_text(encoding="utf-8")
server = (ROOT / "CloudflareV51/container/server.py").read_text(encoding="utf-8")
wrangler = (ROOT / "CloudflareV51/wrangler.jsonc").read_text(encoding="utf-8")
errors = []

def check(label, cond):
    if not cond:
        errors.append(label)

# Independent contract verification: storage topology.
check("LIVE key preserved", 'const SNAPSHOT_KEY = "published/danasafe_live_snapshot.json";' in worker)
check("authoritative bucket binding preserved", '"binding": "SNAPSHOTS"' in wrangler)
check("authoritative R2 bucket preserved", '"bucket_name": "danasafe-radar-v51"' in wrangler)
check("history lives in same authoritative R2", 'const HISTORY_PREFIX = "history/cycles";' in worker)

# A cycle must be self-contained and recoverable.
for suffix in ["/snapshot.json", "/manifest.json", "/raw/"]:
    check(f"cycle contains {suffix}", suffix in worker)
check("manifest indexes raw objects", "raw_objects: frameKeys" in worker)
check("manifest carries portable hashes", "raw_frames: frameRecords" in worker and "sha256: frame.sha256" in worker and "bytes: frame.raw.byteLength" in worker)
check("raw retrieval follows manifest index", "manifest?.raw_frames?.[frameNumber - 1]?.r2_key" in worker)
check("cycle retrieval endpoint returns archived snapshot", 'readArchiveObject(env, `${prefix}/snapshot.json`)' in worker)
check("manifest retrieval endpoint returns archived manifest", 'readArchiveObject(env, `${prefix}/manifest.json`)' in worker)

# Idempotency: an already-complete 10-frame cycle is reused, not duplicated.
check("existing cycle HEAD check", "existingSnapshot" in worker and "existingManifest" in worker)
check("complete marker used for idempotency", 'existingSnapshot.customMetadata?.archive_complete === "true"' in worker)
check("ten raw objects required for reuse", "(listed.objects ?? []).length === 10" in worker)

# Failure semantics: LIVE publication is downstream of archive and inside the same try.
refresh_start = worker.find('if (path === "/radar/refresh"')
refresh_end = worker.find('return json({ status: "not_found"', refresh_start)
refresh_block = worker[refresh_start:refresh_end]
archive_pos = refresh_block.find("await archiveCycle")
live_pos = refresh_block.find("await persistLiveSnapshot")
check("archive and LIVE are in refresh transaction", archive_pos >= 0 and live_pos >= 0)
check("archive precedes LIVE in transaction", archive_pos < live_pos)
check("no catch-and-ignore around archive", "archiveCycle(env" in refresh_block and "catch" not in refresh_block[archive_pos:live_pos])
check("global failure returns HTTP 500", '}, 500);' in worker)

# The Worker-selected target must constrain the actual Python downloader.
check("Worker passes target to container", "?target=" in worker and "runEngineRefresh(env, latestTimestamp)" in worker)
check("container exports target environment", 'DANASAFE_TARGET_TIMESTAMP' in server)
check("subprocess receives pinned environment", "env=env" in server)

# Raw image integrity metadata must be generated at the source and retained in R2.
check("container computes SHA256 from bytes", "hashlib.sha256(raw).hexdigest()" in server)
check("Worker reads SHA256 header", 'response.headers.get("x-danasafe-sha256")' in worker)
check("R2 raw metadata stores SHA256", "sha256: frame.sha256" in worker)

# Container retention must not be assumed.
check("container still allowed to sleep", 'sleepAfter = "2m"' in worker)
check("no production history path points to container filesystem", "history/cycles" not in server)

if errors:
    print("DANASAFE 8.2 VERIFY 2: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)

print("DANASAFE 8.2 VERIFY 2: PASS")
print("storage topology: PASS")
print("cycle recoverability: PASS")
print("idempotency: PASS")
print("failure semantics: PASS")
print("target pinning: PASS")
print("raw-frame integrity chain: PASS")
