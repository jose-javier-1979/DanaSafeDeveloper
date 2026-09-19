# DanaSafe 6.4 — validated production-worker baseline

DanaSafe 6.4 is intentionally conservative.

## Runtime rule

The iOS application has one active network path only:

`https://danasafe-radar.firefritz.workers.dev`

No local Mac service is used by the iOS runtime. The legacy local HTTP helper scripts have been removed from this release package.

## Worker rule

The `CloudflareV51/` tree is preserved byte-for-byte from both supplied working projects. The two uploaded projects contained identical `CloudflareV51` trees. DanaSafe 6.4 does **not** modify or redeploy that Worker.

The checked-in worker source identifies itself as the V5.1 baseline, while the live production endpoint has reported a later deployed Worker version. Because source package version and live deployment version are not guaranteed to be the same artifact, DanaSafe 6.4 no longer hardcodes a Worker version in the UI header. The live version remains displayed dynamically from `/health`.

## Refresh contract

The validated client flow is retained:

1. `POST /radar/refresh`
2. Accept HTTP 200 atomic snapshot, or HTTP 202 accepted/queued response.
3. For HTTP 202, poll `GET /radar/refresh-status`.
4. On `ready` / `completed`, download `GET /radar/snapshot`.
5. Validate 10 consecutive frames, timestamps, contours and track-cycle coherence.
6. Never regress the visible radar to an older snapshot.

## Nowcast safety

The production Worker may not publish a V6 nowcast block. DanaSafe 6.4 therefore does not bundle an old `radar_nowcast_v6.json` into the app target and does not fabricate live nowcast data. The nowcast UI remains available for a future additive backend contract.

## Version

- Marketing version: 6.4
- Build: 64
- Bundle identifier: unchanged from the V6 developer application
