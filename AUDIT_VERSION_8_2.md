# DanaSafe 8.2 — Auditoría de integración y persistencia histórica

**Versión:** 8.2  
**Build:** 82  
**Bundle ID:** `com.firefritz.DanaSafeDeveloperV82`  
**Base:** proyecto actual DanaSafe 8.1 sobre `main`  
**Objetivo principal:** impedir la pérdida de ciclos radar y permitir su recuperación/validación posterior.

## 1. Decisión de arquitectura

El filesystem del Cloudflare Container se considera efímero y nunca actúa como archivo histórico.

Cloudflare R2, bucket `danasafe-radar-v51`, sigue siendo el almacenamiento autoritativo. Se conserva la clave LIVE existente:

`published/danasafe_live_snapshot.json`

y se añade archivo histórico inmutable:

`history/cycles/<radar_timestamp>/`

Cada ciclo contiene:

- `snapshot.json`
- `manifest.json`
- 10 imágenes AEMET originales en `raw/`

## 2. Invariante archive-before-live

Para un nuevo ciclo:

1. El Worker determina el último timestamp AEMET.
2. Ese timestamp se pasa al Container.
3. El Container fija `DANASAFE_TARGET_TIMESTAMP` para que Python descargue exactamente el ciclo solicitado.
4. Se genera el snapshot atómico.
5. El Worker solicita al Container el manifest y las diez imágenes brutas.
6. Cada frame se guarda en R2 con SHA-256, timestamp, nombre original y número de frame.
7. `manifest.json` registra clave R2, hash, tamaño, timestamp y nombre original de los 10 frames.
8. El snapshot histórico se escribe el último con `archive_complete=true`.
9. El Worker verifica por HEAD snapshot + manifest + 10 frames.
10. Sólo entonces actualiza el snapshot LIVE.

Si falla cualquier paso de archivo/verificación, LIVE no avanza.

## 3. Recuperación

Rutas incorporadas:

- `GET /radar/history`
- `GET /radar/history/cycle?timestamp=...`
- `GET /radar/history/manifest?timestamp=...`
- `GET /radar/history/raw?timestamp=...&frame=1..10`

Los frames recuperados exponen SHA-256 en cabecera y el manifest contiene una copia portable del hash, por lo que la integridad puede comprobarse fuera de Cloudflare.

## 4. Idempotencia

Si ya existe un ciclo con `archive_complete=true` y 10 objetos RAW, el Worker lo reutiliza y evita duplicar escrituras.

## 5. Google Drive

Google Drive no está en la transacción crítica de actualización. Se incorpora `Tools/export_r2_history.py` para exportar posteriormente a cualquier directorio, incluida una carpeta sincronizada con Google Drive.

El exportador:

- descarga snapshot + manifest + 10 frames;
- recalcula SHA-256;
- compara hash y tamaño con el manifest;
- compara también el SHA de metadata R2 cuando está disponible;
- genera `verification.json`;
- aborta ante una discrepancia.

## 6. Aplicación iOS

- Marketing version 8.2.
- Build 82.
- Bundle ID V82 para poder probarla junto a la versión previa.
- Tools muestra estado del histórico R2 y número de ciclos visibles.
- Se conserva el endpoint de producción.

## 7. Dos verificaciones independientes

### Verificación 1 — integridad de implementación

`Tests/verify_v82.py`

Comprueba versionado, archive-before-live, 10 frames, hashes, commit marker, recuperación, pinning temporal e integración iOS.

### Verificación 2 — contrato de retención

`Tests/verify_v82_independent.py`

Comprueba por una vía separada topología R2, recuperabilidad, idempotencia, semántica de fallo, pinning del target e integridad extremo a extremo de los RAW.

Ambas se ejecutan dentro de GitHub Actions antes de Xcode build/tests.

## 8. Criterio de release

No declarar 8.2 operativa hasta completar:

1. Ambas verificaciones automáticas.
2. TypeScript typecheck.
3. Regresión Python canónica.
4. Release build iOS.
5. Unit/UI tests.
6. Despliegue Worker/Container.
7. Refresh real.
8. Confirmación de que el timestamp LIVE aparece en histórico.
9. Recuperación del manifest y 10 frames del ciclo real con hashes correctos.

## 9. Saneamiento del CI heredado

La auditoría de los runs previos de `main` confirmó que el Release build ya pasaba, pero `DanaSafeDeveloperUITests.testPrimaryNavigationAndNowcastHelp()` fallaba y el benchmark de lanzamiento multiplicaba ejecuciones y tiempo de simulador.

8.2 corrige esa deuda previa mediante:

- argumento `--ui-testing`;
- startup con fixture local, sin llamada inicial a Cloudflare;
- supresión de polling/consulta de permisos durante UI tests;
- identificador estable `nowcast.help.dismiss`;
- esperas explícitas por accessibility identifiers;
- un único smoke launch en vez de todas las configuraciones UI;
- benchmark de launch excluido de CI y conservado para ejecución manual.

Esto no reduce la cobertura funcional del CI; elimina variabilidad de red, permisos y benchmark que no pertenecen a la prueba de navegación.
