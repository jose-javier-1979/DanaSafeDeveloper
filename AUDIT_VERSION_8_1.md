# DanaSafe 8.1 — Auditoría integral de candidatura final

**Versión:** 8.1  
**Build:** 81  
**Bundle ID:** `com.firefritz.DanaSafeDeveloperV81`  
**Deployment target:** iOS 17.0  
**Device family:** iPhone  
**Team:** `R6RR6KZ9T4`

## 1. Alcance

Auditoría profunda del árbol completo entregado como DanaSafe 8.0 y saneado como 8.1: proyecto Xcode, metadata, privacidad, assets, Swift, fixtures JSON, Engine Python, Cloudflare Worker/Container, tests, UI tests, App Intents, navegación, permisos, notificaciones, QPE/Nowcast y contratos de red.

No se ha modificado el Worker de producción ni el Engine científico congelado. Los cambios 8.1 están concentrados en la capa iOS, metadata, assets y tests.

## 2. Estructura iOS auditada

El target principal contiene los 15 Swift funcionales:

- `DanaSafeDeveloperApp.swift`
- `ContentView.swift`
- `DanaSafeAPIClient.swift`
- `DanaSafeModel.swift`
- `Models.swift`
- `LocationService.swift`
- `SearchService.swift`
- `RadarStyle.swift`
- `NowcastModels.swift`
- `NowcastEvaluator.swift`
- `NowcastView.swift`
- `NotificationManager.swift`
- `DanaSafeIntents.swift`
- `QuantitativePrecipitationCore.swift`
- `PrecipitationForecast.swift`

Todos están referenciados por `project.pbxproj` y pertenecen a `PBXSourcesBuildPhase`.

## 3. Metadata / Privacy / Assets

### PASS

- `Info.plist` sincronizado con `$(MARKETING_VERSION)` y `$(CURRENT_PROJECT_VERSION)`.
- Display name: `DanaSafe`.
- Descripción de ubicación expresa finalidad local y que el GPS no se envía al Worker.
- `PrivacyInfo.xcprivacy` incorporado al target.
- Tracking: `false`.
- No se declaran datos recogidos por la app, coherente con el código auditado actual.
- No se detectan APIs de required-reason en el código Swift auditado.
- `Assets.xcassets` incorporado al target.
- `AccentColor` incorporado.
- `AppIcon` válido 1024x1024 incorporado.

### Nota de diseño

El icono incluido en 8.1 es un **asset técnico nuevo** creado para dejar el proyecto compilable y archivable; no se recuperó una imagen histórica de AppIcon de las copias disponibles. Debe considerarse arte provisional si existe branding definitivo pendiente.

## 4. Red / Cloudflare

### PASS

La app iOS sólo contiene el endpoint HTTPS:

`https://danasafe-radar.firefritz.workers.dev`

No se detectan `localhost`, `127.0.0.1`, NSLocalNetwork ni HTTP local en la capa iOS.

Rutas utilizadas por iOS:

- `GET /health`
- `GET /aemet/latest-image-info`
- `GET /radar/snapshot`
- `POST /radar/refresh`
- compatibilidad `GET /radar/refresh-status` si alguna respuesta futura devuelve HTTP 202

El source tree `CloudflareV51` auditado devuelve actualmente el refresh de forma síncrona HTTP 200 y no expone `/radar/refresh-status`; por tanto el camino 202 del cliente queda como compatibilidad futura/dormida con este Worker concreto. Esto no rompe el flujo actual 200.

El manifiesto `WORKER_PRODUCTION_FROZEN_SHA256.txt` coincide al 100% con el Worker incluido. El Worker no se ha alterado en 8.1.

## 5. Nowcast

### PASS

- Fixture canónico: 10 frames.
- Builder canónico ejecutado sobre copia temporal del Engine.
- Resultado: **9 tracks**.
- Timestamp final coincide con el último frame radar.
- Fallback `NowcastBuilderV7.build(from:)` continúa en modelo e Intents cuando el snapshot no trae nowcast.
- Horizonte conservado: 15/30/45/60/90/120 min.
- Se eliminó force unwrap evitable en asociación de tracks.

## 6. QPE / precipitación

### PASS matemático

El ejecutable independiente del core produce:

- área Dénia: **6.464672 km²**
- 48 dBZ: **36.463324 mm/h**
- 72 dBZ, cap a 60 dBZ: **205.048338 mm/h**

Estos fingerprints coinciden con la auditoría matemática previa.

`PrecipitationForecast.swift` permanece integrado en Sources y se ha conectado a la vista Ahora y a la Ayuda:

- 10 min
- 30 min
- 60 min
- mm acumulados
- millones de litros/celda
- pico dBZ
- pico mm/h
- área de celda

Se añadió además App Intent cuantitativo de lluvia 10/30/60.

### Hallazgo científico conocido, no ocultado

Para T004 en su centroide, la reconstrucción actual había producido **0.850573 mm / 5.754552 M L**, mientras una auditoría histórica registró aproximadamente **0.97 mm / 6.58 M L**. El área de celda sí coincide (~6.765 km²). Esta diferencia debe investigarse antes de usar ese fingerprint histórico como golden test exacto; no se ha modificado el algoritmo para forzar la coincidencia.

