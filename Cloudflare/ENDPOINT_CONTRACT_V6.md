# DanaSafeLiveSnapshot V6 contract

Release candidate: `6.0-RC1`

## Deployment isolation

V6 must not overwrite the validated V5.2.2 production path during testing.

- Worker: `danasafe-radar-v6`
- Expected URL: `https://danasafe-radar-v6.firefritz.workers.dev`
- R2 bucket: `danasafe-radar-v6`
- iOS bundle: `com.firefritz.DanaSafeDeveloperV6`
- iOS minimum: 17.0

## Transport contract

The V6 iOS client intentionally supports both backend refresh styles:

1. **Synchronous**: `POST /radar/refresh` returns HTTP 200 + complete `DanaSafeLiveSnapshot`.
2. **Asynchronous-compatible**: HTTP 202 + accepted envelope, followed by polling `GET /radar/refresh-status`, then `GET /radar/snapshot` when ready.

The supplied V6 Worker RC1 uses the synchronous form. Keeping the iOS 5.2.2 asynchronous compatibility prevents reintroducing the contract bug that was fixed before V6.

## Endpoints

- `GET /health`: backend/radar/AEMET status.
- `GET /aemet/timeline`: diagnostic AEMET COMPO timeline.
- `GET /aemet/latest-image-info`: latest AEMET frame metadata.
- `GET /radar/snapshot`: last validated atomic snapshot in R2. Does not run the engine.
- `POST /radar/refresh`: update trigger. Returns a complete snapshot in RC1.

## Atomic snapshot

V6 preserves every V5.2.2 radar field and adds one optional top-level block: `nowcast`.

```json
{
  "schema": {"name": "DanaSafeLiveSnapshot", "version": "6.0.0"},
  "provider": "AEMET",
  "generated_at": "...",
  "radar_timestamp": "...",
  "frame_interval_minutes": 10,
  "radar": {},
  "tracks": {},
  "contours": {},
  "hydrology": {},
  "nowcast": {
    "schema": {"name": "DanaSafeRadarNowcast", "version": "6.0.0"},
    "generated_at": "...",
    "radar_timestamp": "...",
    "horizon_minutes": 120,
    "port": {
      "source": "RadarNowcastEngineV1/NowcastEngine.swift",
      "core_semantics": "association + recent-4 motion vector preserved"
    },
    "track_count": 0,
    "tracks": []
  }
}
```

## Nowcast track

Each track contains:

- stable track id;
- frame persistence;
- first/latest timestamps;
- latest radar-system id and coordinate;
- root area and Zmax;
- estimated effective radius;
- speed, bearing and east/north velocity components;
- recent-vector stability;
- backend confidence;
- projected coordinates at 15, 30, 45, 60, 90 and 120 minutes.

No live user GPS coordinate is required by Cloudflare. Closest approach, ETA and user-specific threat assessment are calculated on-device.

## Publication invariants

A V6 atomic snapshot is publishable only when:

1. exactly 10 radar frames exist;
2. radar frame timestamps exactly match the AEMET sequence manifest;
3. cadence is exactly the configured 10 minutes;
4. latest radar frame equals `radar_timestamp`;
5. contour timestamp equals `radar_timestamp`;
6. reliable-track endpoints belong to the same 10-frame cycle;
7. `nowcast.radar_timestamp == radar_timestamp`.

Hydrology freshness remains independent and is not presented as radar-synchronous.

## Refresh race handling

The Worker pins the selected AEMET timestamp and passes it to the Container. The Container exports it as `DANASAFE_TARGET_TIMESTAMP`; `download_compo_sequence.py` therefore downloads the 10-frame sequence ending at that exact target instead of silently switching to a newer slot. After processing, the Worker checks AEMET again and may perform one catch-up pass. If AEMET advances again during that pass, the valid snapshot is still published and the residual lag is exposed rather than discarding the new product.
