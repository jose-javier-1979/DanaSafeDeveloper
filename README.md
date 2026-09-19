# DanaSafe Developer 5.1 — Cloudflare end-to-end refresh

This package contains the complete iOS Xcode project, all preserved DanaSafe radar algorithms/data/tools from previous versions, and the Cloudflare V5.1 backend deployment required for a real AEMET → algorithm → app refresh.

## Xcode

Open:

`DanaSafeDeveloper.xcodeproj`

The normal production endpoint remains:

`https://danasafe-radar.firefritz.workers.dev`

At app startup DanaSafe loads the bundled fallback first and then `GET /radar/snapshot`. Tapping ↻ sends `POST /radar/refresh` and accepts a new state only after end-to-end timestamp validation.

## Important deployment dependency

The existing public Worker currently identifies itself as V0.3.0. To activate the V5.1 refresh contract, deploy the included `CloudflareV51/` project once using:

`./CloudflareV51/scripts/deploy.sh`

See `CloudflareV51/README_CLOUDFLARE_5_1.md` and `AUDIT_VERSION_5_1.md`.

## Preserved components

`Engine/`, `Tools/`, all Python/Pillow algorithms, local server fallback, bundled JSON/PNG/data, reliable tracks, Marching Squares contours, hydrology, search and location are retained.
