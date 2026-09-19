# DanaSafe Version 5.0 Cloudflare — architecture audit

## Confirmed public service

The public Worker root responds over HTTPS as `DanaSafe Radar Backend`, reports `status: online`, `version: 0.3.0`, and advertises `/health`, `/radar/snapshot`, `/aemet/timeline`, and `/aemet/latest-image-info`.

## Structural problem corrected

V3.2 treated `http://Mac-IP:7117` as the main data path. V5 makes the public Cloudflare Worker the primary path and keeps the local server only as a developer fallback.

## V5 iOS flow

1. Load bundled snapshot immediately so the UI is never empty.
2. Request Cloudflare automatically once at launch.
3. Refresh button requests Cloudflare again with caching disabled.
4. Probe `/health` and `/aemet/latest-image-info` for diagnostics.
5. Decode `/radar/snapshot` using a compatibility ladder:
   - full atomic DanaSafe snapshot;
   - compact original Cloudflare snapshot;
   - direct radar frames.
6. Never combine a current compact Cloudflare radar snapshot with stale local tracks/contours.
7. On failure, preserve the currently displayed valid snapshot.

## Preserved work

Nothing from V3.2 was removed: `Engine/`, AEMET scripts, 10-frame processing, reliable tracks, Marching Squares, atomic publisher, local server, bundled JSON fallback, hydrology, map/search/location UI and diagnostics remain in the project.

## Validation performed in build environment

- All Swift source files: `swiftc -parse` successful.
- Python source files: compile successfully.
- JSON files: parse successfully.
- Info.plist: valid.
- Xcode project version bumped to 5.0 / build 5.
- Public Worker root verified externally over HTTPS.

## External limitation

This build container cannot resolve public DNS for direct Python/curl requests, so the supplied `Tools/test_cloudflare_backend.py` must be run on the Mac/iPhone network for a live read-only smoke test of every sub-endpoint. The iOS app performs the same endpoint requests and reports their state in Tools.
