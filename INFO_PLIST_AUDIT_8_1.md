# DanaSafe 8.1 — Info.plist audit

## Result

The Info.plist is aligned with the current DanaSafe 8.1 operating model.

### Required/current keys

- `CFBundleDisplayName = DanaSafe`
- `CFBundleIdentifier = $(PRODUCT_BUNDLE_IDENTIFIER)`
- `CFBundleShortVersionString = $(MARKETING_VERSION)`
- `CFBundleVersion = $(CURRENT_PROJECT_VERSION)`
- `LSRequiresIPhoneOS = true`
- `NSLocationWhenInUseUsageDescription` present and scoped to foreground/on-demand location.
- `UISupportedInterfaceOrientations` includes portrait and both landscape orientations for iPhone.
- `UILaunchScreen` present.
- `ITSAppUsesNonExemptEncryption = false` because the app currently relies on Apple platform networking/TLS and does not implement custom or non-exempt cryptography.

### Keys intentionally not present

- No `NSLocationAlwaysAndWhenInUseUsageDescription`: DanaSafe does not request Always authorization.
- No background-location modes: DanaSafe does not perform background location tracking.
- No camera, microphone, photo-library, contacts, Bluetooth, HealthKit, HomeKit, or motion usage descriptions: corresponding APIs are not used.
- No ATS exceptions: the production endpoint is HTTPS.
- No background task identifiers: the current app does not register BGTaskScheduler tasks.
- No push-notification entitlement requirement: current notifications are local (`UNUserNotificationCenter`), not APNs remote push.
- No Siri usage string: current Siri integration uses App Intents/App Shortcuts rather than legacy SiriKit authorization.
- No temporary full-accuracy location dictionary: the app does not call `requestTemporaryFullAccuracyAuthorization`.

## Privacy consistency

Current code requests `requestWhenInUseAuthorization()` only and processes the user coordinate locally for ETA/threat/QPE. The production network endpoint is `https://danasafe-radar.firefritz.workers.dev`; the inspected app code does not transmit the user coordinate to this endpoint. The bundled `PrivacyInfo.xcprivacy` currently declares no tracking, no collected data types, and no required-reason API categories.

## Release note

Before App Store submission, generate Xcode's Privacy Report from the final Archive and verify the App Store Connect privacy answers against the binary actually submitted.
