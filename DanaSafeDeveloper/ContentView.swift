import SwiftUI
import MapKit

struct ContentView: View {
    @StateObject private var model = DanaSafeModel()
    @StateObject private var locationService = LocationService()
    @StateObject private var searchService = SearchService()
    @StateObject private var notificationManager = DanaSafeNotificationManager()

    var body: some View {
        TabView {
            RadarMapView(model: model, locationService: locationService, searchService: searchService)
                .tabItem { Label("Radar", systemImage: "cloud.rain") }

            NowcastView(model: model, locationService: locationService, notificationManager: notificationManager)
                .tabItem { Label("Ahora", systemImage: "location.north.line") }

            SystemsView(model: model)
                .tabItem { Label("Systems", systemImage: "dot.radiowaves.left.and.right") }

            HydrologyView(model: model)
                .tabItem { Label("Hydrology", systemImage: "drop") }

            ToolsView(model: model)
                .tabItem { Label("Tools", systemImage: "wrench.and.screwdriver") }
        }
        .task {
            model.loadBundled()
            if !ProcessInfo.processInfo.arguments.contains("--ui-testing") {
                await model.loadFromCloudflare()
            }
        }
    }
}

struct RadarMapView: View {
    @ObservedObject var model: DanaSafeModel
    @ObservedObject var locationService: LocationService
    @ObservedObject var searchService: SearchService

