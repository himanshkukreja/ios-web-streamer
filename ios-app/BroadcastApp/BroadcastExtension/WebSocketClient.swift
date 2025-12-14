import Foundation
import os.log

/// WebSocket client for streaming video frames to the server.
class WebSocketClient: NSObject {

    // MARK: - Types

    typealias VoidCallback = () -> Void
    typealias ErrorCallback = (Error?) -> Void

    enum WebSocketError: Error, LocalizedError {
        case connectionFailed
        case notConnected
        case sendFailed

        var errorDescription: String? {
            switch self {
            case .connectionFailed:
                return "WebSocket connection failed"
            case .notConnected:
                return "WebSocket not connected"
            case .sendFailed:
                return "Failed to send message"
            }
        }
    }

    // MARK: - Properties

    private let logger = Logger(subsystem: "com.nativebridge.broadcast", category: "WebSocket")

    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private let url: URL

    private(set) var isConnected = false
    private var isReconnecting = false

    private let sendQueue = DispatchQueue(label: "com.nativebridge.websocket.send", qos: .userInteractive)
    private var pendingMessages: [Data] = []
    private let maxPendingMessages = 10

    // Callbacks
    var onConnect: VoidCallback?
    var onDisconnect: ErrorCallback?
    var onError: ErrorCallback?
    var onMessage: ((Data) -> Void)?

    // Heartbeat
    private var heartbeatTimer: Timer?
    private let heartbeatInterval: TimeInterval = 5.0

    // MARK: - Initialization

    init(url: String) {
        guard let url = URL(string: url) else {
            fatalError("Invalid WebSocket URL: \(url)")
        }
        self.url = url
        super.init()
    }

    deinit {
        disconnect()
    }

    // MARK: - Connection

    func connect() {
        logger.info("Connecting to \(self.url.absoluteString)")

        // Create URL session
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 10
        configuration.timeoutIntervalForResource = 60

        urlSession = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)

        // Create WebSocket task
        webSocketTask = urlSession?.webSocketTask(with: url)
        webSocketTask?.resume()

        // Start receiving messages
        receiveMessage()
    }

    func disconnect() {
        logger.info("Disconnecting")

        heartbeatTimer?.invalidate()
        heartbeatTimer = nil

        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil

        urlSession?.invalidateAndCancel()
        urlSession = nil

        isConnected = false
    }

    // MARK: - Sending

    func send(_ data: Data) {
        sendQueue.async { [weak self] in
            guard let self = self else { return }

            if self.isConnected {
                self.sendImmediately(data)
            } else {
                // Queue message if not connected (up to limit)
                if self.pendingMessages.count < self.maxPendingMessages {
                    self.pendingMessages.append(data)
                }
            }
        }
    }

    private func sendImmediately(_ data: Data) {
        let message = URLSessionWebSocketTask.Message.data(data)

        webSocketTask?.send(message) { [weak self] error in
            if let error = error {
                self?.logger.error("Send error: \(error.localizedDescription)")
                self?.handleError(error)
            }
        }
    }

    private func flushPendingMessages() {
        sendQueue.async { [weak self] in
            guard let self = self, self.isConnected else { return }

            for message in self.pendingMessages {
                self.sendImmediately(message)
            }
            self.pendingMessages.removeAll()
        }
    }

    // MARK: - Receiving

    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            guard let self = self else { return }

            switch result {
            case .success(let message):
                switch message {
                case .data(let data):
                    self.handleReceivedData(data)
                case .string(let text):
                    if let data = text.data(using: .utf8) {
                        self.handleReceivedData(data)
                    }
                @unknown default:
                    break
                }

                // Continue receiving
                self.receiveMessage()

            case .failure(let error):
                self.logger.error("Receive error: \(error.localizedDescription)")
                self.handleDisconnection(error: error)
            }
        }
    }

    private func handleReceivedData(_ data: Data) {
        // Parse message type
        guard data.count >= 1 else { return }

        let messageType = data[0]

        if messageType == Constants.MessageType.heartbeat.rawValue {
            // Heartbeat response from server
            logger.debug("Heartbeat received")
        } else {
            // Forward other messages
            onMessage?(data)
        }
    }

    // MARK: - Heartbeat

    private func startHeartbeat() {
        heartbeatTimer?.invalidate()

        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: heartbeatInterval, repeats: true) { [weak self] _ in
            self?.sendHeartbeat()
        }
    }

    private func sendHeartbeat() {
        guard isConnected else { return }

        let heartbeat = ProtocolMessage.heartbeat()
        send(heartbeat)
    }

    // MARK: - Error Handling

    private func handleError(_ error: Error) {
        onError?(error)
    }

    private func handleDisconnection(error: Error?) {
        isConnected = false
        heartbeatTimer?.invalidate()
        heartbeatTimer = nil

        onDisconnect?(error)

        // Attempt reconnection
        if !isReconnecting {
            attemptReconnection()
        }
    }

    private func attemptReconnection() {
        isReconnecting = true

        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) { [weak self] in
            guard let self = self else { return }

            self.isReconnecting = false
            self.logger.info("Attempting reconnection...")
            self.connect()
        }
    }
}

// MARK: - URLSessionWebSocketDelegate

extension WebSocketClient: URLSessionWebSocketDelegate {

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        logger.info("WebSocket connected")

        isConnected = true

        // Start heartbeat
        DispatchQueue.main.async { [weak self] in
            self?.startHeartbeat()
        }

        // Notify and flush pending messages
        onConnect?()
        flushPendingMessages()
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        let reasonString = reason.flatMap { String(data: $0, encoding: .utf8) } ?? "unknown"
        logger.info("WebSocket closed: \(closeCode.rawValue) - \(reasonString)")

        handleDisconnection(error: nil)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error {
            logger.error("WebSocket task error: \(error.localizedDescription)")
            handleDisconnection(error: error)
        }
    }
}
