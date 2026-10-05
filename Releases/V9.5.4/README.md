# DanaSafe V9.5.4 — ETA freshness compensation

Release candidate checkpoint created from the audited V9.5.4 package.

## Purpose
Correct ETA, current distance, closest approach and 10/30/60-minute QPE when the latest processed AEMET radar frame is older than the user's current clock.

## Time-origin rule
The atmospheric position belongs to `track.latestTimestamp` (fallback: snapshot `radarTimestamp`), not to the moment the user opens the app.

```
age = max(0, userNow - observationTimestamp)
currentPosition = observedPosition + motionVector * age
remainingHorizon = max(0, originalNowcastHorizon - age)
```

ETA and QPE are recomputed from the freshness-adjusted position.

## Release status
- Swift parser: PASS (153 Swift files)
- JSON syntax: PASS (28 JSON files)
- plist parsing: PASS
- shell syntax: PASS
- ZIP integrity: PASS
- Xcode/device validation: PENDING

## Audited artifact
`DanaSafeDeveloper-V9.5.4-ETA-FRESHNESS-AUDITED.zip`

SHA-256:
`e25ec3eba28f86269d58c004919d83671c29ae6e29641f03300975ee59f2857c`

## Base
V9.5.3 LOCATION SEARCH AUDITED.

## Safety scope
Hydrology, Navarra, ECRINS, reservoirs, MapKit place search and radar-system generation were intentionally left outside this patch.
