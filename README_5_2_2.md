# DanaSafe 5.2.2

Client-side compatibility release for the deployed asynchronous Cloudflare 5.2.1 backend.

Open `DanaSafeDeveloper.xcodeproj` in Xcode and install on the iPhone as usual.

Expected refresh sequence in Tools:

`Requesting refresh…` → `Queued` / `Waiting · processing` → `Ready · downloading snapshot` → `Completed · SYNC` or `Completed · AEMET +N min`.

This release intentionally does not deploy or replace the production Worker/Container. It is designed to prove the corrected iOS↔Cloudflare contract first.

See `VERSION_5_2_2.md` and `AUDIT_VERSION_5_2_2.md` for details.
