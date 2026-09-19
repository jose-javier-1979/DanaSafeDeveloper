# DanaSafe 5.1.1 Cloud-only diagnostic patch

Purpose: isolate the iOS runtime from the preserved local developer HTTP service before DanaSafe 6 work continues.

Changes:
- Removed local server URL/AppStorage from ContentView.
- Removed all local HTTP fetch/refresh functions from DanaSafeModel.
- publish(snapshot:) no longer mutates any local-server state.
- Removed NSLocalNetworkUsageDescription and NSAllowsLocalNetworking from Info.plist.
- DanaSafeAPIClient is the only runtime network client and points only to the production Cloudflare HTTPS endpoint.
- Tools shows Runtime = Cloudflare HTTPS only and Local service = DISABLED.
- Bundled JSON remains as read-only offline fallback.
- Radar algorithm and golden radar products are unchanged.

Expected diagnostic outcome:
If AEMET is newer than the Cloudflare snapshot and refresh still fails in this build, the fault is definitively in the Cloudflare refresh/backend path rather than the iOS local developer service.
