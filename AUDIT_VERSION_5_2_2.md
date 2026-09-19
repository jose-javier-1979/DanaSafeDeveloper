# DanaSafe 5.2.2 validation report

## Purpose

Correct the verified contract mismatch between the Cloud-only iOS client and the deployed asynchronous Cloudflare Worker 5.2.1 without changing the meteorological engine.

## Root cause addressed

The previous iOS client assumed `POST /radar/refresh` returned a full `DanaSafeLiveSnapshot` synchronously. Production returned HTTP 202 with an accepted/queued JSON envelope. Swift therefore attempted to decode the queue envelope as the snapshot and produced `The data couldn’t be read...`.

A second client-side issue rejected a valid newly published snapshot whenever AEMET advanced to the next 10-minute slot during the long backend refresh. This could leave the UI showing a much older last-valid snapshot even though R2 had advanced.

## 5.2.2 state machine

`POST /radar/refresh`

- HTTP 200 → validate/publish returned atomic snapshot.
- HTTP 202 → decode accepted envelope → poll `/radar/refresh-status` every 3 s.
- `ready/completed` → GET `/radar/snapshot` → validate → publish.
- `failed/error` → retain previous valid snapshot and show backend error.
- 15-minute client deadline → retain previous valid snapshot and report timeout.

After publishing, the client reads current AEMET metadata and reports exact sync or remaining lag. AEMET rollover is informational and no longer invalidates an otherwise coherent atomic snapshot.

## Safety invariants preserved

- exactly 10 radar frames;
- valid ISO-8601 timestamps;
- strict configured cadence;
- last frame timestamp equals `radar_timestamp`;
- contour timestamp matches radar timestamp;
- track endpoints belong to the same cycle;
- incoming snapshot may not move the app backward in radar time;
- local HTTP service is unavailable from iOS;
- all golden meteorological products remain unchanged.
