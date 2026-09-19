#!/usr/bin/env python3
import hashlib
import json
import mimetypes
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


def snapshot_timestamp():
    if not SNAPSHOT.exists():
        return None
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("radar_timestamp")
    except Exception:
        return None


def run_pipeline(target_timestamp=None):
    # The lock serializes expensive refreshes. The timestamp check is deliberately
    # inside the lock: a request that waited for another refresh can reuse its
    # just-published snapshot instead of rerunning the complete pipeline.
    with LOCK:
        if target_timestamp and snapshot_timestamp() == target_timestamp:
            return SNAPSHOT.read_bytes(), "already_current"

        for script in PIPELINE:
            print(f"[DanaSafeContainer] stage={script}", flush=True)
            subprocess.run(
                ["python", str(SCRIPTS / script)],
                cwd=ENGINE,
                check=True,
                timeout=STAGE_TIMEOUT_SECONDS,
            )

        if not SNAPSHOT.exists():
            raise RuntimeError("Pipeline completed without an atomic snapshot")
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

    def current_manifest(self):
        if not MANIFEST.exists():
            raise FileNotFoundError("Current radar sequence manifest is missing")
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        frames = payload.get("frames", [])
        if len(frames) != 10:
            raise RuntimeError(f"Expected 10 archive frames, got {len(frames)}")
        return payload

    def archive_frame(self, frame_number):
        manifest = self.current_manifest()
        match = next((item for item in manifest["frames"] if int(item.get("frame", -1)) == frame_number), None)
        if not match:
            raise FileNotFoundError(f"Archive frame {frame_number} not present in current cycle")
        relative = Path(match["local_file"])
        source = (ENGINE / relative).resolve()
        engine_root = ENGINE.resolve()
        if engine_root != source and engine_root not in source.parents:
            raise RuntimeError("Archive frame resolved outside Engine")
        if not source.exists():
            raise FileNotFoundError(source)
        raw = source.read_bytes()
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        return raw, content_type, match

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self.send_json({
                "status": "ok",
                "engine": "DanaSafe Python/Pillow",
                "version": "5.1-baseline.1",
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
                manifest = self.current_manifest()
                self.send_json({
                    "provider": manifest.get("provider"),
                    "product": manifest.get("product"),
                    "frame_interval_minutes": manifest.get("frame_interval_minutes"),
                    "bounds": manifest.get("bounds"),
                    "frames": manifest.get("frames", []),
                })
            except Exception as exc:
                self.send_json({"status": "error", "error": str(exc)}, 404)
            return
        if path == "/archive/frame":
            try:
                query = parse_qs(urlsplit(self.path).query)
                frame_number = int(query.get("frame", ["0"])[0])
                raw, content_type, item = self.archive_frame(frame_number)
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
            self.send_json({"status": "error", "stage": str(exc.cmd[-1]), "returncode": exc.returncode}, 500)
        except Exception as exc:
            self.send_json({"status": "error", "error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        print("[DanaSafeContainer]", fmt % args, flush=True)


if __name__ == "__main__":
    print("DanaSafe 8.2 history-capable engine listening on :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
