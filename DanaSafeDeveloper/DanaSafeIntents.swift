import AppIntents
import CoreLocation
import Foundation

struct RainArrivalIntent: AppIntent {
    static var title: LocalizedStringResource = "¿Cuánto falta para que llueva?"
    static var description = IntentDescription("Consulta el nowcast DanaSafe 8.1 para tu ubicación actual usando el radar de producción.")
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        do {
            let coordinate = try await OneShotIntentLocation.currentCoordinate()
            let snapshot = try await IntentSnapshotLoader.load(refresh: false)
            guard let nowcast = snapshot.nowcast ?? NowcastBuilderV7.build(from: snapshot.radar) else {
                return .result(dialog: "DanaSafe no dispone de diez frames radar válidos para calcular el nowcast en este momento.")
            }
            guard let assessment = NowcastEvaluator.best(nowcast: nowcast, target: coordinate) else {
                return .result(dialog: "DanaSafe no detecta sistemas con movimiento estimable en el radar actual.")
            }
            if let eta = assessment.etaMinutes {
                return .result(dialog: "DanaSafe detecta precipitación en trayectoria compatible con tu posición. Llegada estimada en unos \(Int(eta.rounded())) minutos, con una confianza del \(Int((assessment.confidence * 100).rounded())) por ciento.")
            }
            return .result(dialog: "DanaSafe detecta sistemas radar, pero ninguno tiene ahora una trayectoria de llegada a tu posición dentro de las próximas dos horas.")
        } catch {
            return .result(dialog: "No he podido consultar DanaSafe: \(error.localizedDescription)")
        }
    }
}

struct RainAmountIntent: AppIntent {
    static var title: LocalizedStringResource = "Lluvia prevista en mi ubicación"
    static var description = IntentDescription("Estima la precipitación acumulada en 10, 30 y 60 minutos con el radar y nowcast de DanaSafe 8.1.")
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        do {
            let coordinate = try await OneShotIntentLocation.currentCoordinate()
            let snapshot = try await IntentSnapshotLoader.load(refresh: false)
            guard let nowcast = snapshot.nowcast ?? NowcastBuilderV7.build(from: snapshot.radar) else {
                return .result(dialog: "DanaSafe no dispone de diez frames radar válidos para calcular lluvia prevista.")
            }
            guard let assessment = NowcastEvaluator.best(nowcast: nowcast, target: coordinate) else {
                return .result(dialog: "DanaSafe no detecta sistemas con movimiento estimable en el radar actual.")
            }
            guard let forecast = PrecipitationForecast.build(track: assessment.track, radarFrames: snapshot.radar.frames, userCoordinate: coordinate) else {
                return .result(dialog: "DanaSafe no puede calcular una estimación cuantitativa de lluvia para tu posición en este momento.")
            }
            let mm10 = forecast.accumulation(minutes: 10)?.centralMm ?? 0
            let mm30 = forecast.accumulation(minutes: 30)?.centralMm ?? 0
            let mm60 = forecast.accumulation(minutes: 60)?.centralMm ?? 0
            return .result(dialog: "Estimación DanaSafe: \(String(format: "%.2f", mm10)) milímetros en 10 minutos, \(String(format: "%.2f", mm30)) en 30 minutos y \(String(format: "%.2f", mm60)) en una hora. Es una estimación radar orientativa.")
        } catch {
            return .result(dialog: "No he podido calcular la lluvia prevista con DanaSafe: \(error.localizedDescription)")
        }
    }
}

struct RadarStatusIntent: AppIntent {
    static var title: LocalizedStringResource = "Estado del radar DanaSafe"
    static var description = IntentDescription("Resume el radar y el nowcast publicados.")
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        do {
            let snapshot = try await IntentSnapshotLoader.load(refresh: false)
            let systems = snapshot.radar.frames.last?.systems.count ?? 0
            let localNowcast = snapshot.nowcast ?? NowcastBuilderV7.build(from: snapshot.radar)
            let moving = localNowcast?.trackCount ?? 0
            return .result(dialog: "Radar DanaSafe \(snapshot.radarTimestamp): \(systems) sistemas en el último frame y \(moving) tracks con movimiento estimado.")
        } catch {
            return .result(dialog: "No he podido consultar el radar DanaSafe: \(error.localizedDescription)")
        }
    }
}

