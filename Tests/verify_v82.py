#!/usr/bin/env python3
from pathlib import Path
import hashlib
import plistlib
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []

def check(label, condition):
    if not condition:
        errors.append(label)

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

ios = ROOT / "DanaSafeDeveloper"
pbx = (ROOT / "DanaSafeDeveloper.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
api = (ios / "DanaSafeAPIClient.swift").read_text(encoding="utf-8")
model = (ios / "DanaSafeModel.swift").read_text(encoding="utf-8")
content = (ios / "ContentView.swift").read_text(encoding="utf-8")
nowcast_view = (ios / "NowcastView.swift").read_text(encoding="utf-8")
ui_tests = (ROOT / "DanaSafeDeveloperUITests/DanaSafeDeveloperUITests.swift").read_text(encoding="utf-8")
launch_tests = (ROOT / "DanaSafeDeveloperUITests/DanaSafeDeveloperUITestsLaunchTests.swift").read_text(encoding="utf-8")
worker = (ROOT / "CloudflareV82/src/index.ts").read_text(encoding="utf-8")
server = (ROOT / "CloudflareV82/container/server.py").read_text(encoding="utf-8")
candidate = (ROOT / "CloudflareV82/wrangler.jsonc").read_text(encoding="utf-8")
production_example = (ROOT / "CloudflareV82/wrangler.production.example.jsonc").read_text(encoding="utf-8")
plist = plistlib.loads((ios / "Info.plist").read_bytes())

check("marketing version 8.2", pbx.count("MARKETING_VERSION = 8.2;") == 2)
check("build 82", pbx.count("CURRENT_PROJECT_VERSION = 82;") == 2)
check("bundle V82", pbx.count("PRODUCT_BUNDLE_IDENTIFIER = com.firefritz.DanaSafeDeveloperV82;") == 2)
check("test bundle V82", "com.firefritz.DanaSafeDeveloperV82Tests" in pbx)
check("ui test bundle V82", "com.firefritz.DanaSafeDeveloperV82UITests" in pbx)
check("Info version variable", plist.get("CFBundleShortVersionString") == "$(MARKETING_VERSION)")
check("Info build variable", plist.get("CFBundleVersion") == "$(CURRENT_PROJECT_VERSION)")

check("8.2 iOS user agent", "DanaSafe-iOS/8.2-history-r2" in api)
check("history health decoding", all(x in api for x in ["historyEnabled", "historyLatestTimestamp", "archivePolicy"]))
check("history surfaced in model", "historyStatus" in model and "historyLatestTimestamp" in model)
check("history surfaced in Tools", 'LabeledContent("R2 histórico"' in content)
check("8.2 data contract UI", 'Section("Version 8.2 data contract")' in content)
check("UI tests skip startup network", 'arguments.contains("--ui-testing")' in content and 'arguments.contains("--ui-testing")' in nowcast_view)
check("stable help dismiss identifier", 'nowcast.help.dismiss' in nowcast_view and 'nowcast.help.dismiss' in ui_tests)
check("CI launch performance skipped", 'XCTSkip' in ui_tests and 'environment["CI"]' in ui_tests)
check("single launch smoke configuration", 'runsForEachTargetApplicationUIConfiguration: Bool { false }' in launch_tests)

# The previously validated backend tree must remain frozen.
manifest = ROOT / "WORKER_PRODUCTION_FROZEN_SHA256.txt"
check("production freeze manifest exists", manifest.exists())
if manifest.exists():
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(None, 1)
        path = ROOT / rel.strip().lstrip("*")
        check("frozen production backend " + rel, path.exists() and sha256(path) == digest)

check("8.2 backend is separate", (ROOT / "CloudflareV82").is_dir())
check("candidate worker isolated", '"name": "danasafe-radar-v82-candidate"' in candidate)
check("candidate R2 isolated", '"bucket_name": "danasafe-radar-v82-candidate"' in candidate)
check("production promotion preserves current bucket", '"bucket_name": "danasafe-radar-v51"' in production_example)

check("R2 history prefix", 'const HISTORY_PREFIX = "history/cycles";' in worker)
check("R2 newest-first index", 'const HISTORY_INDEX_PREFIX = "history/index";' in worker and "REVERSE_TIME_MAX" in worker)
check("archive-before-live policy", 'archive_policy: "archive-before-live"' in worker)
check("history list endpoint", 'path === "/radar/history"' in worker)
check("history cycle endpoint", 'path === "/radar/history/cycle"' in worker)
check("history manifest endpoint", 'path === "/radar/history/manifest"' in worker)
check("history raw endpoint", 'path === "/radar/history/raw"' in worker)
check("cursor pagination", "next_cursor" in worker and 'url.searchParams.get("cursor")' in worker)
check("history list avoids per-cycle HEAD", 'include: ["customMetadata"]' in worker)
check("archive exact 10 frames", "frames.length !== 10" in worker and "frameNumber <= 10" in worker)
check("raw object hashes stored", "sha256: frame.sha256" in worker)
check("portable manifest verification", "raw_frames: frameRecords" in worker and "bytes: frame.raw.byteLength" in worker)
check("authoritative commit marker", 'archive_complete: "true"' in worker and "historyIndexKey" in worker)
check("post-write R2 verification", "R2 archive verification failed after write" in worker and "history commit marker verification failed" in worker)

refresh_archive = worker.find("const archived = await archiveCycle")
refresh_live = worker.find("await persistLiveSnapshot", refresh_archive)
check("archive happens before LIVE", refresh_archive >= 0 and refresh_live > refresh_archive)
check("unchanged fast path requires history", "await archiveIsComplete(env, latestTimestamp)" in worker)
check("monotonic LIVE guard", "skipped-newer-live" in worker and "currentMs > incomingMs" in worker)

check("container timestamp staging", "ARCHIVE_STAGING" in server and "stage_archive_cycle" in server)
check("container staging occurs under lock", "with LOCK:" in server and "stage_archive_cycle(produced_timestamp)" in server)
check("container manifest endpoint is timestamp-specific", 'path == "/archive/manifest"' in server and 'query.get("timestamp"' in server)
check("container raw frame endpoint is timestamp-specific", 'path == "/archive/frame"' in server and "staged_manifest(timestamp)" in server)
check("target timestamp propagated", 'env["DANASAFE_TARGET_TIMESTAMP"] = target_timestamp' in server)
check("raw SHA256 emitted", '"x-danasafe-sha256": hashlib.sha256(raw).hexdigest()' in server)

combined = "\n".join([worker, server, api, model, content, nowcast_view, ui_tests, launch_tests])
check("Google Drive not in critical path", "drive.google.com" not in combined and "GoogleDrive" not in combined)
check("no stale 8.1 runtime strings", "DanaSafe-iOS/8.1" not in combined and "Actualización 8.1" not in combined)

if errors:
    print("DANASAFE 8.2 VERIFY 1: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)

print("DANASAFE 8.2 VERIFY 1: PASS")
print("versioning and iOS contract: PASS")
print("CloudflareV51 frozen reference: PASS")
print("CloudflareV82 isolation: PASS")
print("archive-before-live + newest-first index: PASS")
print("timestamp-specific container staging: PASS")
print("portable SHA256 archive contract: PASS")
