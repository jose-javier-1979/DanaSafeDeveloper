# DanaSafe 7.0 audit

## Baseline

Source: DanaSafe 6.4 archive supplied/validated in this conversation.

## Architectural decision

The production Worker is NOT replaced. DanaSafe 7.0 continues to use:

`https://danasafe-radar.firefritz.workers.dev`

The `CloudflareV51/` tree is frozen byte-for-byte from 6.4.

## Nowcast activation

The production Worker may omit `nowcast`. V7 therefore derives a live local nowcast from the ten radar frames already contained in the validated atomic snapshot. This is a direct Swift port of the canonical `Engine/Scripts/build_nowcast_v6.py` association/motion semantics.

If a future production snapshot contains a timestamp-matched server nowcast, V7 uses it instead.

## User location / privacy

Cloudflare never receives the user's GPS for ETA calculation. ETA, closest approach and threat assessment are calculated on-device.

## Help and live update

The Ahora screen contains an active Help sheet. While visible, it reads the latest already-published atomic snapshot every 60 seconds. This lightweight polling does not trigger the expensive backend refresh pipeline. The explicit update button invokes the existing validated asynchronous refresh contract.

## Verification

- production endpoint assertion
- experimental Worker exclusion
- V7 nowcast fallback wired in model
- V7 nowcast fallback wired in Siri/App Intents
- active Help button
- 60-second lightweight snapshot polling
- no stale iOS bundled nowcast
- version 7.0 / build 70
- separate V7 bundle identifier
- canonical 10-frame nowcast fixture builds 9 tracks
- all Swift source files parse with `swiftc -frontend -parse`
- plist/project syntax checks
- CloudflareV51 byte identity versus 6.4 baseline

A full Apple SDK compile/sign/run must still be performed in Xcode on macOS because this build environment does not contain Apple's iOS SDK.
