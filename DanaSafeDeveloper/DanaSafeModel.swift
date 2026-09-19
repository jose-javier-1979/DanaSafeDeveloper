import Foundation
import CoreLocation
import Combine

@MainActor
final class DanaSafeModel: ObservableObject {
    static let cloudflareBaseURL = DanaSafeAPIClient.productionBaseURL
    private let api = DanaSafeAPIClient()

    @Published var radarFile: RadarSystemsFile?
    @Published var tracks: [RadarTrack] = []
    @Published var contoursFile: ContoursFile?
    @Published var hydrology: SAIHFile?
    @Published var selectedFrameIndex: Int = 0
    @Published var showSignificantOnly = false
    @Published var dataSource = "Bundled fallback snapshot"
    @Published var lastRefresh: Date?
    @Published var snapshotGeneratedAt: Date?
    @Published var errorMessage: String?
    @Published var cloudflareHealth: String = "Not checked"
    @Published var cloudflareVersion: String?
    @Published var latestAEMETInfo: String = "Not checked"
    @Published var historyStatus: String = "Not checked"
    @Published var isRefreshing = false
    @Published var refreshProgress: String = "Idle"
    @Published var nowcast: RadarNowcastFile?
    @Published var nowcastSource: String = "Unavailable"
    @Published var threatAssessments: [RadarThreatAssessment] = []

    private var lastNowcastTarget: CLLocationCoordinate2D?

    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    var frames: [RadarFrame] { radarFile?.frames ?? [] }

    var bestThreat: RadarThreatAssessment? { threatAssessments.first }

    func evaluateNowcast(target: CLLocationCoordinate2D) {
        lastNowcastTarget = target
        guard let nowcast else {
            threatAssessments = []
            return
        }
        threatAssessments = NowcastEvaluator.evaluate(nowcast: nowcast, target: target)
    }

    var selectedFrame: RadarFrame? {
        guard frames.indices.contains(selectedFrameIndex) else { return frames.last }
        return frames[selectedFrameIndex]
    }

    var displayedSystems: [RadarSystem] {
        let systems = selectedFrame?.systems ?? []
        return showSignificantOnly ? systems.filter(\.isSignificant) : systems
    }

    var significantCount: Int {
        selectedFrame?.systems.filter(\.isSignificant).count ?? 0
    }

    var contourLevels: [Int] {
        contoursFile?.levelsDbz ?? []
    }

    var radarAgeMinutes: Int? {
        guard let date = lastRefresh else { return nil }
        return max(0, Int(Date().timeIntervalSince(date) / 60))
    }

    var radarIsFresh: Bool {
        guard let age = radarAgeMinutes else { return false }
        return age <= 30
    }

    var freshnessText: String {
        guard let age = radarAgeMinutes else { return "Unknown age" }
        if age <= 2 { return "LIVE" }
        if age <= 30 { return "LIVE · \(age) min" }
        return "STALE · \(age) min"
    }

    func loadBundled() {
        do {
            radarFile = try loadResource("radar_systems_v03", as: RadarSystemsFile.self)
            let trackFile: ReliableTracksFile = try loadResource("reliable_tracks", as: ReliableTracksFile.self)
            tracks = trackFile.tracks
            contoursFile = try loadResource("national_marching_contours", as: ContoursFile.self)
            hydrology = try loadResource("saih_stations", as: SAIHFile.self)
            nowcast = nil
            nowcastSource = "Bundled fallback · no live nowcast"
            threatAssessments = []
            selectedFrameIndex = max(0, frames.count - 1)
            dataSource = "Bundled fallback snapshot"
            lastRefresh = radarFile.flatMap(radarObservationDate)
            snapshotGeneratedAt = nil
            errorMessage = nil
        } catch {
            errorMessage = "Bundled data error: \(error.localizedDescription)"
        }
    }

    // MARK: - Production Cloudflare async client path

