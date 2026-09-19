# DanaSafe 8.2

- Marketing version: 8.2
- Build: 82
- Bundle ID: `com.firefritz.DanaSafeDeveloperV82`
- iOS minimum: 17.0
- iPhone only
- Production endpoint: `https://danasafe-radar.firefritz.workers.dev`
- Historical radar archive: R2 immutable cycle archive
- Archive policy: archive-before-live
- Per cycle: atomic snapshot + manifest + 10 raw AEMET frames
- Historical retrieval endpoints:
  - `GET /radar/history`
  - `GET /radar/history/cycle?timestamp=...`
  - `GET /radar/history/manifest?timestamp=...`
  - `GET /radar/history/raw?timestamp=...&frame=1..10`
- Container filesystem is treated as ephemeral and is not relied upon for retention.
- Google Drive is deliberately not in the real-time critical path; it can be added later as a secondary export/backup target.
