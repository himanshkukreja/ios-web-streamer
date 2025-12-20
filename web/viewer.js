/**
 * iOS Simulator Stream Viewer
 *
 * WebRTC client for receiving and displaying iOS simulator video stream.
 * Includes device control via WebDriverAgent.
 */

/**
 * Device Controller - handles touch/gesture events and sends to server
 */
class DeviceController {
    constructor(videoElement, statusCallback) {
        this.video = videoElement;
        this.statusCallback = statusCallback;
        this.ws = null;
        this.isConnected = false;
        this.wdaConnected = false;
        this.deviceInfo = null;

        // Touch state tracking
        this.touchStartTime = 0;
        this.touchStartPos = { x: 0, y: 0 };
        this.isTouching = false;
        this.longPressTimer = null;
        this.longPressThreshold = 500; // ms
        this.tapThreshold = 200; // ms for distinguishing tap from hold
        this.swipeThreshold = 30; // pixels

        // Double-tap detection
        this.lastTapTime = 0;
        this.doubleTapThreshold = 300; // ms

        // Keyboard input
        this.keyboardVisible = false;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/control`;

        console.log('Connecting to control WebSocket:', wsUrl);

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('Control WebSocket connected');
            this.isConnected = true;
            this.updateStatus();
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (e) {
                console.error('Error parsing control message:', e);
            }
        };

        this.ws.onclose = () => {
            console.log('Control WebSocket disconnected');
            this.isConnected = false;
            this.wdaConnected = false;
            this.updateStatus();

            // Auto-reconnect after delay
            setTimeout(() => this.connect(), 3000);
        };

        this.ws.onerror = (error) => {
            console.error('Control WebSocket error:', error);
        };
    }

    handleMessage(data) {
        switch (data.type) {
            case 'status':
                this.wdaConnected = data.wdaConnected;
                this.deviceInfo = data.deviceInfo;
                this.updateStatus();
                console.log('WDA Status:', data);
                break;
            case 'result':
                if (!data.success) {
                    console.warn('Command failed:', data.command);
                }
                break;
            case 'error':
                console.error('Control error:', data.error, 'for command:', data.command);
                break;
        }
    }

    updateStatus() {
        if (this.statusCallback) {
            this.statusCallback({
                connected: this.isConnected,
                wdaConnected: this.wdaConnected,
                deviceInfo: this.deviceInfo
            });
        }
    }

    setupEventListeners() {
        const container = document.getElementById('video-container');

        // Mouse events (for desktop)
        container.addEventListener('mousedown', (e) => this.handlePointerStart(e));
        container.addEventListener('mousemove', (e) => this.handlePointerMove(e));
        container.addEventListener('mouseup', (e) => this.handlePointerEnd(e));
        container.addEventListener('mouseleave', (e) => this.handlePointerEnd(e));

        // Touch events (for mobile/tablet)
        container.addEventListener('touchstart', (e) => this.handleTouchStart(e), { passive: false });
        container.addEventListener('touchmove', (e) => this.handleTouchMove(e), { passive: false });
        container.addEventListener('touchend', (e) => this.handleTouchEnd(e), { passive: false });
        container.addEventListener('touchcancel', (e) => this.handlePointerEnd(e));

        // Prevent context menu on long press
        container.addEventListener('contextmenu', (e) => e.preventDefault());

        // Scroll/wheel for scrolling
        container.addEventListener('wheel', (e) => this.handleWheel(e), { passive: false });
    }

    getVideoCoordinates(clientX, clientY) {
        const rect = this.video.getBoundingClientRect();

        // Calculate position relative to video element
        const x = clientX - rect.left;
        const y = clientY - rect.top;

        // Get actual video dimensions (displayed size)
        const videoWidth = rect.width;
        const videoHeight = rect.height;

        return { x: Math.round(x), y: Math.round(y), videoWidth: Math.round(videoWidth), videoHeight: Math.round(videoHeight) };
    }

    handleTouchStart(e) {
        e.preventDefault();
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            this.handlePointerStart({ clientX: touch.clientX, clientY: touch.clientY });
        }
    }

    handleTouchMove(e) {
        e.preventDefault();
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            this.handlePointerMove({ clientX: touch.clientX, clientY: touch.clientY });
        }
    }

    handleTouchEnd(e) {
        e.preventDefault();
        if (e.changedTouches.length === 1) {
            const touch = e.changedTouches[0];
            this.handlePointerEnd({ clientX: touch.clientX, clientY: touch.clientY });
        }
    }

    handlePointerStart(e) {
        if (!this.isConnected || !this.wdaConnected) return;

        const coords = this.getVideoCoordinates(e.clientX, e.clientY);

        this.isTouching = true;
        this.touchStartTime = Date.now();
        this.touchStartPos = coords;
        this.currentPos = coords;

        // Start long press timer
        this.longPressTimer = setTimeout(() => {
            if (this.isTouching) {
                // Long press detected
                this.sendCommand({
                    type: 'longpress',
                    x: this.touchStartPos.x,
                    y: this.touchStartPos.y,
                    duration: 1000,
                    videoWidth: this.touchStartPos.videoWidth,
                    videoHeight: this.touchStartPos.videoHeight
                });
                this.isTouching = false; // Prevent tap on release
            }
        }, this.longPressThreshold);
    }

    handlePointerMove(e) {
        if (!this.isTouching) return;

        const coords = this.getVideoCoordinates(e.clientX, e.clientY);
        this.currentPos = coords;

        // Check if moved enough to cancel long press
        const dx = coords.x - this.touchStartPos.x;
        const dy = coords.y - this.touchStartPos.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance > this.swipeThreshold && this.longPressTimer) {
            clearTimeout(this.longPressTimer);
            this.longPressTimer = null;
        }
    }

    handlePointerEnd(e) {
        if (!this.isTouching) return;

        // Clear long press timer
        if (this.longPressTimer) {
            clearTimeout(this.longPressTimer);
            this.longPressTimer = null;
        }

        const endCoords = e.clientX !== undefined ?
            this.getVideoCoordinates(e.clientX, e.clientY) : this.currentPos;

        const duration = Date.now() - this.touchStartTime;
        const dx = endCoords.x - this.touchStartPos.x;
        const dy = endCoords.y - this.touchStartPos.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        this.isTouching = false;

        if (!this.isConnected || !this.wdaConnected) return;

        if (distance > this.swipeThreshold) {
            // Swipe detected
            this.sendCommand({
                type: 'swipe',
                x: this.touchStartPos.x,
                y: this.touchStartPos.y,
                endX: endCoords.x,
                endY: endCoords.y,
                duration: Math.max(duration, 100),
                videoWidth: this.touchStartPos.videoWidth,
                videoHeight: this.touchStartPos.videoHeight
            });
        } else if (duration < this.tapThreshold) {
            // Check for double tap
            const now = Date.now();
            if (now - this.lastTapTime < this.doubleTapThreshold) {
                // Double tap
                this.sendCommand({
                    type: 'doubletap',
                    x: this.touchStartPos.x,
                    y: this.touchStartPos.y,
                    videoWidth: this.touchStartPos.videoWidth,
                    videoHeight: this.touchStartPos.videoHeight
                });
                this.lastTapTime = 0;
            } else {
                // Single tap
                this.sendCommand({
                    type: 'tap',
                    x: this.touchStartPos.x,
                    y: this.touchStartPos.y,
                    videoWidth: this.touchStartPos.videoWidth,
                    videoHeight: this.touchStartPos.videoHeight
                });
                this.lastTapTime = now;
            }
        }
    }

    handleWheel(e) {
        e.preventDefault();

        if (!this.isConnected || !this.wdaConnected) return;

        const coords = this.getVideoCoordinates(e.clientX, e.clientY);

        this.sendCommand({
            type: 'scroll',
            x: coords.x,
            y: coords.y,
            deltaX: e.deltaX,
            deltaY: e.deltaY,
            videoWidth: coords.videoWidth,
            videoHeight: coords.videoHeight
        });
    }

    sendCommand(cmd) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('Control WebSocket not connected');
            return;
        }

        console.log('Sending command:', cmd);
        this.ws.send(JSON.stringify(cmd));
    }

    // Button actions
    pressHome() {
        this.sendCommand({ type: 'home' });
    }

    pressVolumeUp() {
        this.sendCommand({ type: 'volumeUp' });
    }

    pressVolumeDown() {
        this.sendCommand({ type: 'volumeDown' });
    }

    pressLock() {
        this.sendCommand({ type: 'lock' });
    }

    typeText(text) {
        if (text) {
            this.sendCommand({ type: 'type', text: text });
        }
    }

    showKeyboard() {
        const text = prompt('Enter text to type:');
        if (text) {
            this.typeText(text);
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
        this.wdaConnected = false;
    }
}


class StreamViewer {
    constructor() {
        this.pc = null;
        this.statsInterval = null;
        this.reconnectTimeout = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;

        // Stats tracking
        this.lastBytesReceived = 0;
        this.lastTimestamp = 0;

        // Device info tracking
        this.deviceInfoFetched = false;
        this.lastDeviceInfoFetch = 0;
        this.deviceType = 'device'; // 'device' or 'simulator'

        // DOM elements
        this.elements = {
            video: document.getElementById('video'),
            status: document.getElementById('status'),
            statusText: document.querySelector('.status-text'),
            noStream: document.getElementById('no-stream'),
            connectBtn: document.getElementById('connectBtn'),
            fullscreenBtn: document.getElementById('fullscreenBtn'),
            serverUrl: document.getElementById('server-url'),
            statFps: document.getElementById('stat-fps'),
            statResolution: document.getElementById('stat-resolution'),
            statBitrate: document.getElementById('stat-bitrate'),
            statPacketsLost: document.getElementById('stat-packets-lost'),
            // Device info elements
            deviceInfoPanel: document.getElementById('device-info-panel'),
            infoDevice: document.getElementById('info-device'),
            infoModel: document.getElementById('info-model'),
            infoSystem: document.getElementById('info-system'),
            infoScreen: document.getElementById('info-screen'),
            infoBattery: document.getElementById('info-battery'),
            // Control elements
            controlStatus: document.getElementById('control-status'),
            controlStatusText: document.getElementById('control-status-text'),
            homeBtn: document.getElementById('homeBtn'),
            volumeUpBtn: document.getElementById('volumeUpBtn'),
            volumeDownBtn: document.getElementById('volumeDownBtn'),
            keyboardBtn: document.getElementById('keyboardBtn'),
            lockBtn: document.getElementById('lockBtn'),
        };

        // Device controller for touch/gesture input
        this.controller = new DeviceController(
            this.elements.video,
            (status) => this.updateControlStatus(status)
        );

        this.init();
    }

    init() {
        // Display server URL
        this.elements.serverUrl.textContent = window.location.host;

        // Set up event listeners
        this.elements.connectBtn.addEventListener('click', () => this.connect());
        this.elements.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());

        // Control button listeners
        if (this.elements.homeBtn) {
            this.elements.homeBtn.addEventListener('click', () => this.controller.pressHome());
        }
        if (this.elements.volumeUpBtn) {
            this.elements.volumeUpBtn.addEventListener('click', () => this.controller.pressVolumeUp());
        }
        if (this.elements.volumeDownBtn) {
            this.elements.volumeDownBtn.addEventListener('click', () => this.controller.pressVolumeDown());
        }
        if (this.elements.keyboardBtn) {
            this.elements.keyboardBtn.addEventListener('click', () => this.controller.showKeyboard());
        }
        if (this.elements.lockBtn) {
            this.elements.lockBtn.addEventListener('click', () => this.controller.pressLock());
        }

        // Handle video events
        this.elements.video.addEventListener('playing', () => {
            this.elements.noStream.classList.add('hidden');
            this.elements.fullscreenBtn.disabled = false;
        });

        this.elements.video.addEventListener('pause', () => {
            // Video might pause due to no data
        });

        // Initialize device controller
        this.controller.connect();
        this.controller.setupEventListeners();

        // Auto-connect on load
        this.connect();
    }

    updateControlStatus(status) {
        if (!this.elements.controlStatus || !this.elements.controlStatusText) return;

        this.elements.controlStatus.classList.remove('connected', 'disconnected', 'partial');

        // Determine device type from status or stored value
        const deviceType = status.deviceInfo?.deviceType || this.deviceType || 'device';

        if (status.wdaConnected) {
            this.elements.controlStatus.classList.add('connected');
            if (deviceType === 'simulator') {
                this.elements.controlStatusText.textContent = 'Simulator Controls Active';
            } else {
                this.elements.controlStatusText.textContent = 'Controls Active';
            }
        } else if (status.connected) {
            this.elements.controlStatus.classList.add('partial');
            if (deviceType === 'simulator') {
                this.elements.controlStatusText.textContent = 'Connecting to Simulator...';
            } else {
                this.elements.controlStatusText.textContent = 'WDA Not Connected';
            }
        } else {
            this.elements.controlStatus.classList.add('disconnected');
            this.elements.controlStatusText.textContent = 'Controls Disabled';
        }
    }

    async connect() {
        this.updateStatus('connecting');
        this.elements.connectBtn.disabled = true;
        this.elements.connectBtn.innerHTML = '<span class="btn-icon">⏳</span> Connecting...';

        try {
            // Create peer connection with ICE servers
            this.pc = new RTCPeerConnection({
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' },
                ]
            });

            // Handle incoming tracks
            this.pc.ontrack = (event) => {
                console.log('Track received:', event.track.kind);
                this.elements.video.srcObject = event.streams[0];
                this.updateStatus('connected');
                this.reconnectAttempts = 0;
            };

            // Handle connection state changes
            this.pc.onconnectionstatechange = () => {
                console.log('Connection state:', this.pc.connectionState);

                switch (this.pc.connectionState) {
                    case 'connected':
                        this.updateStatus('connected');
                        break;
                    case 'disconnected':
                    case 'failed':
                        this.handleDisconnect();
                        break;
                    case 'closed':
                        this.updateStatus('disconnected');
                        break;
                }
            };

            // Handle ICE connection state
            this.pc.oniceconnectionstatechange = () => {
                console.log('ICE state:', this.pc.iceConnectionState);
            };

            // Add transceiver for receiving video
            this.pc.addTransceiver('video', { direction: 'recvonly' });

            // Create and send offer
            const offer = await this.pc.createOffer();
            await this.pc.setLocalDescription(offer);

            // Wait for ICE gathering to complete (or timeout)
            await this.waitForIceGathering(2000);

            // Send offer to server
            const response = await fetch('/offer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sdp: this.pc.localDescription.sdp,
                    type: this.pc.localDescription.type
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const answer = await response.json();

            if (answer.error) {
                throw new Error(answer.error);
            }

            // Set remote description
            await this.pc.setRemoteDescription(new RTCSessionDescription(answer));

            // Start stats monitoring
            this.startStatsMonitoring();

            // Update button
            this.elements.connectBtn.innerHTML = '<span class="btn-icon">⏹</span> Disconnect';
            this.elements.connectBtn.disabled = false;
            this.elements.connectBtn.onclick = () => this.disconnect();

        } catch (error) {
            console.error('Connection error:', error);
            this.updateStatus('disconnected');
            this.elements.connectBtn.innerHTML = '<span class="btn-icon">▶</span> Connect';
            this.elements.connectBtn.disabled = false;
            this.elements.connectBtn.onclick = () => this.connect();

            // Schedule reconnect
            this.scheduleReconnect();
        }
    }

    waitForIceGathering(timeout) {
        return new Promise((resolve) => {
            if (this.pc.iceGatheringState === 'complete') {
                resolve();
                return;
            }

            const checkState = () => {
                if (this.pc.iceGatheringState === 'complete') {
                    this.pc.removeEventListener('icegatheringstatechange', checkState);
                    resolve();
                }
            };

            this.pc.addEventListener('icegatheringstatechange', checkState);

            // Timeout fallback
            setTimeout(resolve, timeout);
        });
    }

    disconnect() {
        this.cleanup();
        this.updateStatus('disconnected');
        this.elements.connectBtn.innerHTML = '<span class="btn-icon">▶</span> Connect';
        this.elements.connectBtn.disabled = false;
        this.elements.connectBtn.onclick = () => this.connect();
        this.elements.noStream.classList.remove('hidden');
        this.elements.fullscreenBtn.disabled = true;
    }

    handleDisconnect() {
        console.log('Handling disconnect...');
        this.updateStatus('disconnected');
        this.cleanup();
        this.scheduleReconnect();
    }

    scheduleReconnect() {
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
        }

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Max reconnect attempts reached');
            this.elements.connectBtn.innerHTML = '<span class="btn-icon">▶</span> Connect';
            this.elements.connectBtn.disabled = false;
            this.elements.connectBtn.onclick = () => this.connect();
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * this.reconnectAttempts, 10000);

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        this.reconnectTimeout = setTimeout(() => {
            this.connect();
        }, delay);
    }

    startStatsMonitoring() {
        // Clear existing interval
        if (this.statsInterval) {
            clearInterval(this.statsInterval);
        }

        this.lastBytesReceived = 0;
        this.lastTimestamp = Date.now();

        this.statsInterval = setInterval(async () => {
            if (!this.pc) return;

            try {
                const stats = await this.pc.getStats();
                let fps = 0;
                let width = 0;
                let height = 0;
                let bytesReceived = 0;
                let packetsLost = 0;

                stats.forEach(report => {
                    if (report.type === 'inbound-rtp' && report.kind === 'video') {
                        fps = report.framesPerSecond || 0;
                        width = report.frameWidth || 0;
                        height = report.frameHeight || 0;
                        bytesReceived = report.bytesReceived || 0;
                        packetsLost = report.packetsLost || 0;
                    }
                });

                // Calculate bitrate
                const now = Date.now();
                const timeDiff = (now - this.lastTimestamp) / 1000; // seconds
                const bytesDiff = bytesReceived - this.lastBytesReceived;
                const bitrate = timeDiff > 0 ? (bytesDiff * 8) / timeDiff / 1000 : 0; // kbps

                this.lastBytesReceived = bytesReceived;
                this.lastTimestamp = now;

                // Update UI
                this.elements.statFps.textContent = fps > 0 ? fps.toFixed(1) : '--';
                this.elements.statResolution.textContent = width > 0 ? `${width}×${height}` : '--';
                this.elements.statBitrate.textContent = bitrate > 0 ? `${Math.round(bitrate)} kbps` : '--';
                this.elements.statPacketsLost.textContent = packetsLost.toString();

                // Fetch device info (once every 5 seconds)
                if (!this.deviceInfoFetched || (now - this.lastDeviceInfoFetch > 5000)) {
                    this.fetchDeviceInfo();
                    this.lastDeviceInfoFetch = now;
                }

            } catch (error) {
                console.error('Error getting stats:', error);
            }
        }, 1000);
    }

    async fetchDeviceInfo() {
        try {
            const response = await fetch('/device-info');
            if (response.ok) {
                const deviceInfo = await response.json();
                this.updateDeviceInfo(deviceInfo);
                this.deviceInfoFetched = true;
            }
        } catch (error) {
            console.error('Error fetching device info:', error);
        }
    }

    updateDeviceInfo(info) {
        if (!info || info.error) {
            this.elements.deviceInfoPanel.style.display = 'none';
            return;
        }

        // Show device info panel
        this.elements.deviceInfoPanel.style.display = 'flex';

        // Track device type for UI adjustments
        this.deviceType = info.deviceType || 'device';

        // Update page title based on device type
        if (this.deviceType === 'simulator') {
            document.title = 'iOS Simulator Stream';
            document.querySelector('h1').textContent = 'iOS Simulator Stream';
        } else {
            document.title = 'iOS Device Stream';
            document.querySelector('h1').textContent = 'iOS Device Stream';
        }

        // Update device info values
        this.elements.infoDevice.textContent = this.truncate(info.deviceName || 'Unknown', 12);
        this.elements.infoModel.textContent = info.deviceModel || 'Unknown';
        this.elements.infoSystem.textContent = `${info.systemName || 'iOS'} ${info.systemVersion || ''}`.trim();
        this.elements.infoScreen.textContent = `${info.screenResolution || '--'}`;

        // Format battery info (N/A for simulator)
        if (this.deviceType === 'simulator' || info.batteryLevel === -1) {
            this.elements.infoBattery.textContent = 'N/A';
        } else {
            const batteryLevel = info.batteryLevel !== undefined && info.batteryLevel >= 0 ? `${info.batteryLevel}%` : '--';
            const batteryIcon = info.batteryState === 'charging' ? '⚡' : '';
            this.elements.infoBattery.textContent = `${batteryLevel}${batteryIcon}`;
        }
    }

    truncate(str, maxLen) {
        if (str.length <= maxLen) return str;
        return str.substring(0, maxLen - 1) + '…';
    }

    updateStatus(status) {
        const statusEl = this.elements.status;
        const textEl = this.elements.statusText;

        // Remove all status classes
        statusEl.classList.remove('connected', 'connecting', 'disconnected');

        // Add new status class
        statusEl.classList.add(status);

        // Update text
        const statusTexts = {
            connected: 'Connected',
            connecting: 'Connecting...',
            disconnected: 'Disconnected'
        };

        textEl.textContent = statusTexts[status] || status;
    }

    toggleFullscreen() {
        const container = document.getElementById('video-container');

        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            container.requestFullscreen().catch(err => {
                console.error('Fullscreen error:', err);
            });
        }
    }

    cleanup() {
        if (this.statsInterval) {
            clearInterval(this.statsInterval);
            this.statsInterval = null;
        }

        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }

        if (this.pc) {
            this.pc.close();
            this.pc = null;
        }

        // Reset stats display
        this.elements.statFps.textContent = '--';
        this.elements.statResolution.textContent = '--';
        this.elements.statBitrate.textContent = '--';
        this.elements.statPacketsLost.textContent = '--';
    }
}

// Initialize viewer when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.viewer = new StreamViewer();
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden && window.viewer && window.viewer.pc) {
        // Page is hidden - could pause stats to save resources
    }
});
