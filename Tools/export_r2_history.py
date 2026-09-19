#!/usr/bin/env python3
"""Export verified DanaSafe R2 history to any local folder, including a Google Drive-synced folder."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request


def get(url: str) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "*/*",
            "Cache-Control": "no-store, no-cache",
            "User-Agent": "DanaSafe-History-Exporter/8.2",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read(), {k.lower(): v for k, v in response.headers.items()}


def json_get(url: str) -> dict:
    raw, _ = get(url)
    return json.loads(raw.decode("utf-8"))


def safe_name(timestamp: str) -> str:
    return re.sub(r"[^0-9A-Za-z._+-]+", "-", timestamp)


def endpoint(base: str, path: str, **params: object) -> str:
    base = base.rstrip("/")
    query = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
    return f"{base}/{path.lstrip('/')}?{query}" if query else f"{base}/{path.lstrip('/')}"


def export_cycle(base: str, output: Path, timestamp: str) -> dict:
    cycle_dir = output / safe_name(timestamp)
    raw_dir = cycle_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    snapshot_raw, _ = get(endpoint(base, "radar/history/cycle", timestamp=timestamp))
    manifest_raw, _ = get(endpoint(base, "radar/history/manifest", timestamp=timestamp))
    manifest = json.loads(manifest_raw.decode("utf-8"))

    frames = manifest.get("raw_frames") or []
    if len(frames) != 10:
        raise RuntimeError(f"{timestamp}: expected 10 raw_frames in manifest, got {len(frames)}")

    (cycle_dir / "snapshot.json").write_bytes(snapshot_raw)
    (cycle_dir / "manifest.json").write_bytes(manifest_raw)

    results = []
    for expected in frames:
        frame_number = int(expected["frame"])
        frame_raw, headers = get(
            endpoint(base, "radar/history/raw", timestamp=timestamp, frame=frame_number)
        )
        actual_sha = hashlib.sha256(frame_raw).hexdigest()
        expected_sha = str(expected.get("sha256") or "")
        header_sha = headers.get("x-danasafe-sha256", "")

        if not expected_sha or actual_sha != expected_sha:
            raise RuntimeError(
                f"{timestamp} frame {frame_number}: SHA256 mismatch "
                f"manifest={expected_sha} actual={actual_sha}"
            )
        if header_sha and header_sha != actual_sha:
            raise RuntimeError(
                f"{timestamp} frame {frame_number}: R2 metadata SHA256 mismatch "
                f"header={header_sha} actual={actual_sha}"
            )

        expected_bytes = int(expected.get("bytes") or 0)
        if expected_bytes and expected_bytes != len(frame_raw):
            raise RuntimeError(
                f"{timestamp} frame {frame_number}: byte count mismatch "
                f"manifest={expected_bytes} actual={len(frame_raw)}"
            )

        filename = f"{frame_number:02d}_{expected.get('source_filename') or 'radar.bin'}"
        (raw_dir / filename).write_bytes(frame_raw)
        results.append(
            {
                "frame": frame_number,
                "timestamp": expected.get("timestamp"),
                "filename": filename,
                "bytes": len(frame_raw),
                "sha256": actual_sha,
                "verified": True,
            }
        )

    verification = {
        "archive_version": "8.2",
        "radar_timestamp": timestamp,
        "snapshot_bytes": len(snapshot_raw),
        "manifest_bytes": len(manifest_raw),
        "raw_frame_count": len(results),
        "all_sha256_verified": all(item["verified"] for item in results),
        "frames": results,
    }
    (cycle_dir / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="DanaSafe 8.2 history-capable backend URL")
    parser.add_argument("--output", required=True, help="Destination folder; may be inside Google Drive")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timestamp", help="Export only one exact archived radar timestamp")
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    if args.timestamp:
        timestamps = [args.timestamp]
    else:
        wanted = max(1, args.limit)
        timestamps = []
        cursor = None
        while len(timestamps) < wanted:
            page_size = min(500, wanted - len(timestamps))
            params = {"limit": page_size}
            if cursor:
                params["cursor"] = cursor
            history = json_get(endpoint(args.base_url, "radar/history", **params))
            page = [
                str(item["radar_timestamp"])
                for item in history.get("cycles", [])
                if item.get("archive_complete") and item.get("radar_timestamp")
            ]
            timestamps.extend(page)
            cursor = history.get("next_cursor")
            if not cursor or not page:
                break

    if not timestamps:
        print("No completed DanaSafe 8.2 archive cycles found.")
        return 0

    summaries = []
    for timestamp in timestamps:
        print(f"Exporting {timestamp}...")
        summaries.append(export_cycle(args.base_url, output, timestamp))
        print(f"  verified 10/10 raw frames: {timestamp}")

    index = {
        "archive_version": "8.2",
        "base_url": args.base_url,
        "cycle_count": len(summaries),
        "cycles": summaries,
    }
    (output / "DanaSafe-history-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Export complete: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