## 7. Localización

### PASS estático

- `requestLocation()` ya no llama `requestLocation()` antes de resolver autorización.
- La vista Radar reacciona al cambio real de `locationService.location`, evitando depender de una posición todavía nil inmediatamente después de pedir permiso.
- Siri/App Intents usa un proveedor one-shot con tratamiento de autorización.
- Ubicación utilizada para ETA/QPE permanece local en la app.

## 8. Notificaciones

### PASS estático

- Permiso explícito.
- Sólo notifica amenaza `approaching` o superior.
- ETA <= 120 min.
- Confianza >= 0.50.
- Identificador estable por timestamp radar + track para de-duplicación.
- Refresh manual, polling y cambio de ubicación reevalúan y vuelven a considerar notificación.

Limitación funcional documentada: son notificaciones locales; no equivalen a push remoto si la app está cerrada.

## 9. Navegación y botones

Inventario validado en código y cubierto por UI tests:

### Tabs

- Radar
- Ahora
- Systems
- Hydrology
- Tools

### Ahora

- Evaluar mi ubicación
- Actualizar radar y nowcast
- Activar notificaciones DanaSafe
- Ayuda
- Sheet Ayuda + OK
- QPE 10/30/60 cuando existe evaluación/localización válida

### Tools

- Comprobar Cloudflare + AEMET
- Actualizar radar desde Cloudflare

Se han incorporado `accessibilityIdentifier` estables para automatizar estos flujos.

## 10. Avisos de uso / privacidad

Se añadió una sección explícita de uso responsable:

- DanaSafe es orientativa y no sustituye avisos oficiales.
- La ausencia de alerta no garantiza ausencia de riesgo.
- Ante emergencia deben seguirse AEMET, Protección Civil, 112 y servicios oficiales.
- GPS se procesa localmente.
- SAIH posee marca temporal independiente del radar.

## 11. Tests

### Unit tests incorporados

- fingerprint de área de celda
- 48 dBZ -> mm/h
- cap QPE 72/60 dBZ
- fixture radar canónico
- 9 tracks nowcast
- T004 / F10_SYS_013 / Zmax 42
- área T004
- horizontes 10/30/60

### UI tests incorporados

- existencia de 5 tabs
- navegación a Ahora
- botones principales de Ahora
- apertura/cierre de Ayuda
- navegación a Tools
- botones de health y refresh
- launch test + screenshot

## 12. Engine / Python

- `python -m compileall`: PASS para Engine, Container, Tools y Tests.
- Builder canónico de nowcast: PASS, 9 tracks.
- La regresión offline completa se lanzó sobre una copia temporal; alcanzó correctamente extracción de 714 objetos, reconstrucción de 10 frames y tracking (123 tracks >=2 frames / 67 >=4 frames) antes de superar el tiempo disponible del entorno de auditoría. No se marca la regresión offline completa como PASS hasta ejecutarla sin límite temporal en el Mac.

## 13. Cloudflare / TypeScript

- `src/index.ts`: TypeScript typecheck PASS.
- Python container: compile PASS.
- Worker producción: hashes congelados PASS.
- No se ha tocado el backend en la migración 8.1.

## 14. Swift / proyecto

### PASS estático

- Todos los Swift: `swiftc -frontend -parse` PASS.
- No quedan los force unwrap auditados `best!` / `peakDbz!`.
- No quedan textos visibles V7 auditados.
- Todos los recursos previstos están en `Resources`.
- Unit/UI test targets armonizados a iOS 17 e iPhone.
- Scheme compartido incluye app, Unit Tests y UI Tests.
- No hay dependencias Swift Package Manager reales. Esto es deliberado: el proyecto usa frameworks Apple nativos y evita superficie de dependencia innecesaria.

## 15. Auditorías ejecutadas

### Pass 1

`Tests/verify_v81.py`: **PASS**

Comprueba metadata, privacy, assets, endpoints, validaciones, QPE wiring, tests, nowcast canónico y hashes del Worker.

### Pass 2 independiente

**PASS**

Comprueba de forma separada:

- membership de todos los Swift
- membership de recursos
- UUIDs de proyecto
- scheme y targets
- tabs y acciones principales
- metadata/plist
- ausencia de dependencias SPM reales
- AppIcon 1024x1024

## 16. Pendiente exclusivamente en macOS/Xcode

Este entorno de auditoría no contiene Xcode/iOS Simulator, por lo que la candidatura 8.1 debe ejecutar en el Mac antes de considerarse release binaria:

1. Release build `generic/platform=iOS`.
2. Unit tests.
3. UI tests en **DanaSafe-Test-iPhone17Pro / iOS 26.5**.
4. Clean Release build.
5. Archive con firma Apple Distribution.
6. Organizer validation.
7. Smoke test físico en iPhone.

## 17. Estado

**DanaSafe 8.1 = CANDIDATA COMPLETA DE CÓDIGO PARA COMPILAR.**

No se declara todavía como binario final publicado hasta superar la fase macOS/Xcode del punto 16 y decidir si se mantiene o reemplaza el icono técnico incluido.
