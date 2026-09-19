# DanaSafe 8.2 — historical radar archive candidate

DanaSafe 8.2 evolves the current project without replacing the repository or scientific core.

## Primary change

Every successful new radar cycle is archived in Cloudflare R2 before the LIVE snapshot advances.

For each radar timestamp the archive contains:

- `snapshot.json`
- `manifest.json`
- 10 raw AEMET radar frames

The cycle snapshot is written last with `archive_complete=true`, acting as the commit marker. The Worker verifies all 12 R2 objects before publishing the new LIVE snapshot.

## Recovery

Archived cycles can be listed and individual snapshots, manifests, and raw frames can be retrieved through the Worker history endpoints.

## Validation order

1. Run `python3 Tests/verify_v82.py`.
2. Run the full GitHub Actions CI build and tests.
3. Deploy the 8.2 Worker/Container.
4. Trigger one real radar refresh.
5. Confirm that the returned LIVE timestamp is present in `/radar/history`.
6. Retrieve its manifest and all 10 raw frames and verify hashes/metadata.

Do not consider historical retention operational until steps 3–6 have passed against the production R2 bucket.

## Optional Google Drive / local export

R2 remains the authoritative live archive. For a secondary human-browsable copy, run:

```sh
python3 Tools/export_r2_history.py --output "/path/to/Google Drive/DanaSafe Radar History"
```

The exporter downloads each completed cycle, writes its snapshot, manifest and ten raw frames, recalculates SHA-256 for every frame, checks the manifest hash/byte count and writes `verification.json`. A failed integrity check aborts that cycle instead of silently copying corrupted data.
