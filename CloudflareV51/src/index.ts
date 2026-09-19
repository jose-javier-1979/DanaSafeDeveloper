import { Container } from "@cloudflare/containers";

const AEMET_BASE = "https://www.aemet.es";
const AEMET_TIMELINE = `${AEMET_BASE}/es/api-eltiempo/radar/timeline/compo/PB`;
const SNAPSHOT_KEY = "published/danasafe_live_snapshot.json";
const HISTORY_PREFIX = "history/cycles";

export interface Env {
  DANASAFE_ENGINE: any;
  SNAPSHOTS: any;
}

export class DanaSafeEngine extends Container {
  defaultPort = 8080;
  sleepAfter = "2m";
}

function json(data: unknown, status = 200, extra: Record<string, string> = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, no-cache, must-revalidate",
      ...extra,
    },
  });
}

async function fetchAEMETTimeline(): Promise<any> {
  const response = await fetch(AEMET_TIMELINE, {
    cache: "no-store",
    headers: {
      "user-agent": "DanaSafe-Cloudflare/8.2",
      accept: "application/json",
    },
  });
  if (!response.ok) throw new Error(`AEMET timeline HTTP ${response.status}`);
  return await response.json();
}

function latestElement(timeline: any): any {
  const root = Array.isArray(timeline) ? timeline[0] : timeline;
  const elements = Array.isArray(root?.Elementos) ? root.Elementos : [];
  if (!elements.length) throw new Error("AEMET timeline has no Elementos");
  return [...elements].sort((a, b) => Date.parse(a.Fecha) - Date.parse(b.Fecha)).at(-1);
}

async function readStoredSnapshot(env: Env): Promise<any | null> {
  const object = await env.SNAPSHOTS.get(SNAPSHOT_KEY);
  if (!object) return null;
  return JSON.parse(await object.text());
}

async function persistLiveSnapshot(env: Env, raw: ArrayBuffer, snapshot: any) {
  await env.SNAPSHOTS.put(SNAPSHOT_KEY, raw, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: String(snapshot?.radar_timestamp ?? ""),
      generated_at: String(snapshot?.generated_at ?? ""),
      schema_version: String(snapshot?.schema?.version ?? "8.2.0"),
      archive_policy: "history-before-live",
    },
  });
}

function sameInstant(a?: string, b?: string) {
  if (!a || !b) return false;
  const aa = Date.parse(a);
  const bb = Date.parse(b);
  return Number.isFinite(aa) && Number.isFinite(bb) && aa === bb;
}

