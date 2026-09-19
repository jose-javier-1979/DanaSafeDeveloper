import Foundation
import CoreLocation

// MARK: - DanaSafe V7 local nowcast builder
//
// IMPORTANT ARCHITECTURE INVARIANT
// The production backend remains the validated DanaSafe 6.4 endpoint.
// When that atomic snapshot does not contain a server-side `nowcast` block,
// V7 derives the motion forecast locally from the SAME ten live radar frames.
// This keeps the Worker untouched while avoiding stale/simulated nowcast data.

enum NowcastBuilderV7 {
    private static let maxAssociationKm = 90.0
    private static let maxSpeedKmh = 180.0
    private static let minSpeedKmh = 2.0
    private static let horizonMinutes = [15, 30, 45, 60, 90, 120]
    private static let earthKmPerDegree = 111.32

    private struct TrackState {
        let id: String
        var observations: [RadarSystem]
    }

    static func build(from radar: RadarSystemsFile) -> RadarNowcastFile? {
        let frames = radar.frames.sorted { $0.frame < $1.frame }
        guard frames.count == 10, let latestTimestamp = frames.last?.timestamp else { return nil }

        var tracks: [TrackState] = []
        var serial = 1

        for frame in frames {
            var used = Set<String>()

            for index in tracks.indices {
                guard let latest = tracks[index].observations.last,
                      latest.frame == frame.frame - 1 else { continue }

                var best: (score: Double, system: RadarSystem)?
                for system in frame.systems where !used.contains(system.id) {
                    guard let score = associationScore(previous: latest, candidate: system), score < 1.0 else { continue }
                    if let currentBest = best {
                        if score < currentBest.score {
                            best = (score, system)
                        }
                    } else {
                        best = (score, system)
                    }
                }

                if let best {
                    tracks[index].observations.append(best.system)
                    used.insert(best.system.id)
                }
            }

            for system in frame.systems where !used.contains(system.id) {
                tracks.append(TrackState(id: String(format: "T%03d", serial), observations: [system]))
                serial += 1
            }
        }

        var records = tracks.compactMap(trackRecord)
        records.sort {
            if $0.confidence != $1.confidence { return $0.confidence > $1.confidence }
            if $0.zmaxDbz != $1.zmaxDbz { return $0.zmaxDbz > $1.zmaxDbz }
            return $0.id < $1.id
        }

        return RadarNowcastFile(
            schema: SchemaInfo(name: "DanaSafeRadarNowcast", version: "7.0.0"),
            generatedAt: iso8601Now(),
            radarTimestamp: latestTimestamp,
            horizonMinutes: horizonMinutes.max() ?? 120,
            trackCount: records.count,
            tracks: records
        )
    }

    private static func associationScore(previous: RadarSystem, candidate: RadarSystem) -> Double? {
        let distance = distanceKm(previous.centroid, candidate.centroid)
        guard distance <= maxAssociationKm else { return nil }

        let a1 = max(previous.rootAreaPx, 1)
        let a2 = max(candidate.rootAreaPx, 1)
        let areaRatio = Double(min(a1, a2)) / Double(max(a1, a2))
        let zPenalty = Double(abs(previous.zmaxDbz - candidate.zmaxDbz)) / 60.0
        return distance / maxAssociationKm + (1.0 - areaRatio) * 0.45 + zPenalty * 0.25
    }

