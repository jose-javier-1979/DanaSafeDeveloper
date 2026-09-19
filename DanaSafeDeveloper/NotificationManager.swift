import Foundation
import UserNotifications
import Combine

@MainActor
final class DanaSafeNotificationManager: ObservableObject {
    @Published private(set) var authorizationStatus: UNAuthorizationStatus = .notDetermined

    func refreshAuthorizationStatus() async {
        authorizationStatus = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    func requestAuthorization() async -> Bool {
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])
            await refreshAuthorizationStatus()
            return granted
        } catch {
            await refreshAuthorizationStatus()
            return false
        }
    }

    func notifyIfNeeded(_ assessment: RadarThreatAssessment, radarTimestamp: String) async {
        guard assessment.level >= .approaching,
              let eta = assessment.etaMinutes,
              eta <= 120,
              assessment.confidence >= 0.50 else { return }

        let settings = await UNUserNotificationCenter.current().notificationSettings()
        guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else { return }

        let content = UNMutableNotificationContent()
        content.title = assessment.level.title
        content.body = "Sistema radar a \(Int(assessment.distanceKm.rounded())) km. ETA ~\(Int(eta.rounded())) min · \(assessment.track.zmaxDbz) dBZ · confianza \(Int((assessment.confidence * 100).rounded()))%."
        content.sound = .default
        content.userInfo = ["track_id": assessment.track.id, "radar_timestamp": radarTimestamp]

        // Stable identifier provides de-duplication for the same track/radar cycle.
        let identifier = "danasafe-v81-\(radarTimestamp)-\(assessment.track.id)"
        let request = UNNotificationRequest(identifier: identifier, content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }
}