struct RefreshDanaSafeIntent: AppIntent {
    static var title: LocalizedStringResource = "Actualizar DanaSafe"
    static var description = IntentDescription("Solicita a Cloudflare la actualización del radar DanaSafe.")
    static var openAppWhenRun = false

    func perform() async throws -> some IntentResult & ProvidesDialog {
        do {
            let snapshot = try await IntentSnapshotLoader.load(refresh: true)
            return .result(dialog: "DanaSafe actualizado. Radar \(snapshot.radarTimestamp).")
        } catch {
            return .result(dialog: "No he podido actualizar DanaSafe: \(error.localizedDescription)")
        }
    }
}

struct DanaSafeShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: RainArrivalIntent(),
            phrases: [
                "¿Cuánto falta para que llueva con \(.applicationName)?",
                "¿Va a llover aquí con \(.applicationName)?",
                "Consulta la lluvia con \(.applicationName)"
            ],
            shortTitle: "ETA lluvia",
            systemImageName: "cloud.rain"
        )
        AppShortcut(
            intent: RainAmountIntent(),
            phrases: [
                "¿Cuánta lluvia caerá con \(.applicationName)?",
                "Lluvia prevista con \(.applicationName)"
            ],
            shortTitle: "Lluvia 10 30 60",
            systemImageName: "cloud.heavyrain"
        )
        AppShortcut(
            intent: RadarStatusIntent(),
            phrases: [
                "¿Qué detecta \(.applicationName)?",
                "Estado del radar en \(.applicationName)"
            ],
            shortTitle: "Estado radar",
            systemImageName: "dot.radiowaves.left.and.right"
        )
        AppShortcut(
            intent: RefreshDanaSafeIntent(),
            phrases: ["Actualiza \(.applicationName)"],
            shortTitle: "Actualizar radar",
            systemImageName: "arrow.clockwise"
        )
    }
}

private enum IntentSnapshotLoader {
    static func load(refresh: Bool) async throws -> DanaSafeLiveSnapshot {
        let api = DanaSafeAPIClient()
        let data: Data
        if refresh {
            let start = try await api.startRadarRefresh()
            switch start {
            case .completedSnapshot(let snapshotData):
                data = snapshotData
            case .accepted:
                let deadline = Date().addingTimeInterval(15 * 60)
                var snapshotData: Data?
                while Date() < deadline {
                    try await Task.sleep(nanoseconds: 3_000_000_000)
                    let status = try await api.refreshStatus()
                    switch status.state.lowercased() {
                    case "ready", "completed", "complete":
                        snapshotData = try await api.snapshot()
                    case "error", "failed", "failure":
                        throw DanaSafeAPIError.refreshFailed(status.error ?? "unknown backend error")
                    default:
                        break
                    }
                    if snapshotData != nil { break }
                }
                guard let snapshotData else { throw DanaSafeAPIError.refreshTimeout }
                data = snapshotData
            }
        } else {
            data = try await api.snapshot()
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(DanaSafeLiveSnapshot.self, from: data)
    }
}

@MainActor
private final class OneShotIntentLocation: NSObject, @preconcurrency CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocationCoordinate2D, Error>?

    static func currentCoordinate() async throws -> CLLocationCoordinate2D {
        let provider = OneShotIntentLocation()
        return try await provider.request()
    }

    private func request() async throws -> CLLocationCoordinate2D {
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            switch manager.authorizationStatus {
            case .authorizedAlways, .authorizedWhenInUse:
                manager.requestLocation()
            case .notDetermined:
                manager.requestWhenInUseAuthorization()
            default:
                continuation.resume(throwing: CLError(.denied))
                self.continuation = nil
            }
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        guard continuation != nil else { return }
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            manager.requestLocation()
        case .denied, .restricted:
            continuation?.resume(throwing: CLError(.denied))
            continuation = nil
        default:
            break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let coordinate = locations.last?.coordinate else {
            continuation?.resume(throwing: CLError(.locationUnknown))
            continuation = nil
            return
        }
        continuation?.resume(returning: coordinate)
        continuation = nil
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }
}