    private static func trackRecord(_ track: TrackState) -> NowcastTrack? {
        guard let motion = motion(for: track.observations),
              let first = track.observations.first,
              let latest = track.observations.last else { return nil }

        let persistence = min(1.0, Double(track.observations.count) / 6.0)
        let confidence = min(0.95, 0.20 + 0.45 * persistence + 0.30 * motion.vectorStability)
        let radiusKm = max(4.0, sqrt(Double(max(latest.rootAreaPx, 1))) * 1.4)

        let forecast = horizonMinutes.map { minutes in
            let hours = Double(minutes) / 60.0
            return NowcastForecastPoint(
                minutes: minutes,
                coordinate: offset(
                    latest.centroid,
                    eastKm: motion.velocityEastKmh * hours,
                    northKm: motion.velocityNorthKmh * hours
                )
            )
        }

        return NowcastTrack(
            id: track.id,
            frameCount: track.observations.count,
            firstTimestamp: first.timestamp,
            latestTimestamp: latest.timestamp,
            latestSystemId: latest.id,
            latestCoordinate: latest.centroid,
            rootAreaPx: latest.rootAreaPx,
            zmaxDbz: latest.zmaxDbz,
            radiusKm: rounded(radiusKm, digits: 3),
            motion: NowcastMotion(
                speedKmh: rounded(motion.speedKmh, digits: 3),
                bearingDeg: rounded(motion.bearingDeg, digits: 3),
                velocityEastKmh: rounded(motion.velocityEastKmh, digits: 3),
                velocityNorthKmh: rounded(motion.velocityNorthKmh, digits: 3),
                vectorStability: rounded(motion.vectorStability, digits: 4)
            ),
            confidence: rounded(confidence, digits: 4),
            forecast: forecast
        )
    }

    private struct MotionVector {
        let speedKmh: Double
        let bearingDeg: Double
        let velocityEastKmh: Double
        let velocityNorthKmh: Double
        let vectorStability: Double
    }

    private static func motion(for observations: [RadarSystem]) -> MotionVector? {
        let recent = Array(observations.suffix(4))
        guard recent.count >= 3 else { return nil }

        var east = 0.0
        var north = 0.0
        var hours = 0.0
        var segmentVectors: [(east: Double, north: Double)] = []

        for (a, b) in zip(recent, recent.dropFirst()) {
            guard let aDate = parseISO8601(a.timestamp),
                  let bDate = parseISO8601(b.timestamp) else { continue }
            let dt = bDate.timeIntervalSince(aDate) / 3600.0
            guard dt > 0 else { continue }

            let delta = localXYKm(a.centroid, b.centroid)
            east += delta.east
            north += delta.north
            hours += dt
            segmentVectors.append((delta.east / dt, delta.north / dt))
        }

        guard hours > 0 else { return nil }
        let ve = east / hours
        let vn = north / hours
        let speed = hypot(ve, vn)
        guard speed >= minSpeedKmh, speed <= maxSpeedKmh else { return nil }

        var bearing = atan2(ve, vn) * 180.0 / .pi
        if bearing < 0 { bearing += 360.0 }

        let stability: Double
        if segmentVectors.count >= 2 {
            let meanVe = segmentVectors.reduce(0.0) { $0 + $1.east } / Double(segmentVectors.count)
            let meanVn = segmentVectors.reduce(0.0) { $0 + $1.north } / Double(segmentVectors.count)
            let residuals = segmentVectors.map { hypot($0.east - meanVe, $0.north - meanVn) }
            let meanResidual = residuals.reduce(0, +) / Double(residuals.count)
            stability = max(0, min(1, 1.0 - meanResidual / max(speed, 1.0)))
        } else {
            stability = 0.5
        }

        return MotionVector(
            speedKmh: speed,
            bearingDeg: bearing,
            velocityEastKmh: ve,
            velocityNorthKmh: vn,
            vectorStability: stability
        )
    }

    private static func localXYKm(_ a: RadarCoordinate, _ b: RadarCoordinate) -> (east: Double, north: Double) {
        let latMid = ((a.latitude + b.latitude) * 0.5) * .pi / 180.0
        let east = (b.longitude - a.longitude) * earthKmPerDegree * cos(latMid)
        let north = (b.latitude - a.latitude) * earthKmPerDegree
        return (east, north)
    }

    private static func distanceKm(_ a: RadarCoordinate, _ b: RadarCoordinate) -> Double {
        let delta = localXYKm(a, b)
        return hypot(delta.east, delta.north)
    }

    private static func offset(_ coordinate: RadarCoordinate, eastKm: Double, northKm: Double) -> RadarCoordinate {
        let latitude = coordinate.latitude + northKm / earthKmPerDegree
        let denominator = max(abs(cos(coordinate.latitude * .pi / 180.0)), 0.000001)
        let longitude = coordinate.longitude + eastKm / (earthKmPerDegree * denominator)
        return RadarCoordinate(
            longitude: rounded(longitude, digits: 6),
            latitude: rounded(latitude, digits: 6)
        )
    }