function safeTimestamp(timestamp: string): string {
  if (!Number.isFinite(Date.parse(timestamp))) throw new Error(`Invalid archive timestamp: ${timestamp}`);
  return timestamp.replace(/:/g, "-").replace(/\//g, "-");
}

function archivePrefix(timestamp: string): string {
  return `${HISTORY_PREFIX}/${safeTimestamp(timestamp)}`;
}

function engineFor(env: Env) {
  return env.DANASAFE_ENGINE.getByName("danasafe-radar-engine");
}

async function runEngineRefresh(env: Env, targetTimestamp?: string): Promise<{ raw: ArrayBuffer; snapshot: any }> {
  const engine = engineFor(env);
  const target = targetTimestamp ? `?target=${encodeURIComponent(targetTimestamp)}` : "";
  const response = await engine.fetch(new Request(`http://container/refresh${target}`, {
    method: "POST",
    headers: { accept: "application/json", "cache-control": "no-store" },
  }));
  const raw = await response.arrayBuffer();
  if (!response.ok) {
    const message = new TextDecoder().decode(raw).slice(0, 1000);
    throw new Error(`DanaSafe engine HTTP ${response.status}: ${message}`);
  }
  const snapshot = JSON.parse(new TextDecoder().decode(raw));
  if (!snapshot?.radar_timestamp || !snapshot?.radar?.frames?.length) {
    throw new Error("DanaSafe engine returned an invalid atomic snapshot");
  }
  return { raw, snapshot };
}

async function fetchEngineManifest(env: Env): Promise<any> {
  const response = await engineFor(env).fetch(new Request("http://container/archive/manifest", {
    method: "GET",
    headers: { accept: "application/json", "cache-control": "no-store" },
  }));
  const raw = await response.text();
  if (!response.ok) throw new Error(`Archive manifest HTTP ${response.status}: ${raw.slice(0, 1000)}`);
  return JSON.parse(raw);
}

async function fetchEngineFrame(env: Env, frameNumber: number): Promise<{
  raw: ArrayBuffer;
  timestamp: string;
  filename: string;
  sha256: string;
  contentType: string;
}> {
  const response = await engineFor(env).fetch(new Request(`http://container/archive/frame?frame=${frameNumber}`, {
    method: "GET",
    headers: { "cache-control": "no-store" },
  }));
  const raw = await response.arrayBuffer();
  if (!response.ok) {
    const message = new TextDecoder().decode(raw).slice(0, 1000);
    throw new Error(`Archive frame ${frameNumber} HTTP ${response.status}: ${message}`);
  }
  return {
    raw,
    timestamp: response.headers.get("x-danasafe-timestamp") ?? "",
    filename: response.headers.get("x-danasafe-filename") ?? `frame_${String(frameNumber).padStart(2, "0")}`,
    sha256: response.headers.get("x-danasafe-sha256") ?? "",
    contentType: response.headers.get("content-type") ?? "application/octet-stream",
  };
}

async function archiveCycle(env: Env, rawSnapshot: ArrayBuffer, snapshot: any): Promise<{
  prefix: string;
  snapshotKey: string;
  manifestKey: string;
  frameKeys: string[];
}> {
  const radarTimestamp = String(snapshot?.radar_timestamp ?? "");
  const prefix = archivePrefix(radarTimestamp);
  const snapshotKey = `${prefix}/snapshot.json`;
  const manifestKey = `${prefix}/manifest.json`;

  // Idempotency: a completed cycle is immutable. Reusing it avoids needless R2 writes.
  const existingSnapshot = await env.SNAPSHOTS.head(snapshotKey);
  const existingManifest = await env.SNAPSHOTS.head(manifestKey);
  if (existingSnapshot && existingManifest && existingSnapshot.customMetadata?.archive_complete === "true") {
    const listed = await env.SNAPSHOTS.list({ prefix: `${prefix}/raw/`, limit: 20 });
    if ((listed.objects ?? []).length === 10) {
      return {
        prefix,
        snapshotKey,
        manifestKey,
        frameKeys: listed.objects.map((item: any) => item.key).sort(),
      };
    }
  }

  const manifest = await fetchEngineManifest(env);
  const frames = Array.isArray(manifest?.frames) ? manifest.frames : [];
  if (frames.length !== 10) throw new Error(`Archive requires exactly 10 raw frames; got ${frames.length}`);

  const manifestTimes = frames.map((frame: any) => String(frame?.fecha ?? ""));
  const latestManifestTimestamp = manifestTimes.at(-1);
  if (!sameInstant(latestManifestTimestamp, radarTimestamp)) {
    throw new Error(`Archive cycle mismatch: manifest=${latestManifestTimestamp} snapshot=${radarTimestamp}`);
  }

  const frameKeys: string[] = [];
  for (let frameNumber = 1; frameNumber <= 10; frameNumber += 1) {
    const frame = await fetchEngineFrame(env, frameNumber);
    const expected = frames[frameNumber - 1];
    if (!expected || !sameInstant(String(expected.fecha ?? ""), frame.timestamp)) {
      throw new Error(`Archive frame ${frameNumber} timestamp mismatch`);
    }

    const originalName = String(frame.filename || expected.filename || "frame").split("/").pop() || "frame";
    const key = `${prefix}/raw/${String(frameNumber).padStart(2, "0")}_${originalName}`;
    await env.SNAPSHOTS.put(key, frame.raw, {
      httpMetadata: { contentType: frame.contentType },
      customMetadata: {
        radar_timestamp: frame.timestamp,
        source_filename: originalName,
        frame_number: String(frameNumber),
        sha256: frame.sha256,
        archive_version: "8.2",
      },
    });
    frameKeys.push(key);
  }

  const manifestRaw = new TextEncoder().encode(JSON.stringify({
    archive_schema: { name: "DanaSafeRadarHistoryCycle", version: "8.2.0" },
    archived_at: new Date().toISOString(),
    radar_timestamp: radarTimestamp,
    frame_count: 10,
    source: "AEMET COMPO PB",
    original_manifest: manifest,
    raw_objects: frameKeys,
  }));

  await env.SNAPSHOTS.put(manifestKey, manifestRaw, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: radarTimestamp,
      frame_count: "10",
      archive_version: "8.2",
    },
  });

  // Snapshot is written last and marked complete. This acts as the cycle commit marker.
  await env.SNAPSHOTS.put(snapshotKey, rawSnapshot, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: radarTimestamp,
      generated_at: String(snapshot?.generated_at ?? ""),
      schema_version: String(snapshot?.schema?.version ?? ""),
      archive_version: "8.2",
      archive_complete: "true",
      raw_frame_count: "10",
    },
  });

  const verification = await Promise.all([
    env.SNAPSHOTS.head(snapshotKey),
    env.SNAPSHOTS.head(manifestKey),
    ...frameKeys.map((key) => env.SNAPSHOTS.head(key)),
  ]);
  if (verification.some((item) => !item)) throw new Error("R2 archive verification failed after write");

  return { prefix, snapshotKey, manifestKey, frameKeys };
}

