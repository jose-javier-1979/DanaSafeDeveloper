#!/usr/bin/env python3
"""Public DanaSafe Cloudflare backend smoke test.
Run on a machine with Internet access. It performs read-only GET requests only.
"""
import json
import sys
import urllib.request

BASE = "https://danasafe-radar.firefritz.workers.dev"
PATHS = ["/", "/health", "/radar/snapshot", "/aemet/timeline", "/aemet/latest-image-info"]


def main() -> int:
    ok = True
    for path in PATHS:
        url = BASE + path
        print(f"\n=== {url} ===")
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "DanaSafe-V5-Backend-Test/1.0",
                    "Accept": "application/json",
                    "Cache-Control": "no-cache, no-store",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                print("HTTP", response.status)
                print("Content-Type:", response.headers.get("Content-Type"))
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        print("JSON keys:", ", ".join(sorted(obj.keys())))
                        if path == "/radar/snapshot":
                            if "snapshot" in obj:
                                snap = obj.get("snapshot") or {}
                                print("Contract: compact Cloudflare snapshot")
                                print("timestamp:", snap.get("timestamp"))
                                print("systems:", len(snap.get("systems") or []))
                            elif "radar" in obj:
                                radar = obj.get("radar") or {}
                                frames = radar.get("frames") or []
                                print("Contract: atomic DanaSafe snapshot")
                                print("radar_timestamp:", obj.get("radar_timestamp"))
                                print("frames:", len(frames))
                            elif "frames" in obj:
                                print("Contract: direct RadarSystemsFile")
                                print("frames:", len(obj.get("frames") or []))
                            else:
                                print("WARNING: unknown /radar/snapshot contract")
                                ok = False
                    else:
                        print("JSON type:", type(obj).__name__)
                except Exception as exc:
                    print("ERROR: non-JSON response:", exc)
                    print(raw[:500])
                    ok = False
        except Exception as exc:
            print("ERROR:", repr(exc))
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
