# RadarNowcastEngine V1 -> DanaSafe Engine V6 formal port

## Source

The reference implementation is `RadarNowcastEngineV1/RadarNowcastEngineV1/NowcastEngine.swift` supplied during DanaSafe development.

The server-side port is `Engine/Scripts/build_nowcast_v6.py`.

## Core semantics preserved

The regression test reproduces the Swift V1 core algorithm independently and verifies the Python output for the bundled 10-frame fixture.

Preserved behavior:

- frames processed in ascending frame number;
- one-to-one nearest association from the immediately previous frame;
- maximum association distance: 90 km;
- score: distance/90 + area-ratio penalty × 0.45 + Zmax penalty × 0.25;
- association accepted only when score < 1.0;
- motion uses the latest four observations and requires at least three;
- local planar east/north conversion uses 111.32 km/degree and midpoint latitude;
- accepted speeds: 2–180 km/h;
- bearing uses `atan2(east, north)` normalized to 0–360°;
- effective radius: `max(4 km, sqrt(root_area_px) × 1.4)`.

`Tests/verify_v6.py` verifies track IDs, persistence and the four motion outputs against an independent Python transcription of the Swift V1 semantics, tolerance 0.01.

## V6 backend extensions

The server port adds information that was not required by the V1 prototype:

- vector stability from recent segment residuals;
- location-independent projection at 15/30/45/60/90/120 minutes;
- backend confidence derived from persistence + vector stability;
- atomic JSON publication tied to the same radar timestamp.

These extensions do not alter the V5 radar extraction, radar-system generation, reliable tracks or contours. Golden hashes for those products remain pinned and must continue to pass.

## User-specific evaluation

`NowcastEvaluator.swift` performs the device-side projection against the user's coordinate:

- current distance;
- closest approach over the 120-minute horizon;
- ETA when the projected trajectory intersects the effective system radius;
- geometric confidence adjustment;
- DanaSafe threat category.

This split keeps the user's live coordinate on the iPhone for the normal interactive workflow.