async function historyStatus(env: Env, limit = 50) {
  const result = await env.SNAPSHOTS.list({ prefix: `${HISTORY_PREFIX}/`, limit: Math.min(Math.max(limit, 1), 1000) });
  const snapshots = (result.objects ?? [])
    .filter((item: any) => item.key.endsWith("/snapshot.json"))
    .map((item: any) => ({
      key: item.key,
      uploaded: item.uploaded,
      size: item.size,
      radar_timestamp: item.customMetadata?.radar_timestamp ?? null,
      archive_complete: item.customMetadata?.archive_complete === "true",
      raw_frame_count: Number(item.customMetadata?.raw_frame_count ?? 0),
    }))
    .sort((a: any, b: any) => String(b.uploaded).localeCompare(String(a.uploaded)));

  return {
    archive_version: "8.2",
    cycles_returned: snapshots.length,
    truncated: !!result.truncated,
    cycles: snapshots,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (path === "/") {
        return json({
          service: "DanaSafe Radar Backend",
          status: "online",
          version: "8.2-history.1",
          architecture: "Worker + Container + R2 immutable history",
          archive_policy: "archive-before-live",
          endpoints: [
            "/health",
            "/radar/snapshot",
            "/radar/refresh",
            "/radar/history",
            "/aemet/timeline",
            "/aemet/latest-image-info",
          ],
        });
      }

      if (path === "/aemet/timeline" && request.method === "GET") {
        return json(await fetchAEMETTimeline());
      }

      if (path === "/aemet/latest-image-info" && request.method === "GET") {
        const timeline = await fetchAEMETTimeline();
        const latest = latestElement(timeline);
        return json({
          status: "ok",
          timestamp: latest.Fecha,
          filename: latest["Nombre fichero"],
          source: "AEMET COMPO PB",
        });
      }

      if (path === "/health" && request.method === "GET") {
        const stored = await readStoredSnapshot(env);
        let latest: any = null;
        let aemetError: string | null = null;
        try { latest = latestElement(await fetchAEMETTimeline()); }
        catch (error) { aemetError = error instanceof Error ? error.message : String(error); }

        const history = await historyStatus(env, 1000);
        return json({
          service: "DanaSafe Radar Backend",
          status: "ok",
          version: "8.2-history.1",
          radar_timestamp: stored?.radar_timestamp ?? null,
          snapshot_generated_at: stored?.generated_at ?? null,
          hydrology_retrieved_at: stored?.hydrology?.retrieved_at ?? null,
          hydrology_refresh_coupled_to_radar: false,
          latest_aemet_timestamp: latest?.Fecha ?? null,
          in_sync: !!stored && !!latest && sameInstant(stored.radar_timestamp, latest.Fecha),
          history_enabled: true,
          history_cycles_visible: history.cycles_returned,
          archive_policy: "archive-before-live",
          aemet_error: aemetError,
        });
      }

      if (path === "/radar/history" && request.method === "GET") {
        const requested = Number(url.searchParams.get("limit") ?? "100");
        return json(await historyStatus(env, Number.isFinite(requested) ? requested : 100));
      }

      if (path === "/radar/snapshot" && request.method === "GET") {
        const object = await env.SNAPSHOTS.get(SNAPSHOT_KEY);
        if (!object) return json({ status: "missing", message: "No published snapshot yet. POST /radar/refresh first." }, 404);
        const headers = new Headers();
        object.writeHttpMetadata(headers);
        headers.set("content-type", "application/json; charset=utf-8");
        headers.set("cache-control", "no-store, no-cache, must-revalidate");
        headers.set("x-danasafe-source", "r2-atomic-snapshot");
        return new Response(object.body, { status: 200, headers });
      }

      if (path === "/radar/refresh" && request.method === "POST") {
        // 1) Ask AEMET directly, bypassing cache.
        const timeline = await fetchAEMETTimeline();
        const latest = latestElement(timeline);
        const latestTimestamp = latest.Fecha as string;

        // 2) If LIVE is already at the latest AEMET frame, return it immediately.
        const stored = await readStoredSnapshot(env);
        if (stored && sameInstant(stored.radar_timestamp, latestTimestamp)) {
          return json(stored, 200, {
            "x-danasafe-refresh": "unchanged",
            "x-aemet-latest": latestTimestamp,
          });
        }

        // 3) Build a fresh cycle in the Container.
        let result = await runEngineRefresh(env, latestTimestamp);

        // 4) Reconcile with AEMET once more in case a new ten-minute slot appeared.
        const latestAfter = latestElement(await fetchAEMETTimeline());
        const latestAfterTimestamp = latestAfter.Fecha as string;

        if (!sameInstant(result.snapshot.radar_timestamp, latestAfterTimestamp)) {
          const producedMs = Date.parse(result.snapshot.radar_timestamp);
          const latestAfterMs = Date.parse(latestAfterTimestamp);
          if (Number.isFinite(producedMs) && Number.isFinite(latestAfterMs) && producedMs < latestAfterMs) {
            result = await runEngineRefresh(env, latestAfterTimestamp);
          }
        }

        if (!sameInstant(result.snapshot.radar_timestamp, latestAfterTimestamp)) {
          throw new Error(`Pipeline/AEMET mismatch after reconciliation: pipeline=${result.snapshot.radar_timestamp} AEMET=${latestAfterTimestamp}`);
        }

        // 5) V8.2 invariant: immutable history is committed and verified BEFORE LIVE changes.
        const archived = await archiveCycle(env, result.raw, result.snapshot);

        // 6) Only after archive verification may the current atomic snapshot advance.
        await persistLiveSnapshot(env, result.raw, result.snapshot);

        // 7) Return the same bytes that were persisted as LIVE.
        return new Response(result.raw, {
          status: 200,
          headers: {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store, no-cache, must-revalidate",
            "x-danasafe-refresh": "updated",
            "x-aemet-latest": latestAfterTimestamp,
            "x-danasafe-history": "archived",
            "x-danasafe-history-prefix": archived.prefix,
          },
        });
      }

      return json({ status: "not_found", path, method: request.method }, 404);
    } catch (error) {
      return json({
        status: "error",
        error: error instanceof Error ? error.message : String(error),
      }, 500);
    }
  },
};
