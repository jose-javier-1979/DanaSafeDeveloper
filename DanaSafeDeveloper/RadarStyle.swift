import SwiftUI

func radarColor(_ dbz: Int) -> Color {
    switch dbz {
    case 72...: return Color(red: 200/255, green: 0, blue: 90/255)
    case 66..<72: return .red
    case 60..<66: return .orange
    case 54..<60: return Color(red: 1, green: 187/255, blue: 0)
    case 48..<54: return .yellow
    case 42..<48: return .green
    case 36..<42: return Color(red: 0, green: 192/255, blue: 0)
    case 30..<36: return Color(red: 67/255, green: 131/255, blue: 35/255)
    case 24..<30: return .cyan
    case 18..<24: return Color(red: 0, green: 148/255, blue: 252/255)
    default: return .blue
    }
}

func radarMarkerSize(_ area: Int) -> CGFloat {
    switch area {
    case 200...: return 34
    case 100..<200: return 30
    case 40..<100: return 26
    case 20..<40: return 23
    default: return 20
    }
}
