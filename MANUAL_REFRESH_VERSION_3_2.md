# DanaSafe V3.2 — Manual refresh contract

The refresh button is the only radar trigger.

When pressed, DanaSafe must:
1. query the AEMET COMPO timeline at that moment;
2. select the latest 10 consecutive frames AEMET has actually published;
3. download all 10;
4. execute the complete DanaSafe radar algorithm;
5. validate systems, tracks and contours against that exact cycle;
6. atomically publish the resulting snapshot;
7. return success to the app;
8. make the app fetch that snapshot and display its newest AEMET timestamp.

If any step fails, the previous snapshot remains unchanged and the app reports the error.
