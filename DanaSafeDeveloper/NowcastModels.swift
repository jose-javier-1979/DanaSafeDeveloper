import Foundation
import CoreLocation

struct RadarNowcastFile: Decodable {
    let schema: SchemaInfo?
    let generatedAt: String
    let radarTimestamp: String
    let horizonMinutes: Int
    let trackCount: Int
    let tracks: [NowcastTrack]
}

struct NowcastTrack: Identifiable, Decodable {
    let id: String
    let frameCount: Int
    let firstTimestamp: String
    let latestTimestamp: String
    let latestSystemId: String
    let latestCoordinate: RadarCoordinate
    let rootAreaPx: Int
    let zmaxDbz: Int
    let radiusKm: Double
    let motion: NowcastMotion
    let confidence: Double
    let forecast: [NowcastForecastPoint]
}

struct NowcastMotion: Decodable {
    let speedKmh: Double
    let bearingDeg: Double
    let velocityEastKmh: Double
    let velocityNorthKmh: Double
    let vectorStability: Double
}

struct NowcastForecastPoint: Identifiable, Decodable {
    let minutes: Int
    let coordinate: RadarCoordinate
    var id: Int { minutes }
}

enum RadarThreatLevel: Int, Comparable {
    case none = 0
    case nearby = 1
    case possible = 2
    case approaching = 3
    case high = 4

    static func < (lhs: RadarThreatLevel, rhs: RadarThreatLevel) -> Bool {
        lhs.rawValue < rhs.rawValue
    }

    var title: String {
        switch self {
        case .none: return "Sin amenaza"
        case .nearby: return "Sistema próximo"
        case .possible: return "Posible aproximación"
        case .approaching: return "Lluvia aproximándose"
        case .high: return "Lluvia intensa aproximándose"
        }
    }
}

struct RadarThreatAssessment: Identifiable {
    let id: String
    let track: NowcastTrack
    let distanceKm: Double
    let closestApproachKm: Double
    let etaMinutes: Double?
    let projectedCoordinate: CLLocationCoordinate2D
    let confidence: Double
    let level: RadarThreatLevel
}
