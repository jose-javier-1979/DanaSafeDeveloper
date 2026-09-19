# DanaSafe 5.2.2 — asynchronous Cloudflare client compatibility release

Build: 53

## Scope

This release changes the iOS Cloudflare transport/state machine only. It does not alter the audited radar extraction, RGB→dBZ conversion, system detection, tracking, reliable-track filtering, contours, or bundled fallback products.

## Production facts used for this patch

Observed production Worker 5.2.1 contract on 2026-09-19:

- `POST /radar/refresh` returns HTTP `202 Accepted` when a refresh is queued.
- Response contains `refresh_state`, `target_aemet_timestamp`, and `poll=/radar/refresh-status`.
- `/radar/refresh-status` progresses through asynchronous state and returns `ready` with `radar_timestamp` on completion.
- `/radar/snapshot` is the authoritative complete atomic snapshot.
- AEMET can advance by a 10-minute slot while the backend engine is still processing.

## Fixed in 5.2.2

1. HTTP 202 is no longer decoded as `DanaSafeLiveSnapshot`.
2. The client polls `/radar/refresh-status` every 3 seconds, up to 15 minutes.
3. The atomic snapshot is fetched only when refresh reaches `ready`/completed state.
4. Backend `failed/error` state is surfaced explicitly.
5. A valid newly generated snapshot is published even if AEMET has advanced another slot during processing; remaining lag is shown as `STALE N min` instead of discarding the new snapshot.
6. The client rejects snapshot regression (an incoming radar timestamp older than the one already displayed).
7. The local developer service remains completely disabled from the iOS runtime.
8. Tools exposes refresh progress (`queued`, `processing`, `ready`, `SYNC`/lag).

## Not fixed by this client release

- Backend processing time. Production evidence showed a refresh from 23:05:08Z to 23:14:46Z (~9m38s). If AEMET publishes every 10 minutes, the backend can naturally finish one slot behind.
- The Worker/Container source for deployed production 5.2.1 is not yet reconstructed in the public Git repository.
- Automatic server-side catch-up to the newest AEMET slot after a long refresh is a backend concern and remains for the next backend patch.
- Remote push/APNs and V6 Nowcast are intentionally out of scope.
