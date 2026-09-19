import { Container } from "@cloudflare/containers";

const AEMET_BASE = "https://www.aemet.es";
const AEMET_TIMELINE = `${AEMET_BASE}/es/api-eltiempo/radar/timeline/compo/PB`;
const SNAPSHOT_KEY = "published/danasafe_live_snapshot.json";
const HISTORY_PREFIX = "history/cycles";
const HISTORY_INDEX_PREFIX = "history/index";
const MAX_HISTORY_PAGE = 500;
const REVERSE_TIME_MAX = 9_999_999_999_999;

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

async function readStoredSnapshotRecord(env: Env): Promise<{ raw: ArrayBuffer; snapshot: any } | null> {
  const object = await env.SNAPSHOTS.get(SNAPSHOT_KEY);
  if (!object) return null;
  const raw = await object.arrayBuffer();
  const snapshot = JSON.parse(new TextDecoder().decode(raw));
  return { raw, snapshot };
}

async function readStoredSnapshot(env: Env): Promise<any | null> {
  return (await readStoredSnapshotRecord(env))?.snapshot ?? null;
}

async function persistLiveSnapshot(
  env: Env,
  raw: ArrayBuffer,
  snapshot: any,
): Promise<"updated" | "skipped-newer-live"> {
  // Last-moment monotonicity guard. Archive writes can take longer than another
  // concurrent refresh, so never overwrite a LIVE snapshot with an older cycle.
  const current = await readStoredSnapshot(env);
  const incomingMs = Date.parse(String(snapshot?.radar_timestamp ?? ""));
  const currentMs = Date.parse(String(current?.radar_timestamp ?? ""));
  if (Number.isFinite(incomingMs) && Number.isFinite(currentMs) && currentMs > incomingMs) {
    return "skipped-newer-live";
  }

  await env.SNAPSHOTS.put(SNAPSHOT_KEY, raw, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: String(snapshot?.radar_timestamp ?? ""),
      generated_at: String(snapshot?.generated_at ?? ""),
      schema_version: String(snapshot?.schema?.version ?? "8.2.0"),
      archive_policy: "archive-before-live",
    },
  });
  return "updated";
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

