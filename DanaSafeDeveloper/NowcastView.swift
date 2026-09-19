import SwiftUI
import CoreLocation

struct NowcastView: View {
    @ObservedObject var model: DanaSafeModel
    @ObservedObject var locationService: LocationService
    @ObservedObject var notificationManager: DanaSafeNotificationManager

    @State private var showHelp = false

    var body: some View {
        NavigationStack {
            List {
                Section("DanaSafe 8.2 · nowcast vivo") {
                    LabeledContent("Radar", value: model.nowcast?.radarTimestamp ?? "Sin nowcast disponible")
                    LabeledContent("Fuente", value: model.nowcastSource)
                    LabeledContent("Tracks", value: "\(model.nowcast?.trackCount ?? 0)")
                    LabeledContent("Horizonte", value: "\(model.nowcast?.horizonMinutes ?? 0) min")
                    if let age = model.radarAgeMinutes {
                        LabeledContent("Edad radar", value: "\(age) min")
                    }

                    Button("Evaluar mi ubicación") {
                        locationService.requestLocation()
                    }
                    .accessibilityIdentifier("nowcast.evaluateLocation")

                    Button {
                        Task {
                            await model.refreshFromCloudflare()
                            if let coordinate = locationService.location?.coordinate {
                                evaluateAndNotify(at: coordinate)
                            }
                        }
                    } label: {
                        if model.isRefreshing {
                            HStack {
                                ProgressView().controlSize(.small)
                                Text(model.refreshProgress)
                            }
                        } else {
                            Label("Actualizar radar y nowcast", systemImage: "arrow.clockwise")
                        }
                    }
                    .disabled(model.isRefreshing)
                    .accessibilityIdentifier("nowcast.refresh")
                }

                if let forecast = precipitationForecast {
                    Section("Lluvia prevista") {
                        ForEach(forecast.accumulations) { item in
                            LabeledContent("\(item.minutes) min", value: String(format: "%.2f mm · %.2f M L/celda", item.centralMm, item.centralLitresPerCell / 1_000_000.0))
                        }
                        if let peak = forecast.peakDbz {
                            LabeledContent("Pico radar", value: "\(peak) dBZ")
                        }
                        LabeledContent("Pico estimado", value: String(format: "%.1f mm/h", forecast.peakRainRateMmPerHour))
                        LabeledContent("Área celda", value: String(format: "%.3f km²", forecast.cellAreaKm2))
                        Text("Estimación QPE orientativa. La conversión radar-lluvia tiene incertidumbre y no sustituye pluviómetros ni avisos oficiales.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if let best = model.bestThreat {
                    Section("Evaluación") {
                        LabeledContent("Estado", value: best.level.title)
                        LabeledContent("Distancia", value: String(format: "%.1f km", best.distanceKm))
                        LabeledContent("Paso mínimo", value: String(format: "%.1f km", best.closestApproachKm))
                        if let eta = best.etaMinutes {
                            LabeledContent("ETA", value: "~\(Int(eta.rounded())) min")
                        } else {
                            LabeledContent("ETA", value: "Sin intersección ≤ 120 min")
                        }
                        LabeledContent("Velocidad", value: String(format: "%.1f km/h", best.track.motion.speedKmh))
                        LabeledContent("Rumbo", value: String(format: "%.0f°", best.track.motion.bearingDeg))
                        LabeledContent("Zmax", value: "\(best.track.zmaxDbz) dBZ")
                        LabeledContent("Confianza", value: "\(Int((best.confidence * 100).rounded()))%")
                    }
                } else {
                    Section("Evaluación") {
                        Text(model.nowcast == nil
                             ? "No hay diez frames radar válidos para calcular movimiento. DanaSafe no usa datos antiguos ni simulados."
                             : "Pulsa «Evaluar mi ubicación» para calcular ETA y paso mínimo localmente.")
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Tracks con movimiento") {
                    if model.nowcast?.tracks.isEmpty != false {
                        Text("Sin tracks con movimiento estimable en el ciclo actual.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(model.threatAssessments.prefix(20)) { assessment in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(assessment.track.id).font(.headline)
                                Spacer()
                                Text(assessment.level.title).font(.caption.bold())
                            }
                            Text("\(assessment.track.zmaxDbz) dBZ · \(String(format: "%.0f", assessment.track.motion.speedKmh)) km/h · rumbo \(String(format: "%.0f", assessment.track.motion.bearingDeg))°")
                                .font(.caption)
                            if let eta = assessment.etaMinutes {
                                Text("ETA ~\(Int(eta.rounded())) min · paso \(String(format: "%.1f", assessment.closestApproachKm)) km")
                                    .font(.caption2)
                            } else {
                                Text("Paso mínimo \(String(format: "%.1f", assessment.closestApproachKm)) km")
                                    .font(.caption2)
                            }
                        }
                    }
                }

                Section("Notificaciones") {
                    LabeledContent("Permiso", value: notificationStatusText)
                    Button("Activar notificaciones DanaSafe") {
                        Task { _ = await notificationManager.requestAuthorization() }
                    }
                    .accessibilityIdentifier("nowcast.notifications")
                    Text("DanaSafe 8.2 genera avisos locales tras evaluar una trayectoria real del radar. El cálculo de ubicación se realiza en el iPhone; el Worker no recibe tu GPS.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Ahora")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Ayuda", systemImage: "questionmark.circle") {
                        showHelp = true
                    }
                    .accessibilityIdentifier("nowcast.help")
                }
            }
            .sheet(isPresented: $showHelp) {
                DanaSafeNowcastHelpView(model: model, forecast: precipitationForecast)
            }
            .task {
                guard !ProcessInfo.processInfo.arguments.contains("--ui-testing") else { return }
                await notificationManager.refreshAuthorizationStatus()
                // Lightweight live polling: never starts the expensive backend engine.
                // It only reads the latest atomic snapshot already published by the production Worker.
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(60))
                    if Task.isCancelled { break }
                    await model.loadFromCloudflare()
                    if let coordinate = locationService.location?.coordinate {
                        evaluateAndNotify(at: coordinate)
                    }
                }
            }
            .onChange(of: locationService.location) { _, newLocation in
                guard let newLocation else { return }
                evaluateAndNotify(at: newLocation.coordinate)
            }
        }
    }

    private var precipitationForecast: LocalPrecipitationForecast? {
        guard let best = model.bestThreat,
              let coordinate = locationService.location?.coordinate else { return nil }
        return PrecipitationForecast.build(track: best.track, radarFrames: model.frames, userCoordinate: coordinate)
    }

    private func evaluateAndNotify(at coordinate: CLLocationCoordinate2D) {
        model.evaluateNowcast(target: coordinate)
        if let best = model.bestThreat, let radarTimestamp = model.nowcast?.radarTimestamp {
            Task { await notificationManager.notifyIfNeeded(best, radarTimestamp: radarTimestamp) }
        }
    }

    private var notificationStatusText: String {
        switch notificationManager.authorizationStatus {
        case .authorized: return "Autorizadas"
        case .provisional: return "Provisionales"
        case .denied: return "Denegadas"
        case .notDetermined: return "Sin solicitar"
        case .ephemeral: return "Efímeras"
        @unknown default: return "Desconocido"
        }
    }
}

