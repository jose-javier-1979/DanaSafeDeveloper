# DanaSafe 8.2 Cloudflare backend candidate

This directory contains the **new 8.2 history-capable backend**. It is part of the same DanaSafe repository, but it is deliberately separated from `CloudflareV51/`, which remains the frozen reference for the previously validated production backend.

## Candidate-first deployment

`wrangler.jsonc` deploys a separate Workers.dev service and a separate R2 bucket:

- Worker: `danasafe-radar-v82-candidate`
- R2: `danasafe-radar-v82-candidate`

This allows real end-to-end validation without overwriting the Worker currently used by the iPhone.

`wrangler.production.example.jsonc` documents the eventual production bindings. Do not promote it until the candidate passes both repository verifications plus a real refresh/history retrieval check.

## Historical contract

Each completed cycle is committed to R2 before LIVE can advance:

- `history/cycles/<timestamp>/snapshot.json`
- `history/cycles/<timestamp>/manifest.json`
- ten raw AEMET frames
- a newest-first commit marker under `history/index/`

The index marker is written last and is the authoritative `archive_complete` signal.

History listing is cursor-paginated, newest-first, and does not perform one HEAD request per archived cycle. Health only inspects the newest index marker.

The Container creates timestamp-specific staging bundles while holding its pipeline lock. This prevents overlapping refreshes from reading a mutable manifest belonging to another cycle.
