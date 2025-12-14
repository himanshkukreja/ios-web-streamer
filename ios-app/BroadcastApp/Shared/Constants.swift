import Foundation

/// Shared constants between main app and broadcast extension
enum Constants {
    /// WebSocket server configuration
    enum Server {
        // Use your Mac's local IP for physical device, localhost for simulator
        #if targetEnvironment(simulator)
        static let host = "localhost"
        #else
        static let host = "192.168.1.10"  // Your Mac's local IP
        #endif
        static let port = 8765
        static let url = "ws://\(host):\(port)"
    }

    /// App Group identifier for shared data
    static let appGroupIdentifier = "group.com.nativebridge.broadcast"

    /// Video encoding settings
    enum Video {
        static let defaultWidth = 1080
        static let defaultHeight = 1920
        static let defaultFPS = 30
        static let defaultBitrate = 2_000_000 // 2 Mbps
        static let keyframeInterval = 60 // frames (2 seconds at 30fps)
    }

    /// Message types for WebSocket protocol
    enum MessageType: UInt8 {
        case videoFrame = 0x01
        case config = 0x02
        case heartbeat = 0x03
        case stats = 0x04
        case endStream = 0xFF
    }

    /// UserDefaults keys
    enum UserDefaultsKeys {
        static let serverHost = "serverHost"
        static let serverPort = "serverPort"
        static let videoBitrate = "videoBitrate"
        static let isBroadcasting = "isBroadcasting"
        static let isServerConnected = "isServerConnected"
    }
}
