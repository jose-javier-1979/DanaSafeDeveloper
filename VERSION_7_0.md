# DanaSafe 7.0 — Worker 6.4 + live on-device Nowcast

## Production invariant

DanaSafe 7.0 keeps the validated production backend used by DanaSafe 6.4:

`https://danasafe-radar.firefritz.workers.dev`

`CloudflareV51/` is not modified by this release.

## Nowcast architecture

The production Worker currently publishes the validated atomic radar snapshot but may not include a `nowcast` block. DanaSafe 7.0 therefore applies this rule:

1. If the live snapshot includes `nowcast`, use it after timestamp validation.
2. Otherwise derive Nowcast V7 on-device from the ten radar frames in the same live snapshot.
3. Never load an old bundled nowcast and never simulate radar data.

The local builder is a Swift port of the canonical `Engine/Scripts/build_nowcast_v6.py` semantics:

- maximum association distance: 90 km
- association score: distance + area-ratio penalty + Zmax penalty
- recent observations used for motion: 4
- minimum motion speed: 2 km/h
- maximum motion speed: 180 km/h
- forecast horizon: 120 min
- forecast points: 15/30/45/60/90/120 min
- confidence: persistence + vector stability

ETA, closest approach and threat assessment remain device-local; user GPS is not sent to Cloudflare.

## Live behavior

The Ahora tab polls the already-published atomic snapshot every 60 seconds without starting the backend engine. The explicit `Actualizar radar y nowcast` action invokes the existing validated asynchronous Worker contract.

## Help

The Ahora tab includes an active Help sheet describing data source, algorithm, interpretation and update semantics.