function historyIndexKey(timestamp: string): string {
  const ms = Date.parse(timestamp);
  if (!Number.isFinite(ms)) throw new Error(`Invalid history index timestamp: ${timestamp}`);
  const reversed = Math.max(0, REVERSE_TIME_MAX - ms).toString().padStart(13, "0");
  return `${HISTORY_INDEX_PREFIX}/${reversed}_${safeTimestamp(timestamp)}.json`;
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

async function fetchEngineManifest(env: Env, timestamp: string): Promise<any> {
  const response = await engineFor(env).fetch(new Request(
    `http://container/archive/manifest?timestamp=${encodeURIComponent(timestamp)}`,
    {
      method: "GET",
      headers: { accept: "application/json", "cache-control": "no-store" },
    },
  ));
  const raw = await response.text();
  if (!response.ok) throw new Error(`Archive manifest HTTP ${response.status}: ${raw.slice(0, 1000)}`);
  return JSON.parse(raw);
}

async function fetchEngineFrame(env: Env, timestamp: string, frameNumber: number): Promise<{
  raw: ArrayBuffer;
  timestamp: string;
  filename: string;
  sha256: string;
  contentType: string;
}> {
  const response = await engineFor(env).fetch(new Request(
    `http://container/archive/frame?timestamp=${encodeURIComponent(timestamp)}&frame=${frameNumber}`,
    {
      method: "GET",
      headers: { "cache-control": "no-store" },
    },
  ));
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

async function archiveIsComplete(env: Env, timestamp: string): Promise<boolean> {
  const marker = await env.SNAPSHOTS.head(historyIndexKey(timestamp));
  return !!marker && marker.customMetadata?.archive_complete === "true";
}

async function archiveCycle(env: Env, rawSnapshot: ArrayBuffer, snapshot: any): Promise<{
  prefix: string;
  snapshotKey: string;
  manifestKey: string;
  indexKey: string;
  frameKeys: string[];
}> {
  const radarTimestamp = String(snapshot?.radar_timestamp ?? "");
  const prefix = archivePrefix(radarTimestamp);
  const snapshotKey = `${prefix}/snapshot.json`;
  const manifestKey = `${prefix}/manifest.json`;
  const indexKey = historyIndexKey(radarTimestamp);

  // The index marker is written last, after the whole cycle has been verified.
  // Its presence is therefore the authoritative idempotency/commit check.
  if (await archiveIsComplete(env, radarTimestamp)) {
    return { prefix, snapshotKey, manifestKey, indexKey, frameKeys: [] };
  }

  const manifest = await fetchEngineManifest(env, radarTimestamp);
  const frames = Array.isArray(manifest?.frames) ? manifest.frames : [];
  if (frames.length !== 10) throw new Error(`Archive requires exactly 10 raw frames; got ${frames.length}`);

  const manifestTimes = frames.map((frame: any) => String(frame?.fecha ?? ""));
  const snapshotTimes = Array.isArray(snapshot?.radar?.frames)
    ? snapshot.radar.frames.map((frame: any) => String(frame?.timestamp ?? ""))
    : [];
  if (snapshotTimes.length !== 10) {
    throw new Error(`Archive snapshot requires exactly 10 radar frames; got ${snapshotTimes.length}`);
  }
  for (let i = 0; i < 10; i += 1) {
    if (!sameInstant(manifestTimes[i], snapshotTimes[i])) {
      throw new Error(
        `Archive cycle frame mismatch at ${i + 1}: manifest=${manifestTimes[i]} snapshot=${snapshotTimes[i]}`,
      );
    }
  }

  const latestManifestTimestamp = manifestTimes.at(-1);
  if (!sameInstant(latestManifestTimestamp, radarTimestamp)) {
    throw new Error(`Archive cycle mismatch: manifest=${latestManifestTimestamp} snapshot=${radarTimestamp}`);
  }

  const frameKeys: string[] = [];
  const frameRecords: Array<{
    frame: number;
    timestamp: string;
    source_filename: string;
    r2_key: string;
    sha256: string;
    bytes: number;
  }> = [];

  for (let frameNumber = 1; frameNumber <= 10; frameNumber += 1) {
    const frame = await fetchEngineFrame(env, radarTimestamp, frameNumber);
    const expected = frames[frameNumber - 1];
    if (!expected || !sameInstant(String(expected.fecha ?? ""), frame.timestamp)) {
      throw new Error(`Archive frame ${frameNumber} timestamp mismatch`);
    }
    if (!frame.sha256) {
      throw new Error(`Archive frame ${frameNumber} is missing source SHA-256`);
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
    frameRecords.push({
      frame: frameNumber,
      timestamp: frame.timestamp,
      source_filename: originalName,
      r2_key: key,
      sha256: frame.sha256,
      bytes: frame.raw.byteLength,
    });
  }

  const archivedAt = new Date().toISOString();
  const manifestRaw = new TextEncoder().encode(JSON.stringify({
    archive_schema: { name: "DanaSafeRadarHistoryCycle", version: "8.2.0" },
    archived_at: archivedAt,
    radar_timestamp: radarTimestamp,
    frame_count: 10,
    source: "AEMET COMPO PB",
    original_manifest: manifest,
    raw_objects: frameKeys,
    raw_frames: frameRecords,
  }));

  await env.SNAPSHOTS.put(manifestKey, manifestRaw, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: radarTimestamp,
      frame_count: "10",
      archive_version: "8.2",
    },
  });

  await env.SNAPSHOTS.put(snapshotKey, rawSnapshot, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: radarTimestamp,
      generated_at: String(snapshot?.generated_at ?? ""),
      schema_version: String(snapshot?.schema?.version ?? ""),
      archive_version: "8.2",
      raw_frame_count: "10",
    },
  });

  const verification = await Promise.all([
    env.SNAPSHOTS.head(snapshotKey),
    env.SNAPSHOTS.head(manifestKey),
    ...frameKeys.map((key) => env.SNAPSHOTS.head(key)),
  ]);
  if (verification.some((item) => !item)) {
    throw new Error("R2 archive verification failed after write");
  }

  const markerPayload = new TextEncoder().encode(JSON.stringify({
    archive_schema: { name: "DanaSafeRadarHistoryIndex", version: "8.2.0" },
    archived_at: archivedAt,
    radar_timestamp: radarTimestamp,
    prefix,
    snapshot_key: snapshotKey,
    manifest_key: manifestKey,
    raw_frame_count: 10,
  }));
  await env.SNAPSHOTS.put(indexKey, markerPayload, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: radarTimestamp,
      archive_complete: "true",
      raw_frame_count: "10",
      snapshot_key: snapshotKey,
      manifest_key: manifestKey,
      archive_version: "8.2",
    },
  });

  const committed = await env.SNAPSHOTS.head(indexKey);
  if (!committed || committed.customMetadata?.archive_complete !== "true") {
    throw new Error("R2 history commit marker verification failed");
  }

  return { prefix, snapshotKey, manifestKey, indexKey, frameKeys };
}

