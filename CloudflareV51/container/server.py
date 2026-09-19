#!/usr/bin/env python3
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path("/app")
ENGINE = ROOT / "Engine"
SCRIPTS = ENGINE / "Scripts"
SNAPSHOT = ENGINE / "Data/Published/danasafe_live_snapshot.json"
MANIFEST = ENGINE / "Data/Radar/AEMET/NationalSequence/sequence_manifest.json"
ARCHIVE_STAGING = ENGINE / "Data/ArchiveStaging"
LOCK = threading.Lock()
PIPELINE = [
    "download_compo_sequence.py",
    "process_compo_sequence.py",
    "build_radar_systems_v03.py",
    "track_radar_sequence.py",
    "preview_reliable_tracks.py",
    "sync_latest_frame.py",
    "national_marching_squares.py",
    "publish_live_snapshot.py",
]
STAGE_TIMEOUT_SECONDS = 240
MAX_STAGED_CYCLES = 4


def snapshot_timestamp():
    if not SNAPSHOT.exists():
        return None
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("radar_timestamp")
    except Exception:
        return None


def safe_stage_name(timestamp):
    if not timestamp:
        raise ValueError("archive timestamp is required")
    return re.sub(r"[^0-9A-Za-z._+-]+", "-", str(timestamp))


def stage_dir(timestamp):
    return ARCHIVE_STAGING / safe_stage_name(timestamp)


def read_current_manifest():
    if not MANIFEST.exists():
        raise FileNotFoundError("Current radar sequence manifest is missing")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frames = payload.get("frames", [])
    if len(frames) != 10:
        raise RuntimeError(f"Expected 10 archive frames, got {len(frames)}")
    return payload


def staged_manifest(timestamp):
    path = stage_dir(timestamp) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"Staged archive cycle is missing: {timestamp}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    frames = payload.get("frames", [])
    if len(frames) != 10:
        raise RuntimeError(f"Staged cycle {timestamp} has {len(frames)} frames")
    return payload


def staged_cycle_complete(timestamp):
    try:
        payload = staged_manifest(timestamp)
        root = stage_dir(timestamp)
        if not (root / "snapshot.json").exists():
            return False
        return all((root / "raw" / frame["staged_file"]).exists() for frame in payload["frames"])
    except Exception:
        return False


