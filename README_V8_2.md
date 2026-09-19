# DanaSafe 8.2 — integración de archivo radar histórico

DanaSafe 8.2 evoluciona el proyecto actual sin sustituir el repositorio ni el núcleo científico.

## Estructura de backend

- `CloudflareV51/`: referencia congelada del backend previamente validado. No se modifica.
- `CloudflareV82/`: candidato 8.2 con archivo histórico R2.

El candidato usa un Worker y bucket aislados para poder realizar una validación real sin alterar el endpoint que hoy usa el iPhone.

## Contrato histórico 8.2

Cada ciclo completado se almacena antes de permitir que LIVE avance:

- `snapshot.json`
- `manifest.json`
- 10 frames AEMET brutos
- marcador final bajo `history/index/`

El marcador del índice se escribe **después** de verificar snapshot, manifest y los diez frames. Es la señal autoritativa de `archive_complete`.

El índice utiliza claves de tiempo inverso para que R2 devuelva primero los ciclos más recientes. `/radar/history` admite cursor y no realiza un HEAD por cada ciclo. `/health` sólo consulta el marcador más reciente.

## Concurrencia

El Container congela un bundle identificado por timestamp mientras mantiene el lock del pipeline. Las posteriores lecturas de archivo usan ese bundle y no el `sequence_manifest.json` mutable, evitando mezclar dos ciclos cuando coinciden refreshes alrededor del cambio de slot AEMET.

## Endpoint iOS

La app 8.2 conserva por seguridad el endpoint de producción actual:

`https://danasafe-radar.firefritz.workers.dev`

Hasta que `CloudflareV82` sea promovido, Tools puede mostrar **R2 histórico: OFF · backend actual sin archivo 8.2**. Esto es deliberado: no se declara el histórico operativo antes de una validación real del candidato.

## Orden de validación

1. `python3 Tests/verify_v82.py`
2. `python3 Tests/verify_v82_independent.py`
3. TypeScript del Worker 8.2.
4. Regresión canónica Python.
5. Release build iOS.
6. Unit tests y UI test focalizado.
7. Despliegue aislado del candidato `CloudflareV82`.
8. Refresh real.
9. Confirmar el timestamp en `/radar/history`.
10. Recuperar manifest + 10 RAW y verificar SHA-256.
11. Sólo después, promover la configuración de producción.

## Google Drive / exportación local

R2 es el archivo operativo. Para una copia secundaria en una carpeta local o sincronizada con Google Drive:

```sh
python3 Tools/export_r2_history.py --base-url <backend-8.2> --output "/path/to/Google Drive/DanaSafe Radar History"
```

El exportador recalcula SHA-256 y tamaño de los diez frames y genera `verification.json`. Una discrepancia aborta la exportación del ciclo.