async function historyStatus(env: Env, limit = 50, cursor?: string | null) {
  const boundedLimit = Math.min(Math.max(limit, 1), MAX_HISTORY_PAGE);
  const options: any = {
    prefix: `${HISTORY_INDEX_PREFIX}/`,
    limit: boundedLimit,
    include: ["customMetadata"],
  };
  if (cursor) options.cursor = cursor;

  const result = await env.SNAPSHOTS.list(options);
  const cycles = (result.objects ?? []).map((item: any) => ({
    key: item.key,
    uploaded: item.uploaded,
    size: item.size,
    radar_timestamp: item.customMetadata?.radar_timestamp ?? null,
    archive_complete: item.customMetadata?.archive_complete === "true",
    raw_frame_count: Number(item.customMetadata?.raw_frame_count ?? 0),
    snapshot_key: item.customMetadata?.snapshot_key ?? null,
    manifest_key: item.customMetadata?.manifest_key ?? null,
  }));

  return {
    archive_version: "8.2",
    order: "newest-first",
    cycles_returned: cycles.length,
    truncated: !!result.truncated,
    next_cursor: result.truncated ? (result.cursor ?? null) : null,
    cycles,
  };
}

async function historySummary(env: Env) {
  const result = await env.SNAPSHOTS.list({
    prefix: `${HISTORY_INDEX_PREFIX}/`,
    limit: 1,
    include: ["customMetadata"],
  });
  const latest = (result.objects ?? [])[0] ?? null;
  return {
    available: !!latest,
    latest_timestamp: latest?.customMetadata?.radar_timestamp ?? null,
  };
}

async function readArchiveObject(env: Env, key: string): Promise<Response> {
  const object = await env.SNAPSHOTS.get(key);
  if (!object) return json({ status: "missing", key }, 404);
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("cache-control", "no-store, no-cache, must-revalidate");
  headers.set("x-danasafe-source", "r2-history-archive");
  const metadata = object.customMetadata ?? {};
  if (metadata.sha256) headers.set("x-danasafe-sha256", String(metadata.sha256));
  if (metadata.radar_timestamp) headers.set("x-danasafe-radar-timestamp", String(metadata.radar_timestamp));
  if (metadata.source_filename) headers.set("x-danasafe-source-filename", String(metadata.source_filename));
  if (metadata.archive_complete) headers.set("x-danasafe-archive-complete", String(metadata.archive_complete));
  return new Response(object.body, { status: 200, headers });
}

