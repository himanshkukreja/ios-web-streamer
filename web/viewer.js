/**
 * iOS Simulator Stream Viewer
 *
 * WebRTC client for receiving and displaying iOS simulator video stream.
 */

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
        };

        this.init();
    }

    init() {
        // Display server URL
        this.elements.serverUrl.textContent = window.location.host;

        // Set up event listeners
        this.elements.connectBtn.addEventListener('click', () => this.connect());
        this.elements.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());

        // Handle video events
        this.elements.video.addEventListener('playing', () => {
            this.elements.noStream.classList.add('hidden');
            this.elements.fullscreenBtn.disabled = false;
        });

        this.elements.video.addEventListener('pause', () => {
            // Video might pause due to no data
        });

        // Auto-connect on load
        this.connect();
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

            } catch (error) {
                console.error('Error getting stats:', error);
            }
        }, 1000);
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