    /// Lightweight startup path: load the latest atomic snapshot already published in Cloudflare/R2.
    /// It never pretends that opening the app is a new AEMET observation.
    func loadFromCloudflare() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }

        do {
            await probeCloudflareHealth()
            let data = try await api.snapshot()
            let snapshot = try decoder.decode(DanaSafeLiveSnapshot.self, from: data)
            try validate(snapshot: snapshot)
            publish(snapshot: snapshot, source: "Cloudflare production · published atomic snapshot")
            cloudflareHealth = "Online · snapshot loaded"
        } catch {
            errorMessage = "Cloudflare snapshot: \(error.localizedDescription)"
            // Bundled fallback remains visible.
        }
    }

    /// DanaSafe 8.2 refresh path over the unchanged production Worker. The current Worker returns a synchronous HTTP 200 snapshot; the client also preserves compatibility with HTTP 202 queued/processing responses.
    /// When a 202 response is received, we poll /radar/refresh-status and download the atomic R2 snapshot only after ready.
    /// A newer AEMET slot appearing while the engine works no longer causes the newly
    /// generated valid snapshot to be discarded by the client.
    func refreshFromCloudflare() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer {
            isRefreshing = false
            if refreshProgress.hasPrefix("Waiting") || refreshProgress.hasPrefix("Queued") {
                refreshProgress = "Idle"
            }
        }

        do {
            latestAEMETInfo = "Consultando AEMET…"
            refreshProgress = "Requesting refresh…"

            let start = try await api.startRadarRefresh()
            switch start {
            case .completedSnapshot(let data):
                try await consumeRefreshedSnapshot(data, source: "Cloudflare production · synchronous snapshot")

            case .accepted(let accepted):
                let target = accepted.targetAemetTimestamp ?? accepted.latestAemetTimestamp ?? "latest"
                refreshProgress = "Queued · target \(target)"
                cloudflareHealth = "Refresh queued · \(target)"

                let deadline = Date().addingTimeInterval(15 * 60)
                while Date() < deadline {
                    try await Task.sleep(nanoseconds: 3_000_000_000)
                    let status = try await api.refreshStatus()
                    switch status.state.lowercased() {
                    case "ready", "completed", "complete":
                        refreshProgress = "Ready · downloading snapshot"
                        let data = try await api.snapshot()
                        try await consumeRefreshedSnapshot(data, source: "Cloudflare production · async atomic snapshot")

                        if let statusRadar = status.radarTimestamp,
                           let current = radarFile?.frames.last?.timestamp,
                           !sameInstant(statusRadar, current) {
                            throw NSError(
                                domain: "DanaSafeV522",
                                code: 5221,
                                userInfo: [NSLocalizedDescriptionKey: "Refresh status reports \(statusRadar), but R2 snapshot contains \(current)."]
                            )
                        }
                        return

                    case "error", "failed", "failure":
                        throw DanaSafeAPIError.refreshFailed(status.error ?? "unknown backend error")

                    default:
                        let target = status.targetAemetTimestamp ?? target
                        refreshProgress = "Waiting · \(status.state) · target \(target)"
                        cloudflareHealth = "Refresh \(status.state) · target \(target)"
                    }
                }

                throw DanaSafeAPIError.refreshTimeout
            }

            refreshProgress = "Completed"
        } catch {
            cloudflareHealth = "Refresh failed"
            refreshProgress = "Failed"
            errorMessage = "Actualización 8.2: \(error.localizedDescription)"
            // Never destroy the last validated snapshot on failure.
        }
    }

    private func consumeRefreshedSnapshot(_ data: Data, source: String) async throws {
        let snapshot = try decoder.decode(DanaSafeLiveSnapshot.self, from: data)
        try validate(snapshot: snapshot)

        // Never move the UI backwards if R2 ever serves an older snapshot.
        if let current = lastRefresh,
           let incoming = parseISO8601(snapshot.radarTimestamp),
           incoming < current {
            throw NSError(
                domain: "DanaSafeV522",
                code: 5222,
                userInfo: [NSLocalizedDescriptionKey: "Cloudflare attempted to regress radar from \(current) to \(incoming)."]
            )
        }

        publish(snapshot: snapshot, source: source)

        // AEMET may advance by one slot while a long backend refresh is running.
        // Publish the valid new snapshot instead of discarding it, and expose the
        // remaining lag explicitly in health/progress.
        if let latest = try? await api.latestAEMET(),
           let aemetTimestamp = latest.timestamp {
            latestAEMETInfo = "\(aemetTimestamp) · \(latest.filename ?? "AEMET")"
            if let a = parseISO8601(aemetTimestamp),
               let b = parseISO8601(snapshot.radarTimestamp) {
                let lagMinutes = max(0, Int((a.timeIntervalSince(b) / 60).rounded()))
                if lagMinutes == 0 {
                    cloudflareHealth = "Online · SYNC · radar \(snapshot.radarTimestamp)"
                    refreshProgress = "Completed · SYNC"
                } else {
                    cloudflareHealth = "Online · STALE \(lagMinutes) min · radar \(snapshot.radarTimestamp)"
                    refreshProgress = "Completed · AEMET +\(lagMinutes) min"
                }
            }
        } else {
            refreshProgress = "Completed"
        }

        errorMessage = nil
    }

    private func sameInstant(_ a: String, _ b: String) -> Bool {
        guard let aa = parseISO8601(a), let bb = parseISO8601(b) else { return false }
        return abs(aa.timeIntervalSince(bb)) < 1
    }

    func checkCloudflare() async {
        await probeCloudflareHealth()
        await probeLatestAEMETInfo()
    }

    private func probeCloudflareHealth() async {
        do {
            let health = try await api.health()
            cloudflareVersion = health.version
            let sync = health.inSync.map { $0 ? "SYNC" : "STALE" } ?? "?"
            cloudflareHealth = "Online · \(health.status) · \(sync)"
            if let radar = health.radarTimestamp { cloudflareHealth += " · radar \(radar)" }
            if let latest = health.latestAemetTimestamp { latestAEMETInfo = latest }
            if health.historyEnabled == true {
                let cycles = health.historyCyclesVisible ?? 0
                let policy = health.archivePolicy ?? "archive-before-live"
                historyStatus = "ON · \(cycles) ciclos · \(policy)"
            } else {
                historyStatus = "OFF"
            }
        } catch {
            cloudflareHealth = "Unavailable · \(error.localizedDescription)"
        }
    }

    private func probeLatestAEMETInfo() async {
        do {
            let latest = try await api.latestAEMET()
            if let timestamp = latest.timestamp {
                latestAEMETInfo = "\(timestamp) · \(latest.filename ?? "AEMET")"
            } else {
                latestAEMETInfo = "AEMET endpoint online"
            }
        } catch {
            latestAEMETInfo = "Unavailable · \(error.localizedDescription)"
        }
    }

    private func publish(snapshot: DanaSafeLiveSnapshot, source: String) {
        radarFile = snapshot.radar
        tracks = snapshot.tracks.tracks
        contoursFile = snapshot.contours
        hydrology = snapshot.hydrology
        if let serverNowcast = snapshot.nowcast {
            nowcast = serverNowcast
            nowcastSource = "Worker snapshot"
        } else {
            nowcast = NowcastBuilderV7.build(from: snapshot.radar)
            nowcastSource = nowcast == nil
                ? "Unavailable · insufficient live radar history"
                : "DanaSafe 8.2 on-device · snapshot de producción"
        }
        threatAssessments = []
        if let target = lastNowcastTarget, let nowcast {
            threatAssessments = NowcastEvaluator.evaluate(nowcast: nowcast, target: target)
        }
        selectedFrameIndex = max(0, snapshot.radar.frames.count - 1)
        dataSource = source
        lastRefresh = parseISO8601(snapshot.radarTimestamp)
        snapshotGeneratedAt = parseISO8601(snapshot.generatedAt)
        errorMessage = nil
    }

    private func validate(snapshot: DanaSafeLiveSnapshot) throws {
        guard snapshot.radar.frames.count == 10,
              snapshot.frameIntervalMinutes > 0,
              let latest = snapshot.radar.frames.last?.timestamp,
              latest == snapshot.radarTimestamp,
              parseISO8601(snapshot.radarTimestamp) != nil,
              parseISO8601(snapshot.generatedAt) != nil else {
            throw NSError(domain: "DanaSafeSnapshot", code: 10, userInfo: [NSLocalizedDescriptionKey: "Incomplete or inconsistent radar snapshot"])
        }

        let parsed = snapshot.radar.frames.compactMap { parseISO8601($0.timestamp) }
        guard parsed.count == 10 else {
            throw NSError(domain: "DanaSafeSnapshot", code: 14, userInfo: [NSLocalizedDescriptionKey: "Radar snapshot contains an invalid timestamp"])
        }

        for (previous, current) in zip(parsed, parsed.dropFirst()) {
            let delta = Int(current.timeIntervalSince(previous).rounded())
            if delta != snapshot.frameIntervalMinutes * 60 {
                throw NSError(domain: "DanaSafeSnapshot", code: 13, userInfo: [NSLocalizedDescriptionKey: "Radar frames are not consecutive"])
            }
        }

        guard snapshot.contours.timestamp == snapshot.radarTimestamp else {
            throw NSError(domain: "DanaSafeSnapshot", code: 11, userInfo: [NSLocalizedDescriptionKey: "Contour timestamp does not match radar timestamp"])
        }

        let frameTimes = Set(snapshot.radar.frames.map(\.timestamp))
        let invalidTrack = snapshot.tracks.tracks.first {
            !frameTimes.contains($0.start.timestamp) || !frameTimes.contains($0.end.timestamp)
        }
        if invalidTrack != nil {
            throw NSError(domain: "DanaSafeSnapshot", code: 12, userInfo: [NSLocalizedDescriptionKey: "Track data belongs to another radar cycle"])
        }

        if let nowcast = snapshot.nowcast, nowcast.radarTimestamp != snapshot.radarTimestamp {
            throw NSError(domain: "DanaSafeSnapshot", code: 16, userInfo: [NSLocalizedDescriptionKey: "Nowcast timestamp does not match radar timestamp"])
        }
    }

    private func radarObservationDate(from radar: RadarSystemsFile) -> Date? {
        guard let raw = radar.frames.last?.timestamp else { return nil }
        return parseISO8601(raw)
    }

    private func parseISO8601(_ raw: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: raw) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: raw)
    }

    private func loadResource<T: Decodable>(_ name: String, as type: T.Type) throws -> T {
        guard let url = Bundle.main.url(forResource: name, withExtension: "json") else {
            throw CocoaError(.fileNoSuchFile)
        }
        let data = try Data(contentsOf: url)
        return try decoder.decode(T.self, from: data)
    }

}
