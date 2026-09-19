import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

struct DanaSafeBackendHealth: Decodable {
    let service: String
    let status: String
    let version: String?
    let radarTimestamp: String?
    let snapshotGeneratedAt: String?
    let latestAemetTimestamp: String?
    let inSync: Bool?
    let refreshState: String?
    let refreshRequestedAt: String?
    let refreshStartedAt: String?
    let refreshCompletedAt: String?
    let refreshTargetTimestamp: String?
    let refreshError: String?
    let aemetError: String?
}

struct DanaSafeAEMETLatestInfo: Decodable {
    let status: String?
    let timestamp: String?
    let filename: String?
    let source: String?
}

struct DanaSafeRefreshAccepted: Decodable {
    let status: String
    let refreshState: String
    let changed: Bool?
    let targetAemetTimestamp: String?
    let latestAemetTimestamp: String?
    let poll: String?
}

struct DanaSafeRefreshStatus: Decodable {
    let state: String
    let requestedAt: String?
    let startedAt: String?
    let completedAt: String?
    let targetAemetTimestamp: String?
    let radarTimestamp: String?
    let error: String?
}

enum DanaSafeRefreshStart {
    case completedSnapshot(Data)
    case accepted(DanaSafeRefreshAccepted)
}

enum DanaSafeAPIError: LocalizedError {
    case http(Int, String)
    case invalidResponse
    case unsupportedPayload
    case refreshFailed(String)
    case refreshTimeout

    var errorDescription: String? {
        switch self {
        case .http(let status, let message): return "HTTP \(status): \(message)"
        case .invalidResponse: return "Invalid DanaSafe backend response"
        case .unsupportedPayload: return "Unsupported DanaSafe snapshot payload"
        case .refreshFailed(let message): return "Cloudflare refresh failed: \(message)"
        case .refreshTimeout: return "Cloudflare refresh did not complete before the 15-minute client timeout"
        }
    }
}

struct DanaSafeAPIClient {
    static let productionBaseURL = URL(string: "https://danasafe-radar.firefritz.workers.dev")!

    let baseURL: URL

    init(baseURL: URL = Self.productionBaseURL) {
        self.baseURL = baseURL
    }

    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    func health() async throws -> DanaSafeBackendHealth {
        let (data, _) = try await request(path: "health", method: "GET", timeout: 20)
        return try decoder.decode(DanaSafeBackendHealth.self, from: data)
    }

    func latestAEMET() async throws -> DanaSafeAEMETLatestInfo {
        let (data, _) = try await request(path: "aemet/latest-image-info", method: "GET", timeout: 30)
        return try decoder.decode(DanaSafeAEMETLatestInfo.self, from: data)
    }

    /// Loads the last complete atomic snapshot already published in R2.
    func snapshot() async throws -> Data {
        let (data, _) = try await request(path: "radar/snapshot", method: "GET", timeout: 60)
        return data
    }

    /// DanaSafe 8.1 keeps the validated production synchronous/asynchronous compatibility contract.
    /// Production 5.2.1 may return either:
    /// - HTTP 200 + a complete atomic snapshot when no asynchronous work is required, or
    /// - HTTP 202 + an accepted/queued envelope which must be followed via /radar/refresh-status.
    func startRadarRefresh() async throws -> DanaSafeRefreshStart {
        let (data, response) = try await request(path: "radar/refresh", method: "POST", timeout: 300)
        if response.statusCode == 202 {
            return .accepted(try decoder.decode(DanaSafeRefreshAccepted.self, from: data))
        }
        if response.statusCode == 200 {
            return .completedSnapshot(data)
        }
        throw DanaSafeAPIError.unsupportedPayload
    }

    func refreshStatus() async throws -> DanaSafeRefreshStatus {
        let (data, _) = try await request(path: "radar/refresh-status", method: "GET", timeout: 20)
        return try decoder.decode(DanaSafeRefreshStatus.self, from: data)
    }

    private func request(path: String, method: String, timeout: TimeInterval) async throws -> (Data, HTTPURLResponse) {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store, no-cache", forHTTPHeaderField: "Cache-Control")
        request.setValue("DanaSafe-iOS/8.1-worker64-nowcast-local", forHTTPHeaderField: "User-Agent")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw DanaSafeAPIError.invalidResponse }
        guard (200...299).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Backend error"
            throw DanaSafeAPIError.http(http.statusCode, String(message.prefix(1000)))
        }
        return (data, http)
    }
}
