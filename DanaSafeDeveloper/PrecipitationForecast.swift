import Foundation
import CoreLocation

struct PrecipitationAccumulation: Identifiable {
    let minutes: Int

    let lowerMm: Double
    let centralMm: Double
    let upperMm: Double

    let lowerLitresPerCell: Double
    let centralLitresPerCell: Double
    let upperLitresPerCell: Double

    var id: Int { minutes }
}

struct LocalPrecipitationForecast {
    let trackId: String
    let systemId: String

    let cellAreaKm2: Double
    let confidence: Double

    let peakDbz: Int?
    let peakRainRateMmPerHour: Double

    let accumulations: [PrecipitationAccumulation]

    func accumulation(minutes: Int) -> PrecipitationAccumulation? {
        accumulations.first { $0.minutes == minutes }
    }
}

enum PrecipitationForecast {

    private static let earthRadiusKm = 6_371.0088
    private static let kilometresPerLatitudeDegree = 111.32

    static func build(
        track: NowcastTrack,
        radarFrames: [RadarFrame],
        userCoordinate: CLLocationCoordinate2D
    ) -> LocalPrecipitationForecast? {

        guard let latestSystem = findLatestSystem(
            systemId: track.latestSystemId,
            in: radarFrames
        ) else {
            return nil
        }

        let cellAreaKm2 =
            QuantitativePrecipitationCore
            .realGroundPixelAreaKm2(
                latitudeDegrees: userCoordinate.latitude
            )

        let nestedLevels = monotonicLevels(
            for: latestSystem
        )

        guard !nestedLevels.isEmpty else {
            return nil
        }

        var accumulatedLowerMm = 0.0
        var accumulatedCentralMm = 0.0
        var accumulatedUpperMm = 0.0

        var peakDbz: Int?
        var peakRate = 0.0

        var outputs: [PrecipitationAccumulation] = []

        /*
         Each iteration represents one one-minute integration interval.

         minute = 0 means the interval [0,1 min),
         minute = 1 means [1,2 min), etc.

         Therefore after minute 9 we have integrated 10 minutes.
        */
        for minute in 0..<60 {

            let hours = Double(minute) / 60.0

            let projectedCenter = offset(
                coordinate: track.latestCoordinate.clLocationCoordinate,
                eastKm: track.motion.velocityEastKmh * hours,
                northKm: track.motion.velocityNorthKmh * hours
            )

            let distanceKm = haversineKm(
                from: projectedCenter,
                to: userCoordinate
            )

            if let dbz = highestLevelContaining(
                distanceKm: distanceKm,
                nestedLevels: nestedLevels,
                cellAreaKm2: cellAreaKm2
            ) {
                let band =
                    QuantitativePrecipitationCore
                    .rainRateBand(
                        forDbz: Double(dbz)
                    )

                accumulatedLowerMm +=
                    band.lowerMmPerHour / 60.0

                accumulatedCentralMm +=
                    band.centralMmPerHour / 60.0

                accumulatedUpperMm +=
                    band.upperMmPerHour / 60.0

                if let currentPeak = peakDbz {
                    if dbz > currentPeak {
                        peakDbz = dbz
                    }
                } else {
                    peakDbz = dbz
                }

                peakRate = max(
                    peakRate,
                    band.centralMmPerHour
                )
            }

            let elapsedMinutes = minute + 1

            if elapsedMinutes == 10 ||
               elapsedMinutes == 30 ||
               elapsedMinutes == 60 {

                let areaM2 = cellAreaKm2 * 1_000_000.0

                outputs.append(
                    PrecipitationAccumulation(
                        minutes: elapsedMinutes,

                        lowerMm: accumulatedLowerMm,
                        centralMm: accumulatedCentralMm,
                        upperMm: accumulatedUpperMm,

                        lowerLitresPerCell:
                            QuantitativePrecipitationCore.litres(
                                millimetres: accumulatedLowerMm,
                                areaSquareMetres: areaM2
                            ),

                        centralLitresPerCell:
                            QuantitativePrecipitationCore.litres(
                                millimetres: accumulatedCentralMm,
                                areaSquareMetres: areaM2
                            ),

                        upperLitresPerCell:
                            QuantitativePrecipitationCore.litres(
                                millimetres: accumulatedUpperMm,
                                areaSquareMetres: areaM2
                            )
                    )
                )
            }
        }

        return LocalPrecipitationForecast(
            trackId: track.id,
            systemId: latestSystem.id,
            cellAreaKm2: cellAreaKm2,
            confidence: track.confidence,
            peakDbz: peakDbz,
            peakRainRateMmPerHour: peakRate,
            accumulations: outputs
        )
    }