function historyTimestampFrom(url: URL): string {
  const raw = url.searchParams.get("timestamp");
  if (!raw) throw new Error("timestamp query parameter is required");
  return raw;
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
          version: "8.2-history.2",
          architecture: "Worker + Container + R2 immutable history",
          archive_policy: "archive-before-live",
          endpoints: [
            "/health",
            "/radar/snapshot",
            "/radar/refresh",
            "/radar/history",
            "/radar/history/cycle?timestamp=...",
            "/radar/history/manifest?timestamp=...",
            "/radar/history/raw?timestamp=...&frame=1",
            "/aemet/timeline",
            "/aemet/latest-image-info",
          ],
        });
      }

      if (path === "/aemet/timeline" && request.method === "GET") {
        return json(await fetchAEMETTimeline());
      }

      if (path === "/aemet/latest-image-info" && request.method === "GET") {
        const latest = latestElement(await fetchAEMETTimeline());
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
        try {
          latest = latestElement(await fetchAEMETTimeline());
        } catch (error) {
          aemetError = error instanceof Error ? error.message : String(error);
        }
        const history = await historySummary(env);

        return json({
          service: "DanaSafe Radar Backend",
          status: "ok",
          version: "8.2-history.2",
          radar_timestamp: stored?.radar_timestamp ?? null,
          snapshot_generated_at: stored?.generated_at ?? null,
          hydrology_retrieved_at: stored?.hydrology?.retrieved_at ?? null,
          hydrology_refresh_coupled_to_radar: false,
          latest_aemet_timestamp: latest?.Fecha ?? null,
          in_sync: !!stored && !!latest && sameInstant(stored.radar_timestamp, latest.Fecha),
          history_enabled: true,
          history_latest_timestamp: history.latest_timestamp,
          history_cycles_visible: null,
          archive_policy: "archive-before-live",
          aemet_error: aemetError,
        });
      }

      if (path === "/radar/history" && request.method === "GET") {
        const requested = Number(url.searchParams.get("limit") ?? "100");
        const cursor = url.searchParams.get("cursor");
        return json(await historyStatus(
          env,
          Number.isFinite(requested) ? requested : 100,
          cursor,
        ));
      }

      if (path === "/radar/history/cycle" && request.method === "GET") {
        const prefix = archivePrefix(historyTimestampFrom(url));
        return readArchiveObject(env, `${prefix}/snapshot.json`);
      }

      if (path === "/radar/history/manifest" && request.method === "GET") {
        const prefix = archivePrefix(historyTimestampFrom(url));
        return readArchiveObject(env, `${prefix}/manifest.json`);
      }

      if (path === "/radar/history/raw" && request.method === "GET") {
        const prefix = archivePrefix(historyTimestampFrom(url));
        const frameNumber = Number(url.searchParams.get("frame") ?? "0");
        if (!Number.isInteger(frameNumber) || frameNumber < 1 || frameNumber > 10) {
          return json({ status: "error", error: "frame must be an integer from 1 to 10" }, 400);
        }

        const manifestObject = await env.SNAPSHOTS.get(`${prefix}/manifest.json`);
        if (!manifestObject) {
          return json({ status: "missing", message: "Archive manifest not found" }, 404);
        }
        const manifest = JSON.parse(await manifestObject.text());
        const key = manifest?.raw_frames?.[frameNumber - 1]?.r2_key
          ?? manifest?.raw_objects?.[frameNumber - 1];
        if (!key || typeof key !== "string") {
          return json({ status: "missing", message: `Raw frame ${frameNumber} not indexed` }, 404);
        }
        return readArchiveObject(env, key);
      }

      if (path === "/radar/snapshot" && request.method === "GET") {
        const object = await env.SNAPSHOTS.get(SNAPSHOT_KEY);
        if (!object) {
          return json(
            { status: "missing", message: "No published snapshot yet. POST /radar/refresh first." },
            404,
          );
        }
        const headers = new Headers();
        object.writeHttpMetadata(headers);
        headers.set("content-type", "application/json; charset=utf-8");
        headers.set("cache-control", "no-store, no-cache, must-revalidate");
        headers.set("x-danasafe-source", "r2-atomic-snapshot");
        return new Response(object.body, { status: 200, headers });
      }

      if (path === "/radar/refresh" && request.method === "POST") {
        // 1) Ask AEMET directly, bypassing cache.
        const latestTimestamp = latestElement(await fetchAEMETTimeline()).Fecha as string;

        // 2) Fast path only when BOTH LIVE and the durable 8.2 archive already exist.
        const stored = await readStoredSnapshot(env);
        if (
          stored
          && sameInstant(stored.radar_timestamp, latestTimestamp)
          && await archiveIsComplete(env, latestTimestamp)
        ) {
          return json(stored, 200, {
            "x-danasafe-refresh": "unchanged",
            "x-aemet-latest": latestTimestamp,
            "x-danasafe-history": "already-archived",
          });
        }

        // 3) Build/stage a target-specific cycle in the Container.
        let result = await runEngineRefresh(env, latestTimestamp);

        // 4) Reconcile once if AEMET advances during processing.
        const latestAfterTimestamp = latestElement(await fetchAEMETTimeline()).Fecha as string;
        if (!sameInstant(result.snapshot.radar_timestamp, latestAfterTimestamp)) {
          const producedMs = Date.parse(result.snapshot.radar_timestamp);
          const latestAfterMs = Date.parse(latestAfterTimestamp);
          if (
            Number.isFinite(producedMs)
            && Number.isFinite(latestAfterMs)
            && producedMs < latestAfterMs
          ) {
            result = await runEngineRefresh(env, latestAfterTimestamp);
          }
        }

        if (!sameInstant(result.snapshot.radar_timestamp, latestAfterTimestamp)) {
          throw new Error(
            `Pipeline/AEMET mismatch after reconciliation: pipeline=${result.snapshot.radar_timestamp} AEMET=${latestAfterTimestamp}`,
          );
        }

        // 5) Durable history commits before LIVE can advance.
        const archived = await archiveCycle(env, result.raw, result.snapshot);

        // 6) Monotonic LIVE publish. If another request already published a newer
        // cycle while we archived, keep the newer LIVE and return it to the client.
        const publishState = await persistLiveSnapshot(env, result.raw, result.snapshot);
        let responseRaw = result.raw;
        let responseTimestamp = result.snapshot.radar_timestamp;
        if (publishState === "skipped-newer-live") {
          const current = await readStoredSnapshotRecord(env);
          if (!current) throw new Error("LIVE snapshot disappeared after monotonic publish guard");
          responseRaw = current.raw;
          responseTimestamp = current.snapshot?.radar_timestamp ?? responseTimestamp;
        }

        return new Response(responseRaw, {
          status: 200,
          headers: {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store, no-cache, must-revalidate",
            "x-danasafe-refresh": publishState === "updated" ? "updated" : "newer-live-preserved",
            "x-aemet-latest": latestAfterTimestamp,
            "x-danasafe-live-timestamp": String(responseTimestamp),
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
