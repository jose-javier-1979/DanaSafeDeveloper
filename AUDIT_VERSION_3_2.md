# DanaSafe V3.2 Manual Refresh — audit

## Design decision
Radar updating is intentionally manual. There is no clock trigger, no 60-second polling and no 10-minute server refresh loop.

## Refresh contract
The Radar toolbar circular-arrow button and the Tools refresh button both call the same operation:

1. GET `/refresh` on the Mac server.
2. Server queries the AEMET COMPO timeline at that moment.
3. Server selects the 10 newest consecutive AEMET frames currently available.
4. Server downloads all 10 frames.
5. DanaSafe runs the complete recovered radar algorithm.
6. Systems, reliable tracks and Marching Squares contours are validated against the same 10-frame cycle.
7. A single atomic snapshot is published.
8. The app downloads `/snapshot` and publishes all radar products together.

If any step fails, publication does not occur and the previous complete snapshot remains intact.

## Validation performed in build environment
- All Python files compile with `py_compile`.
- All Swift sources pass `swiftc -parse` where available.
- All 18 JSON files parse successfully.
- `Info.plist` parses successfully.
- Local server `/health` returns HTTP 200 with version `3.2.0-manual-refresh`.
- Search confirms no active `Task.sleep`, clock watch, target-slot, interval or automatic-refresh logic in the operational app/server path.

## Network limitation of build environment
A live AEMET download could not be completed in the build container because DNS resolution for external hosts is disabled there (`Temporary failure in name resolution`). The failure occurred at the intended first network step and did not modify the published snapshot. The same request is designed to run from the user's Mac when the Refresh button is pressed.
