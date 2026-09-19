# DanaSafe 7.0

DanaSafe 7.0 promotes the validated DanaSafe 6.4 production path and activates Nowcast without replacing or redeploying its Worker.

- Production endpoint: `danasafe-radar.firefritz.workers.dev`
- Worker code: frozen from 6.4
- Refresh: existing 200/202 async-compatible contract
- Nowcast: server block when present, otherwise on-device from the same 10 live frames
- GPS ETA/threat: on-device
- Siri/App Intents: use the same local fallback builder
- Notifications: local, based on evaluated live trajectory
- Help: active in Ahora
