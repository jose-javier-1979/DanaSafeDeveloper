# DanaSafe 5.1 Baseline

This directory is the audited pre-V6 reference package.

Start here:

1. Read `BASELINE_AUDIT_REPORT.md`.
2. Read `Cloudflare/ENDPOINT_CONTRACT_V5.md`.
3. Run `python Tests/verify_baseline.py`.
4. For full offline radar regression, run `./Tests/run_offline_regression.sh`.
5. Open `DanaSafeDeveloper.xcodeproj` in Xcode for the final iOS build/device test.

Do not add V6 Nowcast/Siri/notification code to this baseline. Branch/copy it and
use the derivative as the V6 development tree.
