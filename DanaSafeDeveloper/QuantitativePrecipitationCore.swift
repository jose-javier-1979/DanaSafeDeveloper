import Foundation

enum QuantitativePrecipitationCore {

    struct Configuration: Equatable {
        let marshallPalmerA: Double
        let marshallPalmerB: Double
        let qpeCapDbz: Double
        let bandHalfWidthDbz: Double

        static let danaSafeV8 = Configuration(
            marshallPalmerA: 200.0,
            marshallPalmerB: 1.6,
            qpeCapDbz: 60.0,
            bandHalfWidthDbz: 3.0
        )
    }

    struct RainRateBand: Equatable {
        let lowerMmPerHour: Double
        let centralMmPerHour: Double
        let upperMmPerHour: Double
        let effectiveDbz: Double
    }

    struct RadarGeometry: Equatable {
        let widthPx: Double
        let heightPx: Double
        let westLongitude: Double
        let eastLongitude: Double
        let southLatitude: Double
        let northLatitude: Double

        static let aemetCompo = RadarGeometry(
            widthPx: 962.0,
            heightPx: 1079.0,
            westLongitude: -16.08,
            eastLongitude: 12.14,
            southLatitude: 27.22,
            northLatitude: 51.30
        )
    }

    private static let webMercatorEarthRadiusM = 6_378_137.0
    private static let webMercatorLatitudeLimit = 85.05112878

    static func linearReflectivity(fromDbz dbz: Double) -> Double {
        pow(10.0, dbz / 10.0)
    }

    static func rainRateMmPerHour(
        fromDbz dbz: Double,
        configuration: Configuration = .danaSafeV8
    ) -> Double {

        let effectiveDbz = min(dbz, configuration.qpeCapDbz)
        let z = linearReflectivity(fromDbz: effectiveDbz)

        return pow(
            z / configuration.marshallPalmerA,
            1.0 / configuration.marshallPalmerB
        )
    }

    static func rainRateBand(
        forDbz dbz: Double,
        configuration: Configuration = .danaSafeV8
    ) -> RainRateBand {

        let effective = min(dbz, configuration.qpeCapDbz)

        let lowerDbz = max(
            0.0,
            min(
                effective - configuration.bandHalfWidthDbz,
                configuration.qpeCapDbz
            )
        )

        let upperDbz = min(
            effective + configuration.bandHalfWidthDbz,
            configuration.qpeCapDbz
        )

        return RainRateBand(
            lowerMmPerHour: rainRateMmPerHour(
                fromDbz: lowerDbz,
                configuration: configuration
            ),
            centralMmPerHour: rainRateMmPerHour(
                fromDbz: effective,
                configuration: configuration
            ),
            upperMmPerHour: rainRateMmPerHour(
                fromDbz: upperDbz,
                configuration: configuration
            ),
            effectiveDbz: effective
        )
    }

    static func millimetres(
        rainRateMmPerHour: Double,
        durationMinutes: Double
    ) -> Double {
        rainRateMmPerHour * durationMinutes / 60.0
    }

    static func litres(
        millimetres: Double,
        areaSquareMetres: Double
    ) -> Double {
        millimetres * areaSquareMetres
    }

    static func projectedPixelSizeMetres(
        geometry: RadarGeometry = .aemetCompo
    ) -> (width: Double, height: Double) {

        let westX = mercatorX(longitudeDegrees: geometry.westLongitude)
        let eastX = mercatorX(longitudeDegrees: geometry.eastLongitude)

        let northY = mercatorY(latitudeDegrees: geometry.northLatitude)
        let southY = mercatorY(latitudeDegrees: geometry.southLatitude)

        let width = abs(eastX - westX) / geometry.widthPx
        let height = abs(northY - southY) / geometry.heightPx

        return (width, height)
    }

    static func projectedPixelAreaSquareMetres(
        geometry: RadarGeometry = .aemetCompo
    ) -> Double {

        let size = projectedPixelSizeMetres(geometry: geometry)
        return size.width * size.height
    }

    static func realGroundPixelAreaSquareMetres(
        latitudeDegrees: Double,
        geometry: RadarGeometry = .aemetCompo
    ) -> Double {

        let latitude = max(
            -webMercatorLatitudeLimit,
            min(webMercatorLatitudeLimit, latitudeDegrees)
        )

        let projectedArea = projectedPixelAreaSquareMetres(
            geometry: geometry
        )

        let scaleCorrection = pow(
            cos(latitude * .pi / 180.0),
            2.0
        )

        return projectedArea * scaleCorrection
    }

    static func realGroundPixelAreaKm2(
        latitudeDegrees: Double,
        geometry: RadarGeometry = .aemetCompo
    ) -> Double {

        realGroundPixelAreaSquareMetres(
            latitudeDegrees: latitudeDegrees,
            geometry: geometry
        ) / 1_000_000.0
    }

    static func litresPerRadarPixel(
        millimetres: Double,
        latitudeDegrees: Double,
        geometry: RadarGeometry = .aemetCompo
    ) -> Double {

        litres(
            millimetres: millimetres,
            areaSquareMetres: realGroundPixelAreaSquareMetres(
                latitudeDegrees: latitudeDegrees,
                geometry: geometry
            )
        )
    }

    private static func mercatorX(
        longitudeDegrees: Double
    ) -> Double {

        webMercatorEarthRadiusM *
        longitudeDegrees *
        .pi / 180.0
    }

    private static func mercatorY(
        latitudeDegrees: Double
    ) -> Double {

        let latitude = max(
            -webMercatorLatitudeLimit,
            min(webMercatorLatitudeLimit, latitudeDegrees)
        )

        let phi = latitude * .pi / 180.0

        return webMercatorEarthRadiusM *
        log(
            tan(
                .pi / 4.0 + phi / 2.0
            )
        )
    }
}