private struct DanaSafeNowcastHelpView: View {
    @ObservedObject var model: DanaSafeModel
    let forecast: LocalPrecipitationForecast?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Qué está viendo DanaSafe") {
                    Text("DanaSafe 8.2 mantiene el Worker de producción validado. El Worker entrega el snapshot radar validado; si no incluye nowcast, el iPhone calcula el movimiento a partir de los diez frames de ese mismo snapshot.")
                    LabeledContent("Endpoint", value: "danasafe-radar.firefritz.workers.dev")
                    LabeledContent("Radar", value: model.nowcast?.radarTimestamp ?? model.selectedFrame?.timestamp ?? "—")
                    LabeledContent("Fuente", value: model.nowcastSource)
                }

                Section("Cómo se calcula") {
                    Text("Los sistemas se asocian entre frames por distancia, cambio de área y Zmax. Se usan hasta las cuatro observaciones más recientes para estimar el vector de movimiento. Solo se aceptan velocidades entre 2 y 180 km/h y se proyectan posiciones a 15, 30, 45, 60, 90 y 120 minutos.")
                    Text("La ETA y el paso mínimo se calculan después en el dispositivo respecto a tu ubicación. Tu GPS no se envía al Worker.")
                }

                if let forecast {
                    Section("Lluvia prevista en tu posición") {
                        ForEach(forecast.accumulations) { item in
                            LabeledContent("\(item.minutes) min", value: String(format: "%.2f mm · %.2f M L/celda", item.centralMm, item.centralLitresPerCell / 1_000_000.0))
                        }
                    }
                }

                Section("Interpretación") {
                    Text("Nowcast es una extrapolación de movimiento, no una predicción meteorológica determinista. La confianza disminuye cuando el sistema cambia de forma, intensidad o dirección. Conviene interpretar ETA, dBZ, tendencia y avisos oficiales conjuntamente.")
                }

                Section("Actualización") {
                    Text("Mientras la pestaña «Ahora» está abierta, DanaSafe consulta cada 60 segundos el último snapshot atómico ya publicado. El botón «Actualizar radar y nowcast» sí solicita un nuevo ciclo al Worker siguiendo el contrato asíncrono validado.")
                }
            }
            .navigationTitle("Ayuda Nowcast")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("OK") { dismiss() }
                        .accessibilityIdentifier("nowcast.help.dismiss")
                }
            }
        }
    }
}
