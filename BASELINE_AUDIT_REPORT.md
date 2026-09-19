# DanaSafe 5.1 Baseline - Audit and reproducibility report

Baseline: `5.1-baseline.1`

Source archive SHA-256:

`6f84e562efbb2246d3b1b61d18e67e6b36e80670d15847e8d29fbf9cf590eeec`

## Objective

Create a stable, audited and reproducible pre-V6 reference without adding Nowcast,
notifications, Siri or other V6 functionality.

## Corrections incorporated

### 1. Radar-system builder performance

`Engine/Scripts/build_radar_systems_v03.py` now computes connected components once
per dBZ level and frame, then reuses them for each root system. Previously the full
mask/component calculation was repeated for every root and every level.

Regression result: the audited `radar_systems_v03.json` retains exactly the same
SHA-256 as before the optimization.

Measured in the audit environment after optimization: approximately 12 seconds for
`build_radar_systems_v03.py` on the bundled 10-frame fixture.

### 2. Single canonical Engine

Removed the duplicate `CloudflareV51/container/Engine/` tree.

`Engine/` is now the sole Python/Pillow source of truth. `wrangler.jsonc` sets
`image_build_context` to repository root and the Dockerfile copies `Engine/`
directly into the image.

### 3. Docker build-path correction

Dockerfile paths now match the configured build context:

- `Engine/requirements.txt`
- `Engine/`
- `CloudflareV51/container/server.py`

### 4. Refresh concurrency guard

The container accepts an optional target timestamp. The target check occurs inside
the refresh lock, so a request that waited for another refresh can reuse the newly
published snapshot instead of executing the expensive pipeline again.

Each pipeline stage also has an explicit execution timeout.

### 5. AEMET rollover reconciliation

The Worker re-reads the latest AEMET timeline after the container finishes. If the
radar cycle changed during processing, it can accept a snapshot matching the new
latest timestamp or retry once when the generated snapshot is older.

### 6. Endpoint contract alignment

`Cloudflare/ENDPOINT_CONTRACT_V5.md` now documents the endpoints actually used,
including `POST /radar/refresh`, and identifies the full atomic
`DanaSafeLiveSnapshot` as the active production iOS contract.

### 7. Strict iOS snapshot validation

`DanaSafeModel` now requires:

- exactly 10 frames;
- valid ISO-8601 timestamps;
- positive frame interval;
- strict frame cadence;
- latest frame == `radar_timestamp`;
- contour timestamp == radar timestamp;
- track endpoints belonging to the same radar cycle.

### 8. Hydrology freshness made explicit

The radar pipeline does not currently acquire a new SAIH HTML source. Therefore a
radar refresh must not imply simultaneous hydrology refresh.

The atomic snapshot now carries:

- `freshness.radar_timestamp`
- `freshness.hydrology_retrieved_at`
- `freshness.hydrology_refresh_coupled_to_radar = false`

The Worker health response exposes the same distinction.

## Regression fixtures

The following products are cryptographically pinned in
`Baseline/GOLDEN_PRODUCTS.sha256`:

- radar systems V0.3
- all radar tracks
- reliable tracks
- national marching-squares contours

The offline regression regenerates the products from the bundled radar sequence and
fails if any of those hashes changes.

## Verification commands

From repository root:

```sh
python Tests/verify_baseline.py
./Tests/run_offline_regression.sh
```

Optional syntax checks used during this audit:

```sh
tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler \
  --lib ES2022,DOM Tests/cloudflare-stubs.d.ts CloudflareV51/src/index.ts

swiftc -parse DanaSafeDeveloper/*.swift
```

## Audit results

- Baseline structural verification: PASS
- Golden product hashes: PASS
- Atomic snapshot contract: PASS
- Python syntax: PASS
- TypeScript syntax/type check with Cloudflare module stub: PASS
- Swift parser: PASS

## Environment limitation

A full Xcode build, Apple code signing, iOS simulator/device execution and actual
Cloudflare deployment cannot be certified from this Linux audit environment. The
package is prepared for those final checks on macOS/Xcode before being promoted to
V6 development baseline.
