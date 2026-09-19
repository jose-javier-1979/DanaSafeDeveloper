# DanaSafe 6.0 RC1

DanaSafe 6.0 RC1 is built from the validated 5.2.2 Cloud-only client. It preserves the asynchronous refresh compatibility that fixed the V5.2.1 Worker/iOS contract mismatch and adds a location-independent radar nowcast layer.

## Included

- V5.2.2 async-compatible Cloudflare client (`200 snapshot` or `202 -> polling -> snapshot`).
- Cloud-only iOS runtime; local developer server is disabled.
- `DanaSafeLiveSnapshot` schema 6.0 with optional `nowcast` block.
- Formal server-side port of `RadarNowcastEngineV1` to Python.
- Forecast coordinates through 120 minutes.
- Local ETA/closest-approach/threat calculation.
- New **Ahora** tab and V6 trajectory overlay.
- Local user notifications after an on-device threat evaluation.
- App Intents / Siri shortcuts for radar status, ETA query and refresh.
- Parallel V6 Cloudflare Worker/R2 configuration so V5.2.2 remains untouched.

## Important deployment rule

Do **not** deploy V6 over the existing `danasafe-radar` Worker. V6 uses:

- Worker `danasafe-radar-v6`
- R2 `danasafe-radar-v6`
- bundle `com.firefritz.DanaSafeDeveloperV6`

The supplied V6 backend is a synchronous RC1 backend. The iOS client also understands the already-validated asynchronous 5.2.2 pattern, so a future V6 coordinator can be introduced without changing the snapshot model.

## Regression

From project root:

```sh
./Tests/run_v6_regression.sh
```

Expected terminal summary:

```text
BASELINE VERIFY: PASS
DANASAFE V6 VERIFY: PASS
RadarNowcastEngineV1 core-port equivalence: OK
V5 golden radar products unchanged: OK
```

Additional static checks used for RC1:

```sh
swiftc -parse DanaSafeDeveloper/*.swift

tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler \
  --lib ES2022,DOM Tests/cloudflare-stubs.d.ts CloudflareV6/src/index.ts
```

A full Xcode/iOS SDK build, Apple signing, App Intent registration on Siri and physical-device behavior must still be verified on the Mac/iPhone.

## Notifications

RC1 implements local notification authorization and local notifications produced after a user-location assessment. Push delivery while the app is fully closed is intentionally not claimed as complete; that requires APNs device-token registration and backend credentials and should be added only after RC1 is stable.
