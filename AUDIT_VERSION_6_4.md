# DanaSafe 6.4 audit

## Inputs audited

Two supplied projects were compared recursively:

- DanaSafeDeveloper-Version-6.3
- DanaSafeDeveloper-Version-6.1-V5Worker

Their `CloudflareV51/` directories are byte-identical across every file.

## Critical findings

1. Both projects use the same production URL: `https://danasafe-radar.firefritz.workers.dev`.
2. Both contain the same frozen `CloudflareV51` Worker source and container files.
3. The checked-in Worker source identifies itself as `5.1-baseline.1`; the live deployed service has separately reported a later Worker version. Therefore the client must not claim that the source tree and deployed Worker version are the same artifact.
4. The 6.3 client already disabled local-network runtime symbols, but legacy local-server utility scripts were still present in the package. They are removed in 6.4.
5. A historical `radar_nowcast_v6.json` resource remained in the Xcode target even though the production Worker does not currently publish live V6 nowcast data. It is removed from the runtime bundle in 6.4 to eliminate stale-nowcast ambiguity.

## Changes in 6.4

- App version 6.4 / build 64.
- Production endpoint unchanged.
- Async refresh algorithm unchanged.
- Snapshot validation algorithm unchanged.
- Radar extraction/tracks/contours/hydrology algorithms unchanged.
- `CloudflareV51/` unchanged byte-for-byte.
- UI no longer hardcodes a production Worker version in the section title.
- Live Worker version remains read from `/health`.
- Stale bundled V6 nowcast resource removed from Xcode resources.
- Local developer HTTP server helpers removed from the release package.

## Explicitly not changed

No Cloudflare deploy is performed by this package. No Worker, Durable Object, R2 bucket, container image, radar thresholds, RGB→dBZ conversion, system detection, tracking logic, contour generation or hydrology logic is modified.