    @State private var position: MapCameraPosition = .region(
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 39.5, longitude: -3.7),
            span: MKCoordinateSpan(latitudeDelta: 12.5, longitudeDelta: 16.5)
        )
    )
    @State private var selectedSystem: RadarSystem?
    @State private var showTracks = false
    @State private var showContours = false
    @State private var showNowcast = true
    @State private var contourLevel = 36

    var body: some View {
        NavigationStack {
            ZStack(alignment: .top) {
                Map(position: $position) {
                    if showContours, let contourFile = model.contoursFile,
                       let level = contourFile.levels.first(where: { $0.levelDbz == contourLevel }) {
                        ForEach(Array(level.contours.prefix(200))) { contour in
                            if contour.mapCoordinates.count >= 2 {
                                MapPolyline(coordinates: contour.mapCoordinates)
                                    .stroke(radarColor(contour.levelDbz).opacity(0.65), lineWidth: 1.5)
                            }
                        }
                    }

                    if showTracks {
                        ForEach(Array(model.tracks.prefix(80))) { track in
                            MapPolyline(coordinates: [track.start.centroid.clLocationCoordinate, track.end.centroid.clLocationCoordinate])
                                .stroke(radarColor(track.levelDbz).opacity(0.7), style: StrokeStyle(lineWidth: 1.5, dash: [5, 3]))
                        }
                    }

                    if showNowcast, let nowcast = model.nowcast {
                        ForEach(Array(nowcast.tracks.prefix(40))) { track in
                            let coordinates = [track.latestCoordinate.clLocationCoordinate] + track.forecast.map { $0.coordinate.clLocationCoordinate }
                            MapPolyline(coordinates: coordinates)
                                .stroke(radarColor(track.zmaxDbz).opacity(0.85), style: StrokeStyle(lineWidth: 2.2, dash: [8, 4]))
                        }
                    }

                    ForEach(model.displayedSystems) { system in
                        Annotation("S\(system.rank)", coordinate: system.centroid.clLocationCoordinate, anchor: .center) {
                            Button {
                                selectedSystem = system
                            } label: {
                                RadarMarker(system: system)
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    UserAnnotation()
                }
                .mapStyle(.standard(elevation: .realistic))
                .mapControls {
                    MapCompass()
                    MapScaleView()
                    MapPitchToggle()
                    MapUserLocationButton()
                }

                statusCard
                    .padding(.horizontal)
                    .padding(.top, 8)
            }
            .navigationTitle("DanaSafe")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $searchService.query, prompt: "Search city, address or place")
            .onSubmit(of: .search) {
                Task {
                    await searchService.search()
                    if let coordinate = searchService.result?.placemark.coordinate {
                        position = .region(MKCoordinateRegion(center: coordinate, span: MKCoordinateSpan(latitudeDelta: 0.35, longitudeDelta: 0.35)))
                    }
                }
            }
            .onChange(of: locationService.location) { _, newLocation in
                guard let coordinate = newLocation?.coordinate else { return }
                position = .region(MKCoordinateRegion(center: coordinate, span: MKCoordinateSpan(latitudeDelta: 0.5, longitudeDelta: 0.5)))
            }
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button {
                        Task {
                            await model.refreshFromCloudflare()
                        }
                    } label: {
                        if model.isRefreshing {
                            ProgressView()
                                .controlSize(.small)
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                    .disabled(model.isRefreshing)
                    .accessibilityLabel("Actualizar radar desde Cloudflare y AEMET")

                    Button {
                        locationService.requestLocation()
                        if let coordinate = locationService.location?.coordinate {
                            position = .region(MKCoordinateRegion(center: coordinate, span: MKCoordinateSpan(latitudeDelta: 0.5, longitudeDelta: 0.5)))
                        }
                    } label: {
                        Image(systemName: "location")
                    }

                    Menu {
                        Toggle("Reliable tracks", isOn: $showTracks)
                        Toggle("Nowcast trajectory", isOn: $showNowcast)
                        Toggle("Marching Squares contours", isOn: $showContours)
                        Toggle("Significant only", isOn: $model.showSignificantOnly)
                        Picker("Contour dBZ", selection: $contourLevel) {
                            ForEach(model.contourLevels, id: \.self) { level in
                                Text("\(level) dBZ").tag(level)
                            }
                        }
                    } label: {
                        Image(systemName: "square.3.layers.3d")
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                timelineControl
                    .background(.ultraThinMaterial)
            }
            .sheet(item: $selectedSystem) { system in
                SystemDetailView(system: system)
                    .presentationDetents([.medium, .large])
            }
        }
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Radar AEMET · COMPO")
                        .font(.caption.bold())
                    Text(model.selectedFrame?.timestamp ?? "No radar frame")
                        .font(.caption2.monospacedDigit())
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(model.displayedSystems.count) shown")
                        .font(.caption.bold())
                    Text("\(model.significantCount) significant")
                        .font(.caption2)
                }
            }
            HStack(spacing: 6) {
                Circle().fill(model.radarIsFresh && !model.dataSource.contains("Bundled") ? Color.green : Color.orange).frame(width: 7, height: 7)
                Text("\(model.freshnessText) · \(model.dataSource)")
                    .font(.caption2)
                Spacer()
                if let error = model.errorMessage {
                    Text(error).font(.caption2).foregroundStyle(.red).lineLimit(1)
                }
            }
        }
        .padding(12)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private var timelineControl: some View {
        VStack(spacing: 5) {
            HStack {
                Text("Frame")
                Spacer()
                Text(model.selectedFrame?.timestamp ?? "—").monospacedDigit()
            }
            .font(.caption2)
            if model.frames.count > 1 {
                Slider(
                    value: Binding(
                        get: { Double(model.selectedFrameIndex) },
                        set: { model.selectedFrameIndex = Int($0.rounded()) }
                    ),
                    in: 0...Double(model.frames.count - 1),
                    step: 1
                )
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }
}

struct RadarMarker: View {
    let system: RadarSystem

    var body: some View {
        VStack(spacing: 1) {
            ZStack {
                Circle()
                    .fill(radarColor(system.zmaxDbz))
                    .frame(width: radarMarkerSize(system.rootAreaPx), height: radarMarkerSize(system.rootAreaPx))
                Circle()
                    .stroke(.white, lineWidth: 2)
                    .frame(width: radarMarkerSize(system.rootAreaPx), height: radarMarkerSize(system.rootAreaPx))
                Text("\(system.zmaxDbz)")
                    .font(.system(size: 9, weight: .bold, design: .rounded))
                    .foregroundStyle(.black)
            }
            Text("S\(system.rank)")
                .font(.system(size: 8, weight: .semibold))
                .padding(.horizontal, 3)
                .background(.thinMaterial)
                .clipShape(Capsule())
        }
    }
}

struct SystemDetailView: View {
    let system: RadarSystem

    var body: some View {
        NavigationStack {
            List {
                Section("Identity") {
                    LabeledContent("ID", value: system.id)
                    LabeledContent("Rank", value: "S\(system.rank)")
                    LabeledContent("Timestamp", value: system.timestamp)
                }
                Section("Radar physics") {
                    LabeledContent("Root", value: "\(system.rootLevelDbz) dBZ")
                    LabeledContent("Root area", value: "\(system.rootAreaPx) px")
                    LabeledContent("Zmax", value: "\(system.zmaxDbz) dBZ")
                    LabeledContent("Significant", value: system.isSignificant ? "Yes" : "No")
                }
                Section("Centroid") {
                    LabeledContent("Latitude", value: String(format: "%.6f", system.centroid.latitude))
                    LabeledContent("Longitude", value: String(format: "%.6f", system.centroid.longitude))
                }
                Section("Nested dBZ levels") {
                    ForEach(system.levels.keys.sorted(by: { Int($0)! < Int($1)! }), id: \.self) { level in
                        if let value = system.levels[level] {
                            LabeledContent("\(level) dBZ", value: "\(value.areaPx) px · \(value.componentCount) comp")
                        }
                    }
                }
            }
            .navigationTitle("Radar system S\(system.rank)")
        }
    }
}

struct SystemsView: View {
    @ObservedObject var model: DanaSafeModel

    var body: some View {
        NavigationStack {
            List(model.displayedSystems) { system in
                NavigationLink {
                    SystemDetailView(system: system)
                } label: {
                    HStack {
                        Circle().fill(radarColor(system.zmaxDbz)).frame(width: 14, height: 14)
                        VStack(alignment: .leading) {
                            Text("S\(system.rank) · \(system.zmaxDbz) dBZ")
                                .font(.headline)
                            Text("A12 \(system.rootAreaPx) px · \(String(format: "%.3f", system.centroid.latitude)), \(String(format: "%.3f", system.centroid.longitude))")
                                .font(.caption)
                        }
                        Spacer()
                        if system.isSignificant {
                            Text("SIG").font(.caption2.bold()).padding(4).background(.yellow.opacity(0.25)).clipShape(Capsule())
                        }
                    }
                }
            }
            .navigationTitle("Radar systems")
            .toolbar {
                Toggle("Significant", isOn: $model.showSignificantOnly)
            }
        }
    }
}

struct HydrologyView: View {
    @ObservedObject var model: DanaSafeModel
    @State private var query = ""

    var filtered: [SAIHStation] {
        guard let stations = model.hydrology?.stations else { return [] }
        if query.isEmpty { return stations }
        return stations.filter { $0.station.localizedCaseInsensitiveContains(query) || $0.variable.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationStack {
            List(filtered) { station in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(station.station).font(.headline)
                        Spacer()
                        Text(station.status.uppercased())
                            .font(.caption2.bold())
                            .foregroundStyle(station.status == "ok" ? .green : .orange)
                    }
                    Text(station.variable).font(.caption)
                    if let flow = station.flowM3s {
                        Text(String(format: "%.2f m³/s", flow)).font(.body.monospacedDigit())
                    }
                    Text("SAIH-CHJ · observed data").font(.caption2).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Hydrology")
            .searchable(text: $query, prompt: "Search station or variable")
        }
    }
}

struct ToolsView: View {
    @ObservedObject var model: DanaSafeModel

    var body: some View {
        NavigationStack {
            Form {
                Section("Production backend · validated") {
                    LabeledContent("Endpoint", value: "danasafe-radar.firefritz.workers.dev")
                    LabeledContent("Worker", value: model.cloudflareHealth)
                    if let version = model.cloudflareVersion {
                        LabeledContent("Worker version", value: version)
                    }
                    LabeledContent("AEMET", value: model.latestAEMETInfo)
                    LabeledContent("R2 histórico", value: model.historyStatus)
                    Button("Comprobar Cloudflare + AEMET") {
                        Task { await model.checkCloudflare() }
                    }
                    .accessibilityIdentifier("tools.healthCheck")
                    Button {
                        Task { await model.refreshFromCloudflare() }
                    } label: {
                        HStack {
                            Text("Actualizar radar desde Cloudflare")
                            if model.isRefreshing {
                                Spacer()
                                ProgressView().controlSize(.small)
                            }
                        }
                    }
                    .disabled(model.isRefreshing)
                    .accessibilityIdentifier("tools.refresh")
                }

                Section("Runtime isolation") {
                    LabeledContent("Runtime", value: "Cloudflare HTTPS only")
                    LabeledContent("Local service", value: "DISABLED")
                    Text("DanaSafe 8.2 does not contact the Mac developer server. It keeps the validated production Cloudflare endpoint from 6.4 and computes Nowcast locally when the Worker snapshot has no nowcast block.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }


                Section("Current data") {
                    LabeledContent("Source", value: model.dataSource)
                    LabeledContent("Frames", value: "\(model.frames.count)")
                    LabeledContent("Selected frame", value: model.selectedFrame?.timestamp ?? "—")
                    LabeledContent("Freshness", value: model.freshnessText)
                    LabeledContent("Systems", value: "\(model.selectedFrame?.systems.count ?? 0)")
                    LabeledContent("Significant", value: "\(model.significantCount)")
                    LabeledContent("Reliable tracks", value: "\(model.tracks.count)")
                    LabeledContent("Contour levels", value: "\(model.contourLevels.count)")
                    LabeledContent("SAIH stations", value: "\(model.hydrology?.stations.count ?? 0)")
                    LabeledContent("Nowcast tracks", value: "\(model.nowcast?.trackCount ?? 0)")
                    LabeledContent("Refresh", value: model.refreshProgress)
                }

                Section("Recovered radar algorithm") {
                    Text("RGB → dBZ → zgrid → 8-neighbour connected components → Z≥12 roots → 2 px root dilation → nested dBZ components → rank → significance filter")
                    LabeledContent("Root threshold", value: "12 dBZ")
                    LabeledContent("Minimum root", value: "8 px")
                    LabeledContent("Association dilation", value: "2 px")
                    LabeledContent("Significant", value: "A12 ≥ 20 px OR Zmax ≥ 36 dBZ")
                    Text("Levels: 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72 dBZ")
                        .font(.caption)
                }

                Section("Uso responsable y privacidad") {
                    Text("DanaSafe ofrece estimaciones orientativas basadas en radar, nowcast, QPE e hidrología observada. No sustituye los avisos oficiales de AEMET, Protección Civil, 112 ni las indicaciones de los servicios de emergencia.")
                    Text("La ausencia de una alerta en DanaSafe no garantiza ausencia de riesgo meteorológico o de inundación. Ante una emergencia, sigue siempre las instrucciones oficiales.")
                    Text("La ubicación usada para ETA, paso mínimo y precipitación prevista se procesa localmente en el iPhone y no se envía al Worker de DanaSafe.")
                    Text("Los datos SAIH tienen su propia marca temporal y pueden no estar sincronizados con el ciclo radar.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Version 8.2 data contract") {
                    Text("Cloudflare HTTPS is the only network path. DanaSafe 8.2 keeps the validated production endpoint unchanged; the live Worker version is reported dynamically above.")
                        .font(.caption)
                    Text("8.2 validated-backend mode: POST /radar/refresh accepts the current synchronous 200 snapshot and retains compatibility with a 202 queued response followed by /radar/refresh-status. Before LIVE advances, the Worker archives the atomic snapshot, manifest and the ten raw AEMET frames in R2 and verifies their existence. If the Worker does not publish nowcast, DanaSafe derives it from the same ten live radar frames on-device.")
                        .font(.caption)
                }
            }
            .navigationTitle("DanaSafe Tools")
        }
    }
}
