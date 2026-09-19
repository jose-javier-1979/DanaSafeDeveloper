#!/usr/bin/env python3
"""DanaSafe V6 radar nowcast.

Builds root-system temporal tracks from radar_systems_v03.json and publishes a
location-independent motion forecast. User-specific ETA/threat evaluation stays
on the device so the backend does not need the user's live GPS position.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import math
import os
import tempfile
from typing import Any

BASE = Path(__file__).resolve().parents[1]
PROC = BASE / "Data/Radar/AEMET/NationalSequence/Processed"
RADAR = PROC / "radar_systems_v03.json"
OUT = PROC / "radar_nowcast_v6.json"

MAX_ASSOCIATION_KM = 90.0
MAX_SPEED_KMH = 180.0
MIN_SPEED_KMH = 2.0
HORIZON_MINUTES = (15, 30, 45, 60, 90, 120)
EARTH_KM_PER_DEG = 111.32


def parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def local_xy_km(a: dict[str, float], b: dict[str, float]) -> tuple[float, float]:
    lat_mid = math.radians((a["latitude"] + b["latitude"]) * 0.5)
    east = (b["longitude"] - a["longitude"]) * EARTH_KM_PER_DEG * math.cos(lat_mid)
    north = (b["latitude"] - a["latitude"]) * EARTH_KM_PER_DEG
    return east, north


def distance_km(a: dict[str, float], b: dict[str, float]) -> float:
    east, north = local_xy_km(a, b)
    return math.hypot(east, north)


def offset(coord: dict[str, float], east_km: float, north_km: float) -> dict[str, float]:
    lat = coord["latitude"] + north_km / EARTH_KM_PER_DEG
    cos_lat = max(abs(math.cos(math.radians(coord["latitude"]))), 1e-6)
    lon = coord["longitude"] + east_km / (EARTH_KM_PER_DEG * cos_lat)
    return {"longitude": round(lon, 6), "latitude": round(lat, 6)}


def association_score(previous: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, float] | None:
    d = distance_km(previous["centroid"], candidate["centroid"])
    if d > MAX_ASSOCIATION_KM:
        return None
    a1 = max(int(previous.get("root_area_px", 0)), 1)
    a2 = max(int(candidate.get("root_area_px", 0)), 1)
    area_ratio = min(a1, a2) / max(a1, a2)
    z_penalty = abs(int(previous.get("zmax_dbz", 0)) - int(candidate.get("zmax_dbz", 0))) / 60.0
    score = d / MAX_ASSOCIATION_KM + (1.0 - area_ratio) * 0.45 + z_penalty * 0.25
    return score, d


def build_tracks(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    serial = 1
    for frame in sorted(frames, key=lambda f: int(f["frame"])):
        used: set[str] = set()
        for track in tracks:
            latest = track["observations"][-1]
            if int(latest["frame"]) != int(frame["frame"]) - 1:
                continue
            candidates = []
            for system in frame.get("systems", []):
                if system["id"] in used:
                    continue
                scored = association_score(latest, system)
                if scored is not None:
                    score, d = scored
                    candidates.append((score, d, system))
            candidates.sort(key=lambda item: item[0])
            if candidates and candidates[0][0] < 1.0:
                _, _, best = candidates[0]
                track["observations"].append(best)
                used.add(best["id"])
        for system in frame.get("systems", []):
            if system["id"] not in used:
                tracks.append({
                    "id": f"T{serial:03d}",
                    "observations": [system],
                })
                serial += 1
    return tracks


def motion(track: dict[str, Any]) -> dict[str, float] | None:
    obs = track["observations"][-4:]
    if len(obs) < 3:
        return None
    east = north = hours = 0.0
    segment_vectors: list[tuple[float, float]] = []
    for a, b in zip(obs, obs[1:]):
        dt = (parse_iso(b["timestamp"]) - parse_iso(a["timestamp"])).total_seconds() / 3600.0
        if dt <= 0:
            continue
        de, dn = local_xy_km(a["centroid"], b["centroid"])
        east += de
        north += dn
        hours += dt
        segment_vectors.append((de / dt, dn / dt))
    if hours <= 0:
        return None
    ve = east / hours
    vn = north / hours
    speed = math.hypot(ve, vn)
    if speed < MIN_SPEED_KMH or speed > MAX_SPEED_KMH:
        return None
    bearing = math.degrees(math.atan2(ve, vn))
    if bearing < 0:
        bearing += 360.0

    # Direction/speed consistency over recent segments. 1 = stable vector.
    if len(segment_vectors) >= 2:
        mean_ve = sum(v[0] for v in segment_vectors) / len(segment_vectors)
        mean_vn = sum(v[1] for v in segment_vectors) / len(segment_vectors)
        residuals = [math.hypot(v[0] - mean_ve, v[1] - mean_vn) for v in segment_vectors]
        mean_residual = sum(residuals) / len(residuals)
        stability = max(0.0, min(1.0, 1.0 - mean_residual / max(speed, 1.0)))
    else:
        stability = 0.5

    return {
        "speed_kmh": round(speed, 3),
        "bearing_deg": round(bearing, 3),
        "velocity_east_kmh": round(ve, 3),
        "velocity_north_kmh": round(vn, 3),
        "vector_stability": round(stability, 4),
    }


def track_record(track: dict[str, Any]) -> dict[str, Any] | None:
    m = motion(track)
    if m is None:
        return None
    observations = track["observations"]
    latest = observations[-1]
    persistence = min(1.0, len(observations) / 6.0)
    confidence = min(0.95, 0.20 + 0.45 * persistence + 0.30 * m["vector_stability"])
    radius_km = max(4.0, math.sqrt(max(int(latest.get("root_area_px", 0)), 1)) * 1.4)
    forecasts = []
    for minutes in HORIZON_MINUTES:
        hours = minutes / 60.0
        forecasts.append({
            "minutes": minutes,
            "coordinate": offset(
                latest["centroid"],
                m["velocity_east_kmh"] * hours,
                m["velocity_north_kmh"] * hours,
            ),
        })
    return {
        "id": track["id"],
        "frame_count": len(observations),
        "first_timestamp": observations[0]["timestamp"],
        "latest_timestamp": latest["timestamp"],
        "latest_system_id": latest["id"],
        "latest_coordinate": latest["centroid"],
        "root_area_px": int(latest.get("root_area_px", 0)),
        "zmax_dbz": int(latest.get("zmax_dbz", 0)),
        "radius_km": round(radius_km, 3),
        "motion": m,
        "confidence": round(confidence, 4),
        "forecast": forecasts,
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main() -> None:
    data = json.loads(RADAR.read_text(encoding="utf-8"))
    frames = data.get("frames", [])
    if len(frames) != 10:
        raise RuntimeError(f"Expected 10 radar frames, got {len(frames)}")
    tracks = build_tracks(frames)
    records = [record for t in tracks if (record := track_record(t)) is not None]
    records.sort(key=lambda r: (-r["confidence"], -r["zmax_dbz"], r["id"]))
    latest = frames[-1]["timestamp"]
    result = {
        "schema": {"name": "DanaSafeRadarNowcast", "version": "6.0.0"},
        "generated_at": datetime.now().astimezone().isoformat(),
        "radar_timestamp": latest,
        "horizon_minutes": max(HORIZON_MINUTES),
        "port": {
            "source": "RadarNowcastEngineV1/NowcastEngine.swift",
            "core_semantics": "association + recent-4 motion vector preserved",
            "backend_extensions": ["vector_stability", "location_independent_forecast", "backend_confidence"],
        },
        "association": {
            "max_distance_km": MAX_ASSOCIATION_KM,
            "minimum_motion_speed_kmh": MIN_SPEED_KMH,
            "maximum_motion_speed_kmh": MAX_SPEED_KMH,
            "recent_observations": 4,
        },
        "track_count": len(records),
        "tracks": records,
    }
    atomic_write_json(OUT, result)
    print(f"Published V6 nowcast: {len(records)} tracks · radar {latest}")
    print(f"Nowcast: {OUT}")


if __name__ == "__main__":
    main()
