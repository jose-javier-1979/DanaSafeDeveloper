import Foundation
import Testing
@testable import DanaSafeDeveloper

struct DanaSafeDeveloperTests {
    @Test func quantitativePrecipitationFingerprints() throws {
        let area = QuantitativePrecipitationCore.realGroundPixelAreaKm2(latitudeDegrees: 38.866956)
        let rate48 = QuantitativePrecipitationCore.rainRateMmPerHour(fromDbz: 48)
        let capped72 = QuantitativePrecipitationCore.rainRateMmPerHour(fromDbz: 72)
        #expect(abs(area - 6.464672) < 0.001)
        #expect(abs(rate48 - 36.463324) < 0.001)
        #expect(abs(capped72 - 205.048338) < 0.001)
    }

    @Test func canonicalNowcastFixture() throws {
        let url = try #require(Bundle.main.url(forResource: "radar_systems_v03", withExtension: "json"))
        let data = try Data(contentsOf: url)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let radar = try decoder.decode(RadarSystemsFile.self, from: data)
        let nowcast = try #require(NowcastBuilderV7.build(from: radar))
        #expect(nowcast.trackCount == 9)
        let t004 = try #require(nowcast.tracks.first { $0.id == "T004" })
        #expect(t004.latestSystemId == "F10_SYS_013")
        #expect(t004.zmaxDbz == 42)
        let forecast = try #require(PrecipitationForecast.build(track: t004, radarFrames: radar.frames, userCoordinate: t004.latestCoordinate.clLocationCoordinate))
        #expect(abs(forecast.cellAreaKm2 - 6.765497) < 0.001)
        #expect(forecast.accumulations.map(\.minutes) == [10, 30, 60])
    }
}
