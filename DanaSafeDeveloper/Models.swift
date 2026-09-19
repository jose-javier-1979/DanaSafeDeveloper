import Foundation
import CoreLocation


struct DanaSafeLiveSnapshot: Decodable {
    let schema: SchemaInfo?
    let provider: String?
    let generatedAt: String
    let radarTimestamp: String
    let frameIntervalMinutes: Int
    let radar: RadarSystemsFile
    let tracks: ReliableTracksFile
    let contours: ContoursFile
    let hydrology: SAIHFile
    let nowcast: RadarNowcastFile?
}



// MARK: - Cloudflare Worker compact contract (original DanaSafe backend)

struct CloudflareRadarResponse: Decodable {
    let status: String
    let version: String
    let snapshot: CloudflareRadarSnapshot
}

struct CloudflareRadarSnapshot: Decodable {
    let timestamp: String
    let systems: [RadarSystem]
}

struct DanaSafeServerHealth: Decodable {
    let service: String
    let version: String?
    let status: String
    let radarTimestamp: String?
    let radarSystems: Int?
    let snapshotGeneratedAt: String?
}

struct RadarSystemsFile: Decodable {
    let schema: SchemaInfo?
    let provider: String?
    let product: String?
    let projection: String?
    let frames: [RadarFrame]
}

struct SchemaInfo: Decodable {
    let name: String?
    let version: String?
}

struct RadarFrame: Identifiable, Decodable {
    let frame: Int
    let timestamp: String
    let systems: [RadarSystem]
    var id: Int { frame }
}

struct RadarSystem: Identifiable, Decodable {
    let id: String
    let frame: Int
    let timestamp: String
    let rootLevelDbz: Int
    let rootAreaPx: Int
    let zmaxDbz: Int
    let centroid: RadarCoordinate
    let bboxPx: [Int]
    let levels: [String: RadarLevel]
    let rank: Int

    enum CodingKeys: String, CodingKey {
        case id, frame, timestamp, centroid, levels, rank
        case rootLevelDbz, rootAreaPx, zmaxDbz, bboxPx
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        frame = try c.decodeIfPresent(Int.self, forKey: .frame) ?? 1
        timestamp = try c.decodeIfPresent(String.self, forKey: .timestamp) ?? ""
        rootLevelDbz = try c.decodeIfPresent(Int.self, forKey: .rootLevelDbz) ?? 12
        rootAreaPx = try c.decodeIfPresent(Int.self, forKey: .rootAreaPx) ?? 0
        zmaxDbz = try c.decodeIfPresent(Int.self, forKey: .zmaxDbz) ?? 0
        centroid = try c.decode(RadarCoordinate.self, forKey: .centroid)
        bboxPx = try c.decodeIfPresent([Int].self, forKey: .bboxPx) ?? []
        levels = try c.decodeIfPresent([String: RadarLevel].self, forKey: .levels) ?? [:]
        rank = try c.decodeIfPresent(Int.self, forKey: .rank) ?? 0
    }

    var isSignificant: Bool {
        rootAreaPx >= 20 || zmaxDbz >= 36
    }
}

struct RadarCoordinate: Decodable {
    let longitude: Double
    let latitude: Double

    var clLocationCoordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }
}

struct RadarLevel: Decodable {
    let componentCount: Int
    let areaPx: Int
}

struct ReliableTracksFile: Decodable {
    let tracks: [RadarTrack]
}

struct RadarTrack: Identifiable, Decodable {
    let trackId: String
    let levelDbz: Int
    let frames: Int
    let start: TrackEndpoint
    let end: TrackEndpoint
    let meanSpeedKmh: Double
    let movements: [TrackMovement]

    var id: String { trackId }
}

struct TrackEndpoint: Decodable {
    let frame: Int
    let timestamp: String
    let centroid: RadarCoordinate
}

struct TrackMovement: Decodable {
    let fromFrame: Int
    let toFrame: Int
    let distanceKm: Double
    let speedKmh: Double
    let bearingDeg: Double
    let areaChangePx: Int
}

struct ContoursFile: Decodable {
    let timestamp: String?
    let levelsDbz: [Int]
    let levels: [ContourLevel]
}

struct ContourLevel: Identifiable, Decodable {
    let levelDbz: Int
    let contours: [RadarContour]
    var id: Int { levelDbz }
}

struct RadarContour: Identifiable, Decodable {
    let id: String
    let levelDbz: Int
    let closed: Bool
    let pointCount: Int
    let centroid: RadarCoordinate
    let coordinates: [[Double]]

    var mapCoordinates: [CLLocationCoordinate2D] {
        coordinates.compactMap { pair in
            guard pair.count >= 2 else { return nil }
            return CLLocationCoordinate2D(latitude: pair[1], longitude: pair[0])
        }
    }
}

struct SAIHFile: Decodable {
    let source: String
    let retrievedAt: String
    let stationCount: Int
    let stations: [SAIHStation]
}

struct SAIHStation: Identifiable, Decodable {
    let id: String
    let station: String
    let variable: String
    let flowM3s: Double?
    let thresholdsM3s: SAIHThresholds?
    let time: String?
    let status: String
    let source: String
    let observed: Bool?
}

struct SAIHThresholds: Decodable {
    let yellow: Double?
    let orange: Double?
    let red: Double?
}
