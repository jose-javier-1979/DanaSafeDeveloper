# DanaSafe V5.1 Baseline - Cloudflare endpoint contract

Primary base URL:

`https://danasafe-radar.firefritz.workers.dev`

Baseline identifier: `5.1-baseline.1`.

## Public Worker endpoints

- `GET /`
- `GET /health`
- `GET /radar/snapshot`
- `POST /radar/refresh`
- `GET /aemet/timeline`
- `GET /aemet/latest-image-info`

All application-facing responses use `Cache-Control: no-store` semantics.

## Canonical iOS snapshot contract

DanaSafe 5.1 Baseline accepts one production snapshot shape from
`GET /radar/snapshot` and `POST /radar/refresh`: the full atomic
`DanaSafeLiveSnapshot`.

Required top-level fields used by iOS:

- `generated_at`
- `radar_timestamp`
- `frame_interval_minutes`
- `radar.frames`
- `tracks.tracks`
- `contours`
- `hydrology`

The radar contract is strict:

- exactly 10 radar frames;
- every timestamp must parse as ISO-8601;
- frame timestamps must be consecutive at `frame_interval_minutes` cadence;
- the last radar frame timestamp must equal `radar_timestamp`;
- contour timestamp must equal `radar_timestamp`;
- every reliable-track start/end timestamp must belong to the same 10-frame cycle.

Legacy compact structs remain in source for compatibility/reference only. They are
not part of the active V5.1 Baseline production decoding path.

## GET /health

Reports Worker/backend status and, when available:

- `radar_timestamp`
- `snapshot_generated_at`
- `latest_aemet_timestamp`
- `in_sync`
- `aemet_error`
- `hydrology_retrieved_at`
- `hydrology_refresh_coupled_to_radar` (currently `false`)

Radar and hydrology freshness are intentionally independent. A radar refresh does
not imply that SAIH data was refreshed at the same instant.

## GET /radar/snapshot

Returns the last atomic snapshot persisted in R2. It never executes the radar
pipeline. Returns HTTP 404 if no snapshot has yet been published.

## POST /radar/refresh

1. Worker requests the latest AEMET COMPO/PB timeline with cache bypassed.
2. If R2 already contains that radar timestamp, it returns the stored snapshot.
3. Otherwise it asks the bound Container to refresh, passing the target timestamp.
4. The Container serializes refreshes. After acquiring the lock it reuses an
   already-current snapshot if another request produced the same target while the
   request was waiting.
5. The Worker re-checks AEMET after processing to handle a radar-cycle rollover
   during the pipeline. If necessary it retries once against the newer target.
6. Only a snapshot matching the latest AEMET timestamp is persisted to R2.
7. The exact bytes persisted to R2 are returned to iOS.

## Container/internal endpoints

The Container exposes only internal endpoints through the Durable Object binding:

- `GET /health`
- `GET /snapshot`
- `POST /refresh?target=<ISO8601>`

## Engine source of truth

`Engine/` at repository root is the single canonical Python/Pillow engine.
`CloudflareV51` builds its container with repository-root `image_build_context`;
there is no second copied Engine tree under `CloudflareV51/container/`.

## Hydrology limitation in this baseline

`extract_saih.py` parses a locally supplied `Engine/Data/saih_aforos.html` file.
The current production radar refresh pipeline does not download a new SAIH source,
therefore it must not claim hydrology is refreshed with each radar cycle. The
atomic snapshot carries the original `hydrology.retrieved_at` plus a `freshness`
block that makes this separation explicit.

## Preserved local development path

The Python/AEMET algorithm remains available under `Engine/` and `Tools/` for
local development and regression testing.
