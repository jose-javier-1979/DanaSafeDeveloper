# DanaSafe 5.1 architecture audit

## Failure points found in 5.0

1. iOS `GET /radar/snapshot` refreshed HTTP, not necessarily AEMET or the algorithm.
2. `/aemet/latest-image-info` was diagnostic only.
3. There was no proven remote trigger for the Python/Pillow pipeline.
4. The existing Worker source/deployment was not included in the Xcode package.
5. A Worker isolate alone is not the correct place for the existing filesystem/Pillow pipeline.
6. A durable published snapshot was not under the V5.0 project's control.

## V5.1 closures

- `POST /radar/refresh` is now the explicit remote trigger.
- Worker fetch to AEMET uses `cache: no-store`.
- Cloudflare Container runs the unchanged Python/Pillow pipeline.
- R2 persists the last accepted atomic snapshot across container sleep/restarts.
- Worker compares the triggering AEMET timestamp with the pipeline result before R2 publication.
- iOS compares AEMET and returned snapshot again before publication to MapKit.
- GET startup path and POST refresh path are separate.
- V3.2 local developer server remains preserved.
- Bundle JSON remains offline fallback.
- Existing radar systems, tracks, contours, hydrology, search, location and tools remain present.

## DNS conclusion

`workers.dev` is sufficient for functional testing and requires no CNAME. A production Custom Domain is recommended later; Cloudflare creates the DNS/TLS record when the Custom Domain is attached.