    private static func parseISO8601(_ raw: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: raw) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: raw)
    }

    private static func iso8601Now() -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: Date())
    }

    private static func rounded(_ value: Double, digits: Int) -> Double {
        let scale = pow(10.0, Double(digits))
        return (value * scale).rounded() / scale
    }
}

// MARK: - User-specific threat evaluation

enum NowcastEvaluator {
    static func evaluate(track: NowcastTrack, target: CLLocationCoordinate2D, horizonMinutes: Int = 120) -> RadarThreatAssessment {
        let p = track.latestCoordinate.clLocationCoordinate
        let latMid = (p.latitude + target.latitude) * 0.5 * .pi / 180
        let tx = (target.longitude - p.longitude) * 111.32 * cos(latMid)
        let ty = (target.latitude - p.latitude) * 111.32
        let ve = track.motion.velocityEastKmh
        let vn = track.motion.velocityNorthKmh
        let vv = ve * ve + vn * vn

        let maxHours = Double(horizonMinutes) / 60.0
        let rawT = vv > 0 ? (tx * ve + ty * vn) / vv : 0
        let closestHours = min(max(0, rawT), maxHours)
        let cx = ve * closestHours
        let cy = vn * closestHours
        let miss = hypot(tx - cx, ty - cy)
        let eta: Double? = rawT >= 0 && rawT <= maxHours && miss <= track.radiusKm ? rawT * 60.0 : nil
        let projected = offset(p, eastKm: cx, northKm: cy)
        let distance = CLLocation(latitude: p.latitude, longitude: p.longitude)
            .distance(from: CLLocation(latitude: target.latitude, longitude: target.longitude)) / 1000.0
        let geometry = max(0, 1.0 - miss / max(track.radiusKm * 2.0, 1.0))
        let confidence = min(0.95, max(0, track.confidence * 0.75 + geometry * 0.25))
        let level = threatLevel(track: track, eta: eta, miss: miss, distance: distance, confidence: confidence)

        return RadarThreatAssessment(
            id: track.id,
            track: track,
            distanceKm: distance,
            closestApproachKm: miss,
            etaMinutes: eta,
            projectedCoordinate: projected,
            confidence: confidence,
            level: level
        )
    }

    static func evaluate(nowcast: RadarNowcastFile, target: CLLocationCoordinate2D) -> [RadarThreatAssessment] {
        nowcast.tracks
            .map { evaluate(track: $0, target: target, horizonMinutes: nowcast.horizonMinutes) }
            .sorted {
                switch ($0.etaMinutes, $1.etaMinutes) {
                case let (a?, b?): return a < b
                case (_?, nil): return true
                case (nil, _?): return false
                case (nil, nil):
                    if $0.level != $1.level { return $0.level > $1.level }
                    return $0.closestApproachKm < $1.closestApproachKm
                }
            }
    }

    static func best(nowcast: RadarNowcastFile, target: CLLocationCoordinate2D) -> RadarThreatAssessment? {
        evaluate(nowcast: nowcast, target: target).first
    }

    private static func threatLevel(track: NowcastTrack, eta: Double?, miss: Double, distance: Double, confidence: Double) -> RadarThreatLevel {
        if let eta {
            if eta <= 60, track.zmaxDbz >= 36, confidence >= 0.60 { return .high }
            if eta <= 120, confidence >= 0.50 { return .approaching }
            return .possible
        }
        if miss <= track.radiusKm * 1.75, distance <= 80 { return .possible }
        if distance <= 60 { return .nearby }
        return .none
    }

    private static func offset(_ p: CLLocationCoordinate2D, eastKm: Double, northKm: Double) -> CLLocationCoordinate2D {
        let lat = p.latitude + northKm / 111.32
        let denominator = max(abs(cos(p.latitude * .pi / 180)), 0.000001)
        let lon = p.longitude + eastKm / (111.32 * denominator)
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }
}
