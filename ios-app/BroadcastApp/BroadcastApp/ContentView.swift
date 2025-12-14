import SwiftUI
import ReplayKit

struct ContentView: View {
    @StateObject private var broadcastManager = BroadcastManager()
    @State private var serverHost = Constants.Server.host
    @State private var serverPort = String(Constants.Server.port)

    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                // Status Section
                StatusCard(isConnected: broadcastManager.isConnected,
                          isBroadcasting: broadcastManager.isBroadcasting)

                // Broadcast Picker
                VStack(spacing: 12) {
                    Text("Start Broadcast")
                        .font(.headline)
                        .foregroundColor(.secondary)

                    BroadcastPickerRepresentable()
                        .frame(width: 80, height: 80)

                    Text("Tap the circle above")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color(.systemBackground))
                .cornerRadius(16)
                .shadow(color: .black.opacity(0.1), radius: 10)

                // Server Configuration
                ServerConfigView(host: $serverHost, port: $serverPort)

                // Stats (when broadcasting)
                if broadcastManager.isBroadcasting {
                    StatsView(frameCount: broadcastManager.frameCount,
                             fps: broadcastManager.currentFPS)
                }

                Spacer()

                // Instructions
                InstructionsView()
            }
            .padding()
            .navigationTitle("Screen Streamer")
            .onAppear {
                loadSettings()
            }
            .onChange(of: serverHost) { _ in saveSettings() }
            .onChange(of: serverPort) { _ in saveSettings() }
        }
    }

    private func loadSettings() {
        if let savedHost = UserDefaults.standard.string(forKey: Constants.UserDefaultsKeys.serverHost) {
            serverHost = savedHost
        }
        if let savedPort = UserDefaults.standard.string(forKey: Constants.UserDefaultsKeys.serverPort) {
            serverPort = savedPort
        }
    }

    private func saveSettings() {
        UserDefaults.standard.set(serverHost, forKey: Constants.UserDefaultsKeys.serverHost)
        UserDefaults.standard.set(serverPort, forKey: Constants.UserDefaultsKeys.serverPort)

        // Also save to app group for extension access
        if let defaults = UserDefaults(suiteName: Constants.appGroupIdentifier) {
            defaults.set(serverHost, forKey: Constants.UserDefaultsKeys.serverHost)
            defaults.set(serverPort, forKey: Constants.UserDefaultsKeys.serverPort)
        }
    }
}

// MARK: - Status Card

struct StatusCard: View {
    let isConnected: Bool
    let isBroadcasting: Bool

    var body: some View {
        HStack(spacing: 20) {
            StatusIndicator(
                title: "Server",
                isActive: isConnected,
                activeColor: .green,
                inactiveColor: .red
            )

            Divider()
                .frame(height: 40)

            StatusIndicator(
                title: "Broadcast",
                isActive: isBroadcasting,
                activeColor: .blue,
                inactiveColor: .gray
            )
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.1), radius: 10)
    }
}

struct StatusIndicator: View {
    let title: String
    let isActive: Bool
    let activeColor: Color
    let inactiveColor: Color

    var body: some View {
        VStack(spacing: 8) {
            Circle()
                .fill(isActive ? activeColor : inactiveColor)
                .frame(width: 16, height: 16)
                .overlay(
                    Circle()
                        .stroke(isActive ? activeColor.opacity(0.3) : Color.clear, lineWidth: 4)
                        .scaleEffect(isActive ? 1.5 : 1)
                        .animation(isActive ? .easeInOut(duration: 1).repeatForever(autoreverses: true) : .default, value: isActive)
                )

            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)

            Text(isActive ? "Active" : "Inactive")
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundColor(isActive ? activeColor : inactiveColor)
        }
        .frame(minWidth: 80)
    }
}

// MARK: - Broadcast Picker

