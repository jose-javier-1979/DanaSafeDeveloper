# DanaSafe 8.2

- Marketing version: 8.2
- Build: 82
- Bundle ID: `com.firefritz.DanaSafeDeveloperV82`
- iOS minimum: 17.0
- iPhone only
- iOS production endpoint: `https://danasafe-radar.firefritz.workers.dev`
- Frozen backend reference: `CloudflareV51/`
- New history backend candidate: `CloudflareV82/`
- Candidate Worker: `danasafe-radar-v82-candidate`
- Candidate R2: `danasafe-radar-v82-candidate`
- History policy: archive-before-live
- Per cycle: snapshot + manifest + 10 raw AEMET frames + final index marker
- History listing: newest-first, cursor-paginated
- Container filesystem: scratch/staging only
- Google Drive: optional verified secondary export, never in the live critical path
- Production history status: not declared operational until candidate E2E validation and promotion.