    // MARK: - Nested dBZ geometry

    private struct NestedLevel {
        let dbz: Int
        let areaPx: Int
    }

    /*
     Radar levels should be nested physically:

       A12 >= A18 >= A24 >= ...

     The historical audit found one real case where component association
     broke this property. We repair it only in the QPE geometry and do not
     modify the baseline radar product.
    */
    private static func monotonicLevels(
        for system: RadarSystem
    ) -> [NestedLevel] {

        var raw: [(dbz: Int, areaPx: Int)] =
            system.levels.compactMap { key, value in
                guard let dbz = Int(key) else {
                    return nil
                }

                return (
                    dbz: dbz,
                    areaPx: max(value.areaPx, 0)
                )
            }

        if !raw.contains(where: {
            $0.dbz == system.rootLevelDbz
        }) {
            raw.append(
                (
                    dbz: system.rootLevelDbz,
                    areaPx: max(system.rootAreaPx, 0)
                )
            )
        }

        raw.sort {
            $0.dbz < $1.dbz
        }

        var previousArea = Int.max
        var result: [NestedLevel] = []

        for level in raw {

            let correctedArea =
                min(level.areaPx, previousArea)

            guard correctedArea > 0 else {
                continue
            }

            result.append(
                NestedLevel(
                    dbz: level.dbz,
                    areaPx: correctedArea
                )
            )

            previousArea = correctedArea
        }

        return result
    }

    private static func highestLevelContaining(
        distanceKm: Double,
        nestedLevels: [NestedLevel],
        cellAreaKm2: Double
    ) -> Int? {

        /*
         Each nested radar area is represented by an equivalent circle:

             area = pi * radius^2

         We test from highest dBZ downward so nested levels are not added
         together. The user receives the intensity of the strongest level
         containing their location.
        */

        for level in nestedLevels.reversed() {

            let areaKm2 =
                Double(level.areaPx) * cellAreaKm2

            let radiusKm =
                sqrt(areaKm2 / .pi)

            if distanceKm <= radiusKm {
                return level.dbz
            }
        }

        return nil
    }

    // MARK: - System lookup

    private static func findLatestSystem(
        systemId: String,
        in frames: [RadarFrame]
    ) -> RadarSystem? {

        for frame in frames.sorted(
            by: { $0.frame > $1.frame }
        ) {
            if let system = frame.systems.first(
                where: { $0.id == systemId }
            ) {
                return system
            }
        }

        return nil
    }

    // MARK: - Motion geometry

    private static func offset(
        coordinate: CLLocationCoordinate2D,
        eastKm: Double,
        northKm: Double
    ) -> CLLocationCoordinate2D {

        let latitudeDelta =
            northKm / kilometresPerLatitudeDegree

        let latitudeRadians =
            coordinate.latitude * .pi / 180.0

        let longitudeScale =
            kilometresPerLatitudeDegree *
            max(cos(latitudeRadians), 0.01)

        let longitudeDelta =
            eastKm / longitudeScale

        return CLLocationCoordinate2D(
            latitude:
                coordinate.latitude + latitudeDelta,
            longitude:
                coordinate.longitude + longitudeDelta
        )
    }

    private static func haversineKm(
        from a: CLLocationCoordinate2D,
        to b: CLLocationCoordinate2D
    ) -> Double {

        let lat1 = a.latitude * .pi / 180.0
        let lat2 = b.latitude * .pi / 180.0

        let deltaLat =
            (b.latitude - a.latitude) *
            .pi / 180.0

        let deltaLon =
            (b.longitude - a.longitude) *
            .pi / 180.0

        let h =
            pow(sin(deltaLat / 2.0), 2.0)
            +
            cos(lat1) *
            cos(lat2) *
            pow(sin(deltaLon / 2.0), 2.0)

        return 2.0 *
            earthRadiusKm *
            atan2(
                sqrt(h),
                sqrt(max(0.0, 1.0 - h))
            )
    }
}
