# DanaSafe 8.2 — R2 historical archive

The existing `CloudflareV51` directory is retained because it is the production backend tree used by the current DanaSafe project. DanaSafe 8.2 evolves that same backend rather than introducing a parallel service.

## Retention invariant

A new LIVE radar cycle may not be published until its historical archive has been committed and verified in R2.

Each cycle is stored below:

`history/cycles/<radar_timestamp>/`

with:

- `snapshot.json`
- `manifest.json`
- `raw/01_<AEMET filename>`
- ...
- `raw/10_<AEMET filename>`

The historical `snapshot.json` is written last with `archive_complete=true`. The Worker then HEAD-verifies the manifest, snapshot, and all ten raw frames. Only after that check succeeds is `published/danasafe_live_snapshot.json` advanced.

## Retrieval

- `GET /radar/history`
- `GET /radar/history/cycle?timestamp=<ISO8601>`
- `GET /radar/history/manifest?timestamp=<ISO8601>`
- `GET /radar/history/raw?timestamp=<ISO8601>&frame=1..10`

## Storage roles

- R2: authoritative durable radar archive and LIVE snapshot.
- Container filesystem: working scratch space only; never treated as durable.
- Google Drive: intentionally excluded from the live refresh transaction. It may be used later for asynchronous secondary export, research datasets, or human browsing.

This design prevents a Drive authentication/API failure from blocking an emergency radar refresh.
