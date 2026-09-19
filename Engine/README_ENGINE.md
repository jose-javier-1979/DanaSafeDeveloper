# DanaSafe Radar Engine — V3.2

Manual refresh pipeline:

1. `download_compo_sequence.py` — queries AEMET COMPO and downloads the 10 newest consecutive frames currently available.
2. `process_compo_sequence.py` — RGB -> dBZ / reflectivity processing.
3. `build_radar_systems_v03.py` — hierarchical radar systems.
4. `track_radar_sequence.py` — temporal object tracking.
5. `preview_reliable_tracks.py` — reliable-track filtering.
6. `sync_latest_frame.py` — synchronizes the clean latest frame.
7. `national_marching_squares.py` — georeferenced isocontours.
8. `publish_live_snapshot.py` — validates temporal coherence and atomically publishes the complete snapshot.

The app's Refresh button invokes this exact pipeline through `/refresh`. No automatic or clock-trigger refresh is used in V3.2.

Recovered algorithm criteria:
- dBZ levels: 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72.
- root threshold: Z >= 12 dBZ.
- minimum root area: 8 px.
- root association dilation: 2 px.
- higher-level overlap association >= 0.50.
- significant: root area >= 20 px OR Zmax >= 36 dBZ.
