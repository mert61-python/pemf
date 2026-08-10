/**
 * PEMF Vet System - Main JavaScript
 * Real-time web interface with WebSocket support
 */

class PEMFWebInterface {
    constructor() {
        this.websocket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.isConnected = false;
        this.currentTreatment = null;
        this.updateInterval = null;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initializeWebSocket();
        this.loadInitialData();
        this.startPeriodicUpdates();

        // Show loading state initially
        this.showLoading();
    }

    /**
     * WebSocket Management
     */
    initializeWebSocket() {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.hostname}:8081/`;

            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = (event) => {
                console.log('WebSocket bağlantısı kuruldu');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus(true);
                this.hideLoading();
            };

            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('WebSocket mesaj parse hatası:', error);
                }
            };

            this.websocket.onclose = (event) => {
                console.log('WebSocket bağlantısı kapandı');
                this.isConnected = false;
                this.updateConnectionStatus(false);
                this.attemptReconnect();
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket hatası:', error);
                this.updateConnectionStatus(false);
            };

        } catch (error) {
            console.error('WebSocket başlatma hatası:', error);
            this.fallbackToPolling();
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Yeniden bağlanma denemesi ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);

            setTimeout(() => {
                this.initializeWebSocket();
            }, this.reconnectDelay * this.reconnectAttempts);
        } else {
            console.log('Maksimum yeniden bağlanma denemesi aşıldı, polling moduna geçiliyor');
            this.fallbackToPolling();
        }
    }

    fallbackToPolling() {
        console.log('WebSocket kullanılamıyor, HTTP polling kullanılıyor');
        this.startPeriodicUpdates();
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'status_update':
                this.updateSystemStatus(data.payload);
                break;
            case 'treatment_update':
                this.updateTreatmentStatus(data.payload);
                break;
            case 'sensor_data':
                this.updateSensorData(data.payload);
                break;
            case 'notification':
                this.showNotification(data.payload);
                break;
            case 'error':
                this.showError(data.payload.message);
                break;
            default:
                console.log('Bilinmeyen WebSocket mesaj tipi:', data.type);
        }
    }

    sendWebSocketMessage(type, payload) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            const message = {
                type: type,
                payload: payload,
                timestamp: new Date().toISOString()
            };
            this.websocket.send(JSON.stringify(message));
        } else {
            console.warn('WebSocket bağlantısı mevcut değil, HTTP fallback kullanılıyor');
            this.sendHttpRequest(type, payload);
        }
    }

    /**
     * HTTP API Management
     */
    async sendHttpRequest(endpoint, data = null, method = 'GET') {
        try {
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            };

            if (data && method !== 'GET') {
                options.body = JSON.stringify(data);
            }

            const response = await fetch(`/api/${endpoint}`, options);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API isteği hatası (${endpoint}):`, error);
            this.showError(`API hatası: ${error.message}`);
            throw error;
        }
    }

    /**
     * Data Loading and Updates
     */
    async loadInitialData() {
        try {
            await Promise.all([
                this.loadSystemStatus(),
                this.loadTreatmentHistory(),
                this.loadSensorData()
            ]);
        } catch (error) {
            console.error('İlk veri yükleme hatası:', error);
            this.showError('Veri yüklenirken hata oluştu');
        }
    }

    async loadSystemStatus() {
        try {
            const status = await this.sendHttpRequest('status');
            this.updateSystemStatus(status);
        } catch (error) {
            console.error('Sistem durumu yükleme hatası:', error);
        }
    }

    async loadTreatmentHistory() {
        try {
            const history = await this.sendHttpRequest('treatment-history');
            this.updateTreatmentHistory(history);
        } catch (error) {
            console.error('Tedavi geçmişi yükleme hatası:', error);
        }
    }

    async loadSensorData() {
        try {
            const sensorData = await this.sendHttpRequest('sensor-data');
            this.updateSensorData(sensorData);
        } catch (error) {
            console.error('Sensör verisi yükleme hatası:', error);
        }
    }

    startPeriodicUpdates() {
        // Clear existing interval
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }

        // Only use polling if WebSocket is not connected
        if (!this.isConnected) {
            this.updateInterval = setInterval(() => {
                this.loadSystemStatus();
                this.loadSensorData();
            }, 5000); // Update every 5 seconds
        }
    }

    /**
     * UI Updates
     */
    updateSystemStatus(status) {
        const statusElement = document.getElementById('system-status');
        const statusIndicator = document.getElementById('status-indicator');

        if (statusElement && statusIndicator) {
            statusElement.textContent = status.system_status === 'online' ? 'Çevrimiçi' : 'Çevrimdışı';
            statusIndicator.className = `status-indicator ${status.system_status === 'online' ? 'status-online' : 'status-offline'}`;
        }

        // Update current parameters
        this.updateCurrentParameters(status.current_parameters);

        // Update treatment status
        if (status.treatment_active !== undefined) {
            this.updateTreatmentControls(status.treatment_active);
        }
    }

    updateCurrentParameters(parameters) {
        const elements = {
            'current-frequency': parameters.frequency ? `${parameters.frequency} Hz` : 'Belirtilmemiş',
            'current-intensity': parameters.intensity ? `${parameters.intensity} mT` : 'Belirtilmemiş',
            'current-duration': parameters.duration ? `${parameters.duration} dk` : 'Belirtilmemiş'
        };

        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
    }

    updateTreatmentStatus(treatmentData) {
        this.currentTreatment = treatmentData;
        this.updateTreatmentControls(treatmentData.active);

        if (treatmentData.active) {
            this.showNotification({
                type: 'info',
                message: 'Tedavi başlatıldı',
                duration: 3000
            });
        }
    }

    updateTreatmentControls(isActive) {
        const startBtn = document.getElementById('start-treatment-btn');
        const stopBtn = document.getElementById('stop-treatment-btn');

        if (startBtn && stopBtn) {
            startBtn.disabled = isActive;
            stopBtn.disabled = !isActive;

            if (isActive) {
                startBtn.textContent = 'Tedavi Devam Ediyor...';
                stopBtn.textContent = 'Tedaviyi Durdur';
            } else {
                startBtn.textContent = 'Tedavi Başlat';
                stopBtn.textContent = 'Durdur';
            }
        }
    }

    updateSensorData(sensorData) {
        // HTML'deki ID'lere göre güncelle (object-temperature, ambient-temperature, magnetic-field, current)
        const sensorElements = {
            'object-temperature': sensorData.object_temp ? `${sensorData.object_temp.toFixed(1)}` : '--',
            'ambient-temperature': sensorData.ambient_temp ? `${sensorData.ambient_temp.toFixed(1)}` : '--',
            'magnetic-field': sensorData.magnetic_field ? `${sensorData.magnetic_field.toFixed(2)}` : '--',
            'current': sensorData.current ? `${sensorData.current.toFixed(2)}` : '--'
        };

        Object.entries(sensorElements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
                element.classList.add('fade-in');
            }
        });

        // Update ESP info
        const espInfo = document.getElementById('esp-info');
        const currentEsp = document.getElementById('current-esp');
        if (espInfo && sensorData.esp_id) {
            if (currentEsp) {
                currentEsp.textContent = sensorData.esp_id;
            }
            espInfo.className = `esp-info ${sensorData.esp_status || 'offline'}`;
        }

        // Update chart data if chart exists (for inline script compatibility)
        if (window.updateChartData && typeof window.updateChartData === 'function') {
            window.updateChartData(sensorData);
        }
    }

    updateTreatmentHistory(historyData) {
        const tableBody = document.getElementById('treatment-history-tbody');
        if (!tableBody || !historyData.sessions) return;

        tableBody.innerHTML = '';

        historyData.sessions.slice(0, 10).forEach(session => {
            const row = document.createElement('tr');
            // None değerlerini kontrol et
            const formatValue = (value, unit = '') => {
                if (value === null || value === undefined || value === 'None' || value === '') {
                    return 'Belirtilmemiş';
                }
                return unit ? `${value} ${unit}` : value;
            };

            row.innerHTML = `
                <td>${this.formatDate(session.session_date)}</td>
                <td>${formatValue(session.patient_name)}</td>
                <td>${formatValue(session.frequency_hz, 'Hz')}</td>
                <td>${formatValue(session.intensity_mt, 'mT')}</td>
                <td>${formatValue(session.duration_minutes, 'dk')}</td>
                <td>
                    <button class="btn btn-outline btn-sm" onclick="pemfInterface.viewSessionDetails('${session.session_id}')">
                        Detaylar
                    </button>
                </td>
            `;
            tableBody.appendChild(row);
        });
    }

    updateConnectionStatus(isConnected) {
        const connectionElement = document.getElementById('connection-status');
        if (connectionElement) {
            connectionElement.className = `status-indicator ${isConnected ? 'status-online' : 'status-offline'}`;
            connectionElement.innerHTML = `
                <span class="status-dot"></span>
                ${isConnected ? 'Bağlı' : 'Bağlantı Kesildi'}
            `;
        }
    }

    /**
     * Treatment Controls
     */
    async startTreatment() {
        try {
            const frequency = document.getElementById('frequency-input')?.value || 0;
            const intensity = document.getElementById('intensity-input')?.value || 0;
            const duration = document.getElementById('duration-input')?.value || 0;

            if (!frequency || !intensity || !duration) {
                this.showError('Lütfen tüm tedavi parametrelerini girin');
                return;
            }

            const treatmentData = {
                frequency: parseFloat(frequency),
                intensity: parseFloat(intensity),
                duration: parseFloat(duration)
            };

            this.showLoading('Tedavi başlatılıyor...');

            if (this.isConnected) {
                this.sendWebSocketMessage('start_treatment', treatmentData);
            } else {
                await this.sendHttpRequest('start-treatment', treatmentData, 'POST');
                this.showSuccess('Tedavi başarıyla başlatıldı');
            }

        } catch (error) {
            console.error('Tedavi başlatma hatası:', error);
            this.showError('Tedavi başlatılırken hata oluştu');
        } finally {
            this.hideLoading();
        }
    }

    async stopTreatment() {
        try {
            this.showLoading('Tedavi durduruluyor...');

            if (this.isConnected) {
                this.sendWebSocketMessage('stop_treatment', {});
            } else {
                await this.sendHttpRequest('stop-treatment', {}, 'POST');
                this.showSuccess('Tedavi başarıyla durduruldu');
            }

        } catch (error) {
            console.error('Tedavi durdurma hatası:', error);
            this.showError('Tedavi durdurulurken hata oluştu');
        } finally {
            this.hideLoading();
        }
    }

    async updateParameters() {
        try {
            const frequency = document.getElementById('frequency-input')?.value || 0;
            const intensity = document.getElementById('intensity-input')?.value || 0;
            const duration = document.getElementById('duration-input')?.value || 0;

            const parameters = {
                frequency: parseFloat(frequency),
                intensity: parseFloat(intensity),
                duration: parseFloat(duration)
            };

            if (this.isConnected) {
                this.sendWebSocketMessage('update_parameters', parameters);
            } else {
                await this.sendHttpRequest('update-parameters', parameters, 'POST');
                this.showSuccess('Parametreler güncellendi');
            }

        } catch (error) {
            console.error('Parametre güncelleme hatası:', error);
            this.showError('Parametreler güncellenirken hata oluştu');
        }
    }

    /**
     * Session Details
     */
    async viewSessionDetails(sessionId) {
        try {
            const details = await this.sendHttpRequest(`session-details?session_id=${sessionId}`);
            this.showSessionDetailsModal(details);
        } catch (error) {
            console.error('Seans detayları yükleme hatası:', error);
            this.showError('Seans detayları yüklenirken hata oluştu');
        }
    }

    showSessionDetailsModal(details) {
        // Create modal if it doesn't exist
        let modal = document.getElementById('session-details-modal');
        if (!modal) {
            modal = this.createSessionDetailsModal();
            document.body.appendChild(modal);
        }

        // Populate modal with session details
        const modalContent = modal.querySelector('.modal-content');
        modalContent.innerHTML = `
            <div class="modal-header">
                <h3>Seans Detayları</h3>
                <button class="btn btn-outline" onclick="pemfInterface.closeModal('session-details-modal')">×</button>
            </div>
            <div class="modal-body">
                <div class="grid grid-2">
                    <div class="card">
                        <h4>Hasta Bilgileri</h4>
                        <p><strong>Ad:</strong> ${details.session_details.patient_name || 'Belirtilmemiş'}</p>
                        <p><strong>Tür:</strong> ${details.session_details.patient_species || 'Belirtilmemiş'}</p>
                        <p><strong>Irk:</strong> ${details.session_details.patient_breed || 'Belirtilmemiş'}</p>
                        <p><strong>Yaş:</strong> ${details.session_details.patient_age || 'Belirtilmemiş'}</p>
                        <p><strong>Ağırlık:</strong> ${details.session_details.patient_weight || 'Belirtilmemiş'}</p>
                    </div>
                    <div class="card">
                        <h4>Tedavi Parametreleri</h4>
                        ${Object.entries(details.parameters).map(([key, param]) =>
                            `<p><strong>${param.turkish_name}:</strong> ${param.value}</p>`
                        ).join('')}
                    </div>
                </div>
                <div class="card mt-3">
                    <h4>Seans Bilgileri</h4>
                    <p><strong>Tarih:</strong> ${this.formatDate(details.session_details.session_date)}</p>
                    <p><strong>Veteriner:</strong> ${details.session_details.veterinarian || 'Belirtilmemiş'}</p>
                    <p><strong>Notlar:</strong> ${details.session_details.notes || 'Not bulunmuyor'}</p>
                </div>
            </div>
        `;

        modal.style.display = 'flex';
    }

    createSessionDetailsModal() {
        const modal = document.createElement('div');
        modal.id = 'session-details-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <!-- Content will be populated dynamically -->
            </div>
        `;
        return modal;
    }

    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
        }
    }

    /**
     * Notification System
     */
    showNotification(notification) {
        const container = this.getNotificationContainer();

        const notificationElement = document.createElement('div');
        notificationElement.className = `alert alert-${notification.type || 'info'} fade-in`;
        notificationElement.innerHTML = `
            <div class="flex-between">
                <span>${notification.message}</span>
                <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; color: inherit; cursor: pointer;">×</button>
            </div>
        `;

        container.appendChild(notificationElement);

        // Auto remove after duration
        const duration = notification.duration || 5000;
        setTimeout(() => {
            if (notificationElement.parentNode) {
                notificationElement.remove();
            }
        }, duration);
    }

    showSuccess(message) {
        this.showNotification({ type: 'success', message, duration: 3000 });
    }

    showError(message) {
        this.showNotification({ type: 'danger', message, duration: 5000 });
    }

    showWarning(message) {
        this.showNotification({ type: 'warning', message, duration: 4000 });
    }

    getNotificationContainer() {
        let container = document.getElementById('notification-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notification-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 1000;
                max-width: 400px;
            `;
            document.body.appendChild(container);
        }
        return container;
    }

    /**
     * Loading States
     */
    showLoading(message = 'Yükleniyor...') {
        let loader = document.getElementById('global-loader');
        if (!loader) {
            loader = document.createElement('div');
            loader.id = 'global-loader';
            loader.innerHTML = `
                <div style="
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0, 0, 0, 0.5);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 9999;
                ">
                    <div class="card text-center">
                        <div class="loading mb-2"></div>
                        <p>${message}</p>
                    </div>
                </div>
            `;
            document.body.appendChild(loader);
        } else {
            const messageElement = loader.querySelector('p');
            if (messageElement) {
                messageElement.textContent = message;
            }
            loader.style.display = 'block';
        }
    }

    hideLoading() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.style.display = 'none';
        }
    }

    /**
     * Event Listeners
     */
    setupEventListeners() {
        // Treatment control buttons
        const startBtn = document.getElementById('start-treatment-btn');
        const stopBtn = document.getElementById('stop-treatment-btn');
        const updateBtn = document.getElementById('update-parameters-btn');

        if (startBtn) {
            startBtn.addEventListener('click', () => this.startTreatment());
        }

        if (stopBtn) {
            stopBtn.addEventListener('click', () => this.stopTreatment());
        }

        if (updateBtn) {
            updateBtn.addEventListener('click', () => this.updateParameters());
        }

        // Refresh buttons
        const refreshBtns = document.querySelectorAll('[data-refresh]');
        refreshBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.getAttribute('data-refresh');
                this.refreshData(target);
            });
        });

        // Modal close on outside click
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                e.target.style.display = 'none';
            }
        });

        // Handle page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                // Page is hidden, reduce update frequency
                if (this.updateInterval) {
                    clearInterval(this.updateInterval);
                }
            } else {
                // Page is visible, resume normal updates
                this.startPeriodicUpdates();
            }
        });

        // Handle connection changes
        window.addEventListener('online', () => {
            this.showSuccess('İnternet bağlantısı yeniden kuruldu');
            if (!this.isConnected) {
                this.initializeWebSocket();
            }
        });

        window.addEventListener('offline', () => {
            this.showWarning('İnternet bağlantısı kesildi');
        });
    }

    /**
     * Utility Functions
     */
    formatDate(dateString) {
        if (!dateString) return 'Belirtilmemiş';

        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('tr-TR', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            return dateString;
        }
    }

    refreshData(target) {
        switch (target) {
            case 'status':
                this.loadSystemStatus();
                break;
            case 'history':
                this.loadTreatmentHistory();
                break;
            case 'sensors':
                this.loadSensorData();
                break;
            case 'all':
                this.loadInitialData();
                break;
            default:
                console.warn('Bilinmeyen refresh target:', target);
        }
    }

    /**
     * Chart Management (for inline script compatibility)
     */
    updateChartData(data) {
        // This method will be called by inline script if chart exists
        if (window.realtimeChart && typeof window.realtimeChart !== 'undefined') {
            if (window.updateChartData && typeof window.updateChartData === 'function') {
                window.updateChartData(data);
            }
        }
    }

    // Public method to send custom messages
    sendCustomMessage(type, data) {
        if (this.isConnected) {
            this.sendWebSocketMessage(type, data);
        } else {
            console.warn('WebSocket bağlantısı mevcut değil');
        }
    }

    // Get current connection status
    getConnectionStatus() {
        return {
            websocket: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
            currentTreatment: this.currentTreatment
        };
    }
}

// Initialize the interface when the page loads
let pemfInterface;

document.addEventListener('DOMContentLoaded', () => {
    pemfInterface = new PEMFWebInterface();

    // Make it globally accessible for debugging
    window.pemfInterface = pemfInterface;

    console.log('PEMF Web Interface başlatıldı');
});

// Export for module usage if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PEMFWebInterface;
}
