#!/usr/bin/env python3
from pathlib import Path
import plistlib, re, sys

ROOT = Path(__file__).resolve().parents[1]
errors = []

def check(label, condition):
    if not condition:
        errors.append(label)

ios = ROOT / "DanaSafeDeveloper"
pbx = (ROOT / "DanaSafeDeveloper.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
api = (ios / "DanaSafeAPIClient.swift").read_text(encoding="utf-8")
model = (ios / "DanaSafeModel.swift").read_text(encoding="utf-8")
content = (ios / "ContentView.swift").read_text(encoding="utf-8")
worker = (ROOT / "CloudflareV51/src/index.ts").read_text(encoding="utf-8")
server = (ROOT / "CloudflareV51/container/server.py").read_text(encoding="utf-8")
plist = plistlib.loads((ios / "Info.plist").read_bytes())

check("marketing version 8.2", pbx.count("MARKETING_VERSION = 8.2;") == 2)
check("build 82", pbx.count("CURRENT_PROJECT_VERSION = 82;") == 2)
check("bundle V82", pbx.count("PRODUCT_BUNDLE_IDENTIFIER = com.firefritz.DanaSafeDeveloperV82;") == 2)
check("test bundle V82", "com.firefritz.DanaSafeDeveloperV82Tests" in pbx)
check("ui test bundle V82", "com.firefritz.DanaSafeDeveloperV82UITests" in pbx)
check("Info version variable", plist.get("CFBundleShortVersionString") == "$(MARKETING_VERSION)")
check("Info build variable", plist.get("CFBundleVersion") == "$(CURRENT_PROJECT_VERSION)")

check("8.2 iOS user agent", "DanaSafe-iOS/8.2-history-r2" in api)
check("history health decoding", "historyCyclesVisible" in api and "archivePolicy" in api)
check("history surfaced in model", "historyStatus" in model)
check("history surfaced in Tools", 'LabeledContent("R2 histórico"' in content)
check("8.2 data contract UI", 'Section("Version 8.2 data contract")' in content)

check("R2 history prefix", 'const HISTORY_PREFIX = "history/cycles";' in worker)
check("archive-before-live policy", 'archive_policy: "archive-before-live"' in worker)
check("history list endpoint", 'path === "/radar/history"' in worker)
check("history cycle endpoint", 'path === "/radar/history/cycle"' in worker)
check("history manifest endpoint", 'path === "/radar/history/manifest"' in worker)
check("history raw endpoint", 'path === "/radar/history/raw"' in worker)
check("archive exact 10 frames", "frames.length !== 10" in worker and "frameNumber <= 10" in worker)
check("raw object hashes stored", 'sha256: frame.sha256' in worker)
check("cycle commit marker", 'archive_complete: "true"' in worker)
check("post-write R2 verification", "R2 archive verification failed after write" in worker)

refresh_archive = worker.find("const archived = await archiveCycle")
refresh_live = worker.find("await persistLiveSnapshot", refresh_archive)
check("archive happens before LIVE", refresh_archive >= 0 and refresh_live > refresh_archive)

archive_manifest = worker.find("await env.SNAPSHOTS.put(manifestKey")
archive_snapshot = worker.find("await env.SNAPSHOTS.put(snapshotKey", archive_manifest)
check("snapshot commit marker written after manifest", archive_manifest >= 0 and archive_snapshot > archive_manifest)

check("container manifest endpoint", 'path == "/archive/manifest"' in server)
check("container raw frame endpoint", 'path == "/archive/frame"' in server)
check("target timestamp propagated", 'env["DANASAFE_TARGET_TIMESTAMP"] = target_timestamp' in server)
check("raw SHA256 emitted", '"x-danasafe-sha256": hashlib.sha256(raw).hexdigest()' in server)

combined = "\n".join([worker, server, api, model, content])
check("Google Drive not in critical path", "drive.google.com" not in combined and "GoogleDrive" not in combined)

# Guard against accidentally shipping the old app version in user-visible/runtime strings.
check("no stale 8.1 runtime strings", "DanaSafe-iOS/8.1" not in combined and "Actualización 8.1" not in combined)

if errors:
    print("DANASAFE 8.2 VERIFY 1: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)

print("DANASAFE 8.2 VERIFY 1: PASS")
print("versioning: PASS")
print("archive-before-live invariant: PASS")
print("10 raw frames + manifest + snapshot contract: PASS")
print("historical retrieval endpoints: PASS")
print("container target pinning + SHA256: PASS")
print("iOS archive health visibility: PASS")
