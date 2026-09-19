# DanaSafe 8.2 — Auditoría de integración y persistencia histórica

**Versión:** 8.2  
**Build:** 82  
**Bundle ID:** `com.firefritz.DanaSafeDeveloperV82`  
**Base:** DanaSafe 8.1 sobre `main`  
**Objetivo:** impedir la pérdida de ciclos radar, hacerlos recuperables y mantener intacto el backend previamente validado.

## 1. Separación de responsabilidades

`CloudflareV51/` permanece byte por byte conforme a `WORKER_PRODUCTION_FROZEN_SHA256.txt`.

`CloudflareV82/` contiene el nuevo backend histórico. Su configuración por defecto es deliberadamente aislada:

- Worker candidato: `danasafe-radar-v82-candidate`
- R2 candidato: `danasafe-radar-v82-candidate`

La configuración `wrangler.production.example.jsonc` documenta la promoción futura al Worker y bucket de producción, pero no se usa antes de la validación real.

## 2. Persistencia

El filesystem del Container es scratch. No constituye almacenamiento histórico.

R2 conserva, por ciclo:

- `history/cycles/<timestamp>/snapshot.json`
- `history/cycles/<timestamp>/manifest.json`
- diez RAW AEMET;
- marcador final `history/index/<reverse-time>_<timestamp>.json`.

El marcador del índice es la señal autoritativa de ciclo completo.

## 3. Invariante archive-before-live

1. Worker fija el target AEMET.
2. Container recibe el target en `DANASAFE_TARGET_TIMESTAMP`.
3. Pipeline genera exactamente ese ciclo.
4. Mientras mantiene el lock, el Container crea un staging inmutable por timestamp.
5. Worker recupera del staging manifest + 10 RAW.
6. Cada RAW se guarda con SHA-256, timestamp, nombre, número y tamaño.
7. Se escriben manifest y snapshot históricos.
8. Worker verifica en R2 los 12 objetos.
9. Se escribe y verifica el marcador del índice.
10. Sólo después se intenta avanzar LIVE.

Un guard adicional impide sustituir LIVE por un timestamp anterior si otro refresh concurrente ya publicó uno más nuevo.

## 4. Concurrencia

Las lecturas de archivo no vuelven a consultar el manifest mutable del pipeline. Usan `ArchiveStaging/<timestamp>/`, creado dentro del lock. Esto elimina la carrera entre dos refreshes alrededor de un cambio de slot.

## 5. Histórico y escalabilidad

El índice usa tiempo invertido, de modo que el orden lexicográfico de R2 es newest-first.

`GET /radar/history`:
- admite `limit`;
- admite `cursor`;
- devuelve `next_cursor`;
- obtiene metadata directamente del listing.

`/health` consulta sólo un marcador del índice; su coste no crece linealmente con el histórico.

## 6. Bootstrap desde 8.1

El fast path de “LIVE ya coincide con AEMET” sólo se usa si existe además el marcador histórico 8.2. Tras una actualización, un LIVE actual pero todavía no archivado obliga a generar/stagear y archivar ese mismo target.

## 7. Recuperación e integridad

Rutas:
- `GET /radar/history`
- `GET /radar/history/cycle?timestamp=...`
- `GET /radar/history/manifest?timestamp=...`
- `GET /radar/history/raw?timestamp=...&frame=1..10`

El manifest publica hash y tamaño de cada RAW. La respuesta RAW expone también el SHA-256 de metadata R2.

## 8. Google Drive

Google Drive queda fuera de la transacción crítica. `Tools/export_r2_history.py` exporta a cualquier carpeta y vuelve a verificar hash/tamaño antes de escribir una copia secundaria.

## 9. Aplicación iOS

- Marketing 8.2, build 82, bundle V82.
- Mantiene el endpoint de producción actual.
- Decodifica opcionalmente `history_enabled`, `history_latest_timestamp` y `archive_policy`.
- Mientras producción no haya sido promovida a V82, muestra explícitamente que el backend actual no dispone del archivo 8.2.

## 10. Dos verificaciones independientes

### Verificación 1
`Tests/verify_v82.py`

Comprueba iOS/versionado, inmovilidad V51, aislamiento V82, archive-before-live, índice, staging y hashes.

### Verificación 2
`Tests/verify_v82_independent.py`

Comprueba por otra vía topología de almacenamiento, idempotencia, paginación newest-first, coste O(1) de health, concurrencia, bootstrap y cadena de integridad.

## 11. Criterio de promoción

No considerar el histórico operativo en producción hasta que:
1. ambas verificaciones sean PASS;
2. TypeScript y regresión canónica sean PASS;
3. Release build Xcode y unit tests sean PASS;
4. la app Release se instale y arranque correctamente en un simulador real de CI;
5. el candidato se despliegue de forma aislada;
6. un refresh real produzca un ciclo recuperable;
7. los 10 SHA-256 recuperados coincidan;
8. sólo entonces se promueva el backend de producción.

### Nota sobre XCUI en macOS 26

La prueba XCUI `testPrimaryNavigationAndNowcastHelp` se conserva en el repositorio para ejecución manual, pero deja de ser un gate de CI. En los runners macOS 26 / Xcode 26.6, el proceso `DanaSafeDeveloperUITests.xctrunner` murió con `NSMachErrorDomain Code=-308 (ipc/mig server died)` antes de completar la prueba, mientras Release build y unit tests pasaban. El gate automático usa por ello una comprobación determinista: instala la app Release en el simulador, resuelve su contenedor mediante el bundle ID V82 y la lanza con `simctl launch`.
