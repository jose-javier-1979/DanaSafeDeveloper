# DanaSafe 8.1 — audited candidate

Open `DanaSafeDeveloper.xcodeproj` in Xcode 26.6 or newer available on the development Mac.

Read `AUDIT_VERSION_8_1.md` before Archive.

Recommended validation order on the Mac:

1. Release build for generic iOS.
2. Unit + UI tests on the single simulator `DanaSafe-Test-iPhone17Pro` (iOS 26.5).
3. Clean Release build.
4. Archive / Organizer validation.
5. Physical iPhone smoke test.

The Cloudflare production source tree and Engine are preserved. DanaSafe 8.1 changes are concentrated in the iOS layer, privacy/assets and tests.
