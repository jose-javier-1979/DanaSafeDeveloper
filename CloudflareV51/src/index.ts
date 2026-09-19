import { Container } from "@cloudflare/containers";

const AEMET_BASE = "https://www.aemet.es";
const AEMET_TIMELINE = `${AEMET_BASE}/es/api-eltiempo/radar/timeline/compo/PB`;
const SNAPSHOT_KEY = "published/danasafe_live_snapshot.json";

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
      "user-agent": "DanaSafe-Cloudflare/5.1",
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

async function persistSnapshot(env: Env, raw: ArrayBuffer, snapshot: any) {
  await env.SNAPSHOTS.put(SNAPSHOT_KEY, raw, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: {
      radar_timestamp: String(snapshot?.radar_timestamp ?? ""),
      generated_at: String(snapshot?.generated_at ?? ""),
      schema_version: String(snapshot?.schema?.version ?? "5.1.0"),
    },
  });
}

function sameInstant(a?: string, b?: string) {
  if (!a || !b) return false;
  const aa = Date.parse(a);
  const bb = Date.parse(b);
  return Number.isFinite(aa) && Number.isFinite(bb) && aa === bb;
}

async function runEngineRefresh(env: Env, targetTimestamp?: string): Promise<{ raw: ArrayBuffer; snapshot: any }> {
  const engine = env.DANASAFE_ENGINE.getByName("danasafe-radar-engine");
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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (path === "/") {
        return json({
          service: "DanaSafe Radar Backend",
          status: "online",
          version: "5.1-baseline.1",
          architecture: "Worker + Container + R2",
          endpoints: ["/health", "/radar/snapshot", "/radar/refresh", "/aemet/timeline", "/aemet/latest-image-info"],
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
        return json({
          service: "DanaSafe Radar Backend",
          status: "ok",
          version: "5.1-baseline.1",
          radar_timestamp: stored?.radar_timestamp ?? null,
          snapshot_generated_at: stored?.generated_at ?? null,
          hydrology_retrieved_at: stored?.hydrology?.retrieved_at ?? null,
          hydrology_refresh_coupled_to_radar: false,
          latest_aemet_timestamp: latest?.Fecha ?? null,
          in_sync: !!stored && !!latest && sameInstant(stored.radar_timestamp, latest.Fecha),
          aemet_error: aemetError,
        });
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

        // 2) If the atomic snapshot is already at the latest AEMET frame, return it immediately.
        const stored = await readStoredSnapshot(env);
        if (stored && sameInstant(stored.radar_timestamp, latestTimestamp)) {
          return json(stored, 200, {
            "x-danasafe-refresh": "unchanged",
            "x-aemet-latest": latestTimestamp,
          });
        }

        // 3) Otherwise wake the Linux container. The target timestamp is passed down so
        // concurrent requests that waited on the container lock can reuse a snapshot
        // produced by the request ahead of them instead of rerunning the pipeline.
        let result = await runEngineRefresh(env, latestTimestamp);

        // 4) Re-check AEMET after processing. A new frame may legitimately appear while
        // the pipeline is running. Accept the produced snapshot if it matches the latest
        // frame now visible. If the snapshot is older, retry once against that new target.
        let latestAfter = latestElement(await fetchAEMETTimeline());
        let latestAfterTimestamp = latestAfter.Fecha as string;

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

        // 5) Persist only the already validated atomic snapshot.
        await persistSnapshot(env, result.raw, result.snapshot);

        // 6) Return the same bytes that were persisted, so the iPhone paints exactly what was published.
        return new Response(result.raw, {
          status: 200,
          headers: {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store, no-cache, must-revalidate",
            "x-danasafe-refresh": "updated",
            "x-aemet-latest": latestAfterTimestamp,
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