def cleanup_staging():
    ARCHIVE_STAGING.mkdir(parents=True, exist_ok=True)
    candidates = [
        path for path in ARCHIVE_STAGING.iterdir()
        if path.is_dir() and not path.name.endswith(".tmp")
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for old in candidates[MAX_STAGED_CYCLES:]:
        shutil.rmtree(old, ignore_errors=True)


def stage_archive_cycle(expected_timestamp):
    manifest = read_current_manifest()
    frames = manifest["frames"]
    actual_timestamp = str(frames[-1].get("fecha") or "")
    if expected_timestamp and actual_timestamp != str(expected_timestamp):
        raise RuntimeError(
            f"Archive staging mismatch: manifest={actual_timestamp} expected={expected_timestamp}"
        )
    if snapshot_timestamp() != actual_timestamp:
        raise RuntimeError(
            f"Archive staging snapshot mismatch: snapshot={snapshot_timestamp()} manifest={actual_timestamp}"
        )

    final = stage_dir(actual_timestamp)
    if staged_cycle_complete(actual_timestamp):
        return final

    ARCHIVE_STAGING.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVE_STAGING / (safe_stage_name(actual_timestamp) + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "raw").mkdir(parents=True, exist_ok=True)

    staged_frames = []
    for frame in frames:
        frame_number = int(frame.get("frame", -1))
        if frame_number < 1 or frame_number > 10:
            raise RuntimeError(f"Invalid frame number in manifest: {frame_number}")

        relative = Path(frame["local_file"])
        source = (ENGINE / relative).resolve()
        engine_root = ENGINE.resolve()
        if engine_root != source and engine_root not in source.parents:
            raise RuntimeError("Archive source resolved outside Engine")
        if not source.exists():
            raise FileNotFoundError(source)

        original_name = str(frame.get("filename") or source.name).split("/")[-1]
        staged_file = f"{frame_number:02d}_{original_name}"
        shutil.copy2(source, tmp / "raw" / staged_file)
        staged_frames.append({**frame, "staged_file": staged_file})

    shutil.copy2(SNAPSHOT, tmp / "snapshot.json")
    staged_payload = {
        "provider": manifest.get("provider"),
        "product": manifest.get("product"),
        "region": manifest.get("region"),
        "frame_interval_minutes": manifest.get("frame_interval_minutes"),
        "bounds": manifest.get("bounds"),
        "radar_timestamp": actual_timestamp,
        "frames": staged_frames,
    }
    (tmp / "manifest.json").write_text(
        json.dumps(staged_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if final.exists():
        shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp, final)
    cleanup_staging()
    return final


def run_pipeline(target_timestamp=None):
    # The same lock now covers both the mutable processing pipeline and creation
    # of an immutable, timestamp-specific staging bundle. Subsequent Worker reads
    # never depend on sequence_manifest.json after this function returns.
    with LOCK:
        if target_timestamp and snapshot_timestamp() == target_timestamp:
            try:
                stage_archive_cycle(target_timestamp)
                return SNAPSHOT.read_bytes(), "already_current"
            except Exception as exc:
                print(
                    f"[DanaSafeContainer] current snapshot could not be staged; rebuilding: {exc}",
                    flush=True,
                )

        env = os.environ.copy()
        if target_timestamp:
            env["DANASAFE_TARGET_TIMESTAMP"] = target_timestamp
        else:
            env.pop("DANASAFE_TARGET_TIMESTAMP", None)

        for script in PIPELINE:
            print(f"[DanaSafeContainer] stage={script}", flush=True)
            subprocess.run(
                ["python", str(SCRIPTS / script)],
                cwd=ENGINE,
                check=True,
                timeout=STAGE_TIMEOUT_SECONDS,
                env=env,
            )

        if not SNAPSHOT.exists():
            raise RuntimeError("Pipeline completed without an atomic snapshot")

        produced_timestamp = snapshot_timestamp()
        if target_timestamp and produced_timestamp != target_timestamp:
            raise RuntimeError(
                f"Pipeline target mismatch: produced={produced_timestamp} target={target_timestamp}"
            )
        stage_archive_cycle(produced_timestamp)
        return SNAPSHOT.read_bytes(), "updated"


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200, extra_headers=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(raw)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def send_snapshot(self, raw, refresh_state=None):
        self.send_response(200)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(raw)))
        if refresh_state:
            self.send_header("x-danasafe-engine-refresh", refresh_state)
        self.end_headers()
        self.wfile.write(raw)

    def send_bytes(self, raw, content_type="application/octet-stream", extra_headers=None):
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(raw)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def archive_frame(self, timestamp, frame_number):
        manifest = staged_manifest(timestamp)
        match = next(
            (item for item in manifest["frames"] if int(item.get("frame", -1)) == frame_number),
            None,
        )
        if not match:
            raise FileNotFoundError(
                f"Archive frame {frame_number} not present in staged cycle {timestamp}"
            )

        source = stage_dir(timestamp) / "raw" / match["staged_file"]
        if not source.exists():
            raise FileNotFoundError(source)
        raw = source.read_bytes()
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        return raw, content_type, match

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self.send_json({
                "status": "ok",
                "engine": "DanaSafe Python/Pillow",
                "version": "8.2-history.2",
                "radar_timestamp": snapshot_timestamp(),
            })
            return

        if path == "/snapshot":
            if not SNAPSHOT.exists():
                self.send_json({"status": "missing"}, 404)
                return
            self.send_snapshot(SNAPSHOT.read_bytes())
            return

        if path == "/archive/manifest":
            try:
                timestamp = query.get("timestamp", [None])[0]
                if not timestamp:
                    raise ValueError("timestamp query parameter is required")
                manifest = staged_manifest(timestamp)
                self.send_json(manifest)
            except Exception as exc:
                self.send_json({"status": "error", "error": str(exc)}, 404)
            return

        if path == "/archive/frame":
            try:
                timestamp = query.get("timestamp", [None])[0]
                if not timestamp:
                    raise ValueError("timestamp query parameter is required")
                frame_number = int(query.get("frame", ["0"])[0])
                raw, content_type, item = self.archive_frame(timestamp, frame_number)
                self.send_bytes(raw, content_type, {
                    "x-danasafe-frame": str(frame_number),
                    "x-danasafe-timestamp": str(item.get("fecha", "")),
                    "x-danasafe-filename": str(item.get("filename", "")),
                    "x-danasafe-sha256": hashlib.sha256(raw).hexdigest(),
                })
            except Exception as exc:
                self.send_json({"status": "error", "error": str(exc)}, 404)
            return

        self.send_json({"status": "not_found"}, 404)

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path != "/refresh":
            self.send_json({"status": "not_found"}, 404)
            return

        target = parse_qs(parsed.query).get("target", [None])[0]
        try:
            raw, refresh_state = run_pipeline(target_timestamp=target)
            self.send_snapshot(raw, refresh_state=refresh_state)
        except subprocess.TimeoutExpired as exc:
            self.send_json({
                "status": "error",
                "stage": str(exc.cmd[-1]),
                "error": "stage_timeout",
                "timeout_seconds": STAGE_TIMEOUT_SECONDS,
            }, 504)
        except subprocess.CalledProcessError as exc:
            self.send_json(
                {"status": "error", "stage": str(exc.cmd[-1]), "returncode": exc.returncode},
                500,
            )
        except Exception as exc:
            self.send_json({"status": "error", "error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        print("[DanaSafeContainer]", fmt % args, flush=True)


if __name__ == "__main__":
    print("DanaSafe 8.2 history-capable engine listening on :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