struct BroadcastPickerRepresentable: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let containerView = UIView(frame: CGRect(x: 0, y: 0, width: 80, height: 80))

        let picker = RPSystemBroadcastPickerView(frame: CGRect(x: 0, y: 0, width: 80, height: 80))

        // Set the preferred extension
        picker.preferredExtension = "com.nativebridge.broadcast.extension"

        // Show only microphone toggle if needed (we're video-only for now)
        picker.showsMicrophoneButton = false

        // Find and style the button
        for subview in picker.subviews {
            if let button = subview as? UIButton {
                button.imageView?.tintColor = .systemBlue

                // Make the button fill the picker
                button.frame = picker.bounds
                button.autoresizingMask = [.flexibleWidth, .flexibleHeight]

                // Use a large record icon
                let config = UIImage.SymbolConfiguration(pointSize: 50, weight: .regular)
                let image = UIImage(systemName: "record.circle.fill", withConfiguration: config)
                button.setImage(image, for: .normal)
                button.imageView?.contentMode = .scaleAspectFit

                // Make the button more tappable
                button.isUserInteractionEnabled = true
            }
        }

        // Make sure picker is interactive
        picker.isUserInteractionEnabled = true
        containerView.addSubview(picker)
        picker.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        containerView.isUserInteractionEnabled = true

        return containerView
    }

    func updateUIView(_ uiView: UIView, context: Context) {}
}

// Helper to programmatically trigger the broadcast picker
extension RPSystemBroadcastPickerView {
    func triggerBroadcast() {
        for subview in subviews {
            if let button = subview as? UIButton {
                button.sendActions(for: .touchUpInside)
                break
            }
        }
    }
}

// MARK: - Server Configuration

struct ServerConfigView: View {
    @Binding var host: String
    @Binding var port: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Server Configuration")
                .font(.headline)
                .foregroundColor(.secondary)

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Host")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    TextField("localhost", text: $host)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Port")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    TextField("8765", text: $port)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .keyboardType(.numberPad)
                        .frame(width: 80)
                }
            }

            Text("ws://\(host):\(port)")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.top, 4)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.1), radius: 10)
    }
}

// MARK: - Stats View

struct StatsView: View {
    let frameCount: Int
    let fps: Double

    var body: some View {
        HStack(spacing: 24) {
            VStack {
                Text("\(frameCount)")
                    .font(.title2)
                    .fontWeight(.bold)
                    .monospacedDigit()
                Text("Frames")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            VStack {
                Text(String(format: "%.1f", fps))
                    .font(.title2)
                    .fontWeight(.bold)
                    .monospacedDigit()
                Text("FPS")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: .black.opacity(0.1), radius: 10)
    }
}

// MARK: - Instructions View

struct InstructionsView: View {
    private var isSimulator: Bool {
        #if targetEnvironment(simulator)
        return true
        #else
        return false
        #endif
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if isSimulator {
                Label("Simulator Limitation", systemImage: "exclamationmark.triangle")
                    .font(.caption.bold())
                    .foregroundColor(.orange)

                Text("ReplayKit broadcast extensions don't work in the iOS Simulator. Please use a real iOS device to test screen broadcasting.\n\nTo test the server, run:\n./scripts/start-server.sh --test")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Label("How to use", systemImage: "info.circle")
                    .font(.caption.bold())
                    .foregroundColor(.secondary)

                Text("1. Make sure the Python server is running\n2. Tap the broadcast button above\n3. Select \"Screen Streamer\" from the list\n4. Confirm to start broadcasting")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }
}

// MARK: - Broadcast Manager

class BroadcastManager: ObservableObject {
    @Published var isConnected = false
    @Published var isBroadcasting = false
    @Published var frameCount = 0
    @Published var currentFPS: Double = 0

    init() {
        // Observe broadcast state from UserDefaults (set by extension)
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(checkBroadcastState),
            name: UserDefaults.didChangeNotification,
            object: nil
        )

        // Start periodic check
        Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.checkBroadcastState()
        }
    }

    @objc private func checkBroadcastState() {
        if let defaults = UserDefaults(suiteName: Constants.appGroupIdentifier) {
            DispatchQueue.main.async {
                self.isBroadcasting = defaults.bool(forKey: Constants.UserDefaultsKeys.isBroadcasting)
            }
        }
    }
}

// MARK: - Preview

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
