import MapKit
import Foundation
import Combine

@MainActor
final class SearchService: ObservableObject {
    @Published var query = ""
    @Published var result: MKMapItem?
    @Published var errorMessage: String?

    func search() async {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = text
        request.resultTypes = [.address, .pointOfInterest]
        do {
            let response = try await MKLocalSearch(request: request).start()
            result = response.mapItems.first
            errorMessage = result == nil ? "No results" : nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
