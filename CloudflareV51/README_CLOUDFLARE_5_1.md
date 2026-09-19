# DanaSafe 5.1 — Cloudflare production architecture

## Why V5.1 exists

V5.0 could make a fresh GET to Cloudflare, but it could not prove that the Worker had re-run the DanaSafe radar algorithm. V5.1 closes that gap.

## End-to-end path

1. iOS loads the last published atomic snapshot with `GET /radar/snapshot`.
2. The user taps ↻.
3. iOS sends `POST /radar/refresh` (no-cache, 300 s timeout).
4. The Worker fetches the AEMET COMPO PB timeline with `cache: no-store`.
5. If R2 already contains that exact latest AEMET timestamp, the Worker returns it without recomputation.
6. If AEMET has a newer frame, the Worker wakes one Cloudflare Container.
7. The Container runs the preserved DanaSafe Python/Pillow pipeline:
   - download_compo_sequence.py
   - process_compo_sequence.py
   - build_radar_systems_v03.py
   - track_radar_sequence.py
   - preview_reliable_tracks.py
   - sync_latest_frame.py
   - national_marching_squares.py
   - publish_live_snapshot.py
8. `publish_live_snapshot.py` refuses to publish mixed timestamps.
9. The Worker independently verifies that the returned `radar_timestamp` equals the AEMET frame that triggered the refresh.
10. Only then is the complete atomic JSON stored in R2.
11. The exact bytes stored in R2 are returned to iOS.
12. iOS validates frames, contours and tracks again before replacing the visible radar.

There are therefore three independent temporal checks: Python publisher, Worker, and iOS.

## Persistence

R2 bucket: `danasafe-radar-v51`
Object key: `published/danasafe_live_snapshot.json`

The Container may scale to zero; the published snapshot remains in R2.

## DNS / hostname

For the first deployment keep the existing Workers hostname:

`https://danasafe-radar.firefritz.workers.dev`

No CNAME is required for this route.

For production, prefer a Cloudflare Worker **Custom Domain** such as `radar.<your-domain>`. Add it in Worker > Settings > Domains & Routes > Add > Custom Domain. Cloudflare creates the required DNS record and TLS certificate. Do not pre-create a CNAME on that same hostname.

After a Custom Domain is active, change only `DanaSafeAPIClient.productionBaseURL` in Xcode.

## Cloudflare requirements

Cloudflare Containers require a Workers Paid plan. Docker must be available for a local `wrangler deploy`, or the repository can be connected to Workers Builds.

## First deployment

From the repository root:

```sh
./CloudflareV51/scripts/deploy.sh
```

This installs Wrangler dependencies, creates the R2 bucket if necessary, builds the Python/Pillow Container and deploys the Worker.

The current public Worker must be upgraded with this code before the iOS V5.1 refresh button can execute the remote algorithm. Until then the existing V0.3 Worker does not expose the V5.1 `POST /radar/refresh` contract.

## Verification

After deployment:

```sh
./CloudflareV51/scripts/test_backend.sh
```

Expected properties:

- `/` reports version `5.1.0`.
- `/health` includes `latest_aemet_timestamp`, `radar_timestamp`, and `in_sync`.
- `POST /radar/refresh` returns a full `DanaSafeLiveSnapshot`.
- `radar_timestamp == latest_aemet_timestamp`.
- the snapshot contains 10 consecutive radar frames.
- contour timestamp matches radar timestamp.
- all track start/end timestamps belong to those ten frames.
