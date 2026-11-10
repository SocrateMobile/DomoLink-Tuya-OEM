/**
 * DomoLink Tuya OEM Custom Panel for Home Assistant
 * Glassmorphism Dark Theme matching DomoLink Suite
 * Version 2.0.0
 */

class DomolinkTuyaPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._activeTab = "devices"; // "devices" | "settings"
    this._selectedCategory = "all";
    this._selectedBrand = "all";
    this._searchQuery = "";
    this._showOnline = true;
    this._showOffline = true;
    this._dashboardData = {
      summary: { total_devices: 0, online_count: 0, offline_count: 0, lan_count: 0, account_count: 0 },
      accounts: [],
      devices: [],
      profiles: [],
    };
    this._expandedDps = new Set();
    this._refreshTimer = null;
    this._isScanning = false;
    this._isAddingAccount = false;
  }

  set panel(panel) {
    this._panel = panel;
  }

  set hass(hass) {
    const isFirst = !this._hass;
    this._hass = hass;
    if (isFirst) {
      this._init();
    }
  }

  connectedCallback() {
    this.render();
    this._startPeriodicRefresh();
  }

  disconnectedCallback() {
    this._stopPeriodicRefresh();
  }

  async _init() {
    this.render();
    await this._fetchDashboard();
  }

  _startPeriodicRefresh() {
    this._stopPeriodicRefresh();
    this._refreshTimer = setInterval(() => {
      this._fetchDashboard(false);
    }, 10000);
  }

  _stopPeriodicRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  async _fetchDashboard(renderAfter = true) {
    if (!this._hass) return;
    try {
      const resp = await this._hass.callWS({ type: "domolink_tuya_oem/get_dashboard" });
      if (resp) {
        this._dashboardData = resp;
        if (renderAfter) this.render();
      }
    } catch (e) {
      console.error("[DomoLink-Tuya] Failed to fetch dashboard data:", e);
    }
  }

  _showToast(msg, duration = 3000) {
    const toast = this.shadowRoot.querySelector(".toast-bar");
    if (toast) {
      toast.textContent = msg;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), duration);
    }
  }

  _escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async _sendDpAction(deviceId, action, params = {}) {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({
        type: "domolink_tuya_oem/send_dp_command",
        device_id: deviceId,
        action: action,
        params: params,
      });
      if (res && res.success) {
        this._showToast(`Action ${action} exécutée ✨`);
        await this._fetchDashboard(true);
      }
    } catch (e) {
      this._showToast(`❌ Erreur action: ${e.message || e}`);
    }
  }

  async _sendRawDp(deviceId, code, val) {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({
        type: "domolink_tuya_oem/send_dp_command",
        device_id: deviceId,
        code: code,
        value: val,
      });
      if (res && res.success) {
        this._showToast(`DP ${code} mis à jour avec succès`);
        await this._fetchDashboard(true);
      }
    } catch (e) {
      this._showToast(`❌ Erreur DP: ${e.message || e}`);
    }
  }

  async _updateDeviceMeta(deviceId, customName, forcedType, ip, rtspUrl) {
    if (!this._hass) return;
    try {
      const payload = {
        type: "domolink_tuya_oem/update_device_meta",
        device_id: deviceId,
        custom_name: customName,
        forced_type: forcedType,
        ip: ip,
      };
      if (rtspUrl !== undefined) {
        if (rtspUrl.startsWith("camera.")) {
          payload.linked_camera_entity = rtspUrl;
        } else {
          payload.rtsp_url = rtspUrl;
        }
      }
      const res = await this._hass.callWS(payload);
      if (res && res.success) {
        this._showToast("✨ Appareil mis à jour avec succès !");
        await this._fetchDashboard(true);
      }
    } catch (e) {
      this._showToast(`❌ Erreur: ${e.message || e}`);
    }
  }

  async _scanLan() {
    if (!this._hass || this._isScanning) return;
    this._isScanning = true;
    this.render();
    try {
      const res = await this._hass.callWS({ type: "domolink_tuya_oem/scan_lan" });
      this._showToast(`📡 Scan LAN terminé : ${res.found_count} détecté(s), ${res.updated_count} assigné(s)`);
      await this._fetchDashboard(true);
    } catch (e) {
      this._showToast(`❌ Erreur scan: ${e.message || e}`);
    } finally {
      this._isScanning = false;
      this.render();
    }
  }

  async _addAccount(brand, username, password, countryCode) {
    if (!this._hass || this._isAddingAccount) return;
    this._isAddingAccount = true;
    this.render();
    try {
      const res = await this._hass.callWS({
        type: "domolink_tuya_oem/add_account",
        brand: brand,
        username: username,
        password: password,
        country_code: countryCode,
      });
      if (res && res.success) {
        this._showToast(`🎉 Compte ${res.title} connecté avec succès !`);
        await this._fetchDashboard(true);
      }
    } catch (e) {
      this._showToast(`❌ Erreur connexion: ${e.message || e}`);
    } finally {
      this._isAddingAccount = false;
      this.render();
    }
  }

  async _removeAccount(entryId) {
    if (!confirm("Voulez-vous vraiment déconnecter ce compte de Home Assistant ?")) return;
    try {
      const res = await this._hass.callWS({
        type: "domolink_tuya_oem/remove_account",
        entry_id: entryId,
      });
      if (res && res.success) {
        this._showToast("🗑️ Compte déconnecté");
        await this._fetchDashboard(true);
      }
    } catch (e) {
      this._showToast(`❌ Erreur déconnexion: ${e.message || e}`);
    }
  }

  render() {
    const summary = this._dashboardData.summary || {};
    const devices = this._filterDevices(this._dashboardData.devices || []);
    const accounts = this._dashboardData.accounts || [];
    const profiles = this._dashboardData.profiles || [];

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          color: #f0f6fc;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          background: #0d1117;
          min-height: 100vh;
          box-sizing: border-box;
          padding: 24px;
        }

        /* Glassmorphism containers */
        .glass-panel {
          background: rgba(22, 27, 34, 0.85);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 24px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }

        /* Toast notifications */
        .toast-bar {
          position: fixed;
          top: 24px;
          right: 24px;
          background: #3b82f6;
          color: #ffffff;
          padding: 12px 24px;
          border-radius: 10px;
          font-size: 14px;
          font-weight: 600;
          box-shadow: 0 4px 20px rgba(59, 130, 246, 0.5);
          opacity: 0;
          transform: translateY(-20px);
          transition: all 0.3s ease;
          pointer-events: none;
          z-index: 9999;
        }
        .toast-bar.show {
          opacity: 1;
          transform: translateY(0);
        }

        /* Header */
        header {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 20px;
          margin-bottom: 24px;
        }
        .brand-container {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        .brand-logo {
          width: 52px;
          height: 52px;
          border-radius: 14px;
          background: linear-gradient(135deg, #3b82f6, #1d4ed8);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 28px;
          box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4);
        }
        .brand-text h1 {
          margin: 0;
          font-size: 24px;
          font-weight: 700;
          background: linear-gradient(90deg, #60a5fa, #93c5fd);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }
        .brand-text p {
          margin: 4px 0 0;
          color: #8b949e;
          font-size: 13px;
        }

        /* Nav Tabs */
        .tabs {
          display: flex;
          gap: 8px;
          background: rgba(13, 17, 23, 0.8);
          padding: 6px;
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .tab-btn {
          background: transparent;
          border: none;
          color: #8b949e;
          font-size: 14px;
          font-weight: 600;
          padding: 8px 18px;
          border-radius: 8px;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 8px;
          transition: all 0.2s ease;
        }
        .tab-btn:hover {
          color: #f0f6fc;
          background: rgba(255, 255, 255, 0.05);
        }
        .tab-btn.active {
          color: #ffffff;
          background: #3b82f6;
          box-shadow: 0 2px 10px rgba(59, 130, 246, 0.4);
        }

        /* Summary Stats Cards */
        .stats-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 16px;
          margin-bottom: 24px;
        }
        .stat-card {
          background: rgba(22, 27, 34, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 16px;
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .stat-card.clickable {
          cursor: pointer;
          user-select: none;
          transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .stat-card.clickable:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
        }
        .stat-card.filter-online.active {
          border-color: rgba(16, 185, 129, 0.45);
          background: rgba(16, 185, 129, 0.08);
          box-shadow: 0 0 16px rgba(16, 185, 129, 0.12);
        }
        .stat-card.filter-online.active:hover {
          border-color: #10b981;
          background: rgba(16, 185, 129, 0.16);
          box-shadow: 0 0 20px rgba(16, 185, 129, 0.25);
        }
        .stat-card.filter-online.disabled {
          opacity: 0.38;
          filter: grayscale(0.85);
          border-style: dashed;
          background: rgba(22, 27, 34, 0.3);
        }
        .stat-card.filter-offline.active {
          border-color: rgba(239, 68, 68, 0.45);
          background: rgba(239, 68, 68, 0.08);
          box-shadow: 0 0 16px rgba(239, 68, 68, 0.12);
        }
        .stat-card.filter-offline.active:hover {
          border-color: #ef4444;
          background: rgba(239, 68, 68, 0.16);
          box-shadow: 0 0 20px rgba(239, 68, 68, 0.25);
        }
        .stat-card.filter-offline.disabled {
          opacity: 0.38;
          filter: grayscale(0.85);
          border-style: dashed;
          background: rgba(22, 27, 34, 0.3);
        }
        .stat-icon {
          font-size: 26px;
          width: 44px;
          height: 44px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .stat-value {
          font-size: 20px;
          font-weight: 700;
          color: #f0f6fc;
        }
        .stat-label {
          font-size: 12px;
          color: #8b949e;
        }

        /* Filter Controls */
        .filters-bar {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 14px;
          margin-bottom: 20px;
        }
        .filter-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .pill {
          background: rgba(255, 255, 255, 0.05);
          color: #8b949e;
          border: 1px solid rgba(255, 255, 255, 0.08);
          padding: 6px 14px;
          border-radius: 20px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .pill:hover {
          color: #f0f6fc;
          background: rgba(255, 255, 255, 0.1);
        }
        .pill.active {
          color: #ffffff;
          background: #3b82f6;
          border-color: #3b82f6;
        }
        .search-box {
          position: relative;
          min-width: 240px;
        }
        .search-input {
          width: 100%;
          background: rgba(13, 17, 23, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          padding: 8px 12px;
          color: #f0f6fc;
          font-size: 13px;
          outline: none;
          box-sizing: border-box;
        }
        .search-input:focus {
          border-color: #3b82f6;
        }

        /* Device Grid */
        .device-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 20px;
        }
        .device-card {
          background: rgba(22, 27, 34, 0.9);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 18px;
          display: flex;
          flex-direction: column;
          gap: 14px;
          transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .device-card:hover {
          border-color: rgba(59, 130, 246, 0.4);
          transform: translateY(-2px);
        }
        .device-top {
          display: flex;
          gap: 14px;
          align-items: center;
        }
        .product-img-box {
          width: 56px;
          height: 56px;
          border-radius: 12px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          flex-shrink: 0;
        }
        .product-img {
          max-width: 48px;
          max-height: 48px;
          object-fit: contain;
        }
        .product-fallback-icon {
          font-size: 26px;
        }
        .device-meta {
          flex: 1;
          min-width: 0;
        }
        .device-name {
          font-size: 15px;
          font-weight: 700;
          color: #f0f6fc;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .device-sub {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #8b949e;
          margin-top: 2px;
        }
        .brand-badge {
          background: rgba(255, 255, 255, 0.08);
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 11px;
        }
        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .status-dot.online {
          background: #10b981;
          box-shadow: 0 0 8px #10b981;
        }
        .status-dot.offline {
          background: #ef4444;
        }
        .lan-badge {
          background: rgba(245, 158, 11, 0.15);
          color: #fbbf24;
          border: 1px solid rgba(245, 158, 11, 0.3);
          border-radius: 4px;
          padding: 1px 5px;
          font-size: 10px;
          font-weight: 700;
        }

        /* Controls Section */
        .controls-box {
          background: rgba(13, 17, 23, 0.6);
          border-radius: 12px;
          padding: 14px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .control-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }
        .control-label {
          font-size: 12px;
          font-weight: 600;
          color: #8b949e;
        }

        /* Toggle Button */
        .toggle-switch {
          position: relative;
          display: inline-block;
          width: 44px;
          height: 24px;
        }
        .toggle-switch input {
          opacity: 0;
          width: 0;
          height: 0;
        }
        .slider-round {
          position: absolute;
          cursor: pointer;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: rgba(255, 255, 255, 0.15);
          transition: 0.3s;
          border-radius: 24px;
        }
        .slider-round:before {
          position: absolute;
          content: "";
          height: 18px;
          width: 18px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: 0.3s;
          border-radius: 50%;
        }
        input:checked + .slider-round {
          background-color: #3b82f6;
        }
        input:checked + .slider-round:before {
          transform: translateX(20px);
        }

        /* Sliders */
        .range-slider {
          flex: 1;
          accent-color: #3b82f6;
          cursor: pointer;
        }

        /* Color Picker */
        .color-picker {
          border: none;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          cursor: pointer;
          background: transparent;
        }

        /* Metrics Grid for plugs/sensors */
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
        }
        .metric-item {
          background: rgba(255, 255, 255, 0.04);
          padding: 8px 10px;
          border-radius: 8px;
          display: flex;
          flex-direction: column;
        }
        .metric-val {
          font-size: 14px;
          font-weight: 700;
          color: #f0f6fc;
        }
        .metric-lbl {
          font-size: 11px;
          color: #8b949e;
        }

        /* Camera Box */
        .camera-preview-box {
          position: relative;
          width: 100%;
          height: 140px;
          border-radius: 10px;
          background: #000000;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .camera-img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .live-stream-btn {
          position: absolute;
          bottom: 8px;
          right: 8px;
          background: #ef4444;
          color: white;
          border: none;
          padding: 4px 10px;
          border-radius: 6px;
          font-size: 11px;
          font-weight: 700;
          cursor: pointer;
        }

        /* DP Inspector Accordion */
        .dp-inspector {
          border-top: 1px solid rgba(255, 255, 255, 0.06);
          padding-top: 10px;
        }
        .dp-toggle-btn {
          width: 100%;
          background: transparent;
          border: none;
          color: #60a5fa;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 4px 0;
        }
        .dp-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 11px;
          margin-top: 8px;
        }
        .dp-table th {
          text-align: left;
          color: #8b949e;
          padding: 4px 6px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .dp-table td {
          padding: 4px 6px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }
        .dp-code {
          color: #f59e0b;
          font-family: monospace;
        }

        /* Settings Tab Styles */
        .settings-section {
          margin-bottom: 32px;
        }
        .section-title {
          font-size: 18px;
          font-weight: 700;
          color: #f0f6fc;
          margin-bottom: 16px;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .account-card {
          background: rgba(22, 27, 34, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        .btn-action {
          background: rgba(255, 255, 255, 0.08);
          color: #f0f6fc;
          border: 1px solid rgba(255, 255, 255, 0.12);
          padding: 8px 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: all 0.2s ease;
        }
        .btn-action:hover {
          background: rgba(59, 130, 246, 0.2);
          border-color: #3b82f6;
          color: #60a5fa;
        }
        .btn-action.danger:hover {
          background: rgba(239, 68, 68, 0.2);
          border-color: #ef4444;
          color: #f87171;
        }
        .btn-action.primary {
          background: #3b82f6;
          border-color: #3b82f6;
          color: #ffffff;
        }
        .btn-action.primary:hover {
          background: #2563eb;
        }

        /* Form Inputs */
        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 16px;
          margin-bottom: 16px;
        }
        .form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .form-label {
          font-size: 12px;
          font-weight: 600;
          color: #8b949e;
        }
        .form-input, .form-select {
          background: rgba(13, 17, 23, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 8px;
          padding: 9px 12px;
          color: #f0f6fc;
          font-size: 13px;
          outline: none;
        }
        .form-input:focus, .form-select:focus {
          border-color: #3b82f6;
        }

        /* Device table */
        .device-manage-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }
        .device-manage-table th {
          text-align: left;
          padding: 10px 12px;
          color: #8b949e;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .device-manage-table td {
          padding: 12px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          vertical-align: middle;
        }
      </style>

      <div class="toast-bar"></div>

      <!-- Header -->
      <header>
        <div class="brand-container">
          <div class="brand-logo">⚡</div>
          <div class="brand-text">
            <h1>DomoLink Tuya OEM</h1>
            <p>Gestion intelligente, Décodage universel des DPs & Pilotage multi-marques</p>
          </div>
        </div>

        <div class="tabs">
          <button class="tab-btn ${this._activeTab === "devices" ? "active" : ""}" id="tab-devices">
            <span>📦</span> Appareils & Contrôles
          </button>
          <button class="tab-btn ${this._activeTab === "settings" ? "active" : ""}" id="tab-settings">
            <span>⚙️</span> Paramètres & Comptes
          </button>
        </div>
      </header>

      <!-- Stats Summary -->
      <div class="stats-row">
        <div class="stat-card clickable" id="stat-filter-total" title="Afficher tous les appareils (réinitialiser les filtres)">
          <div class="stat-icon">📱</div>
          <div>
            <div class="stat-value">${summary.total_devices || 0}</div>
            <div class="stat-label">Total Appareils</div>
          </div>
        </div>
        <div class="stat-card clickable filter-online ${this._showOnline ? "active" : "disabled"}" id="stat-filter-online" title="${this._showOnline ? "Cliquer pour masquer les appareils en ligne" : "Cliquer pour afficher les appareils en ligne"}">
          <div class="stat-icon" style="color: #10b981;">🟢</div>
          <div>
            <div class="stat-value">${summary.online_count || 0}</div>
            <div class="stat-label">En Ligne ${!this._showOnline ? "(Masqué)" : ""}</div>
          </div>
        </div>
        <div class="stat-card clickable filter-offline ${this._showOffline ? "active" : "disabled"}" id="stat-filter-offline" title="${this._showOffline ? "Cliquer pour masquer les appareils hors ligne" : "Cliquer pour afficher les appareils hors ligne"}">
          <div class="stat-icon" style="color: #ef4444;">🔴</div>
          <div>
            <div class="stat-value">${summary.offline_count || 0}</div>
            <div class="stat-label">Hors Ligne ${!this._showOffline ? "(Masqué)" : ""}</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="color: #f59e0b;">⚡</div>
          <div>
            <div class="stat-value">${summary.lan_count || 0}</div>
            <div class="stat-label">Contrôle LAN Actif</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon">☁️</div>
          <div>
            <div class="stat-value">${summary.account_count || 0}</div>
            <div class="stat-label">Comptes Connectés</div>
          </div>
        </div>
      </div>

      <!-- Tab Content Area -->
      ${this._activeTab === "devices" ? this._renderDevicesTab(devices) : this._renderSettingsTab(accounts, profiles)}
    `;

    this._bindEvents();
  }

  _filterDevices(devices) {
    return devices.filter((dev) => {
      // Online / Offline filter
      const isOnline = Boolean(dev.online);
      if (isOnline && !this._showOnline) {
        return false;
      }
      if (!isOnline && !this._showOffline) {
        return false;
      }

      // Category filter
      if (this._selectedCategory !== "all" && dev.device_type !== this._selectedCategory) {
        return false;
      }
      // Search query
      if (this._searchQuery) {
        const q = this._searchQuery.toLowerCase();
        const n = (dev.name || "").toLowerCase();
        const p = (dev.product_name || "").toLowerCase();
        const id = (dev.id || "").toLowerCase();
        if (!n.includes(q) && !p.includes(q) && !id.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }

  _renderDevicesTab(devices) {
    return `
      <!-- Filters and Search -->
      <div class="filters-bar">
        <div class="filter-pills">
          <div class="pill ${this._selectedCategory === "all" ? "active" : ""}" data-cat="all">Tous (${devices.length})</div>
          <div class="pill ${this._selectedCategory === "light" ? "active" : ""}" data-cat="light">💡 Éclairages</div>
          <div class="pill ${this._selectedCategory === "switch" ? "active" : ""}" data-cat="switch">🔌 Prises & Switchs</div>
          <div class="pill ${this._selectedCategory === "camera" ? "active" : ""}" data-cat="camera">📹 Caméras</div>
          <div class="pill ${this._selectedCategory === "sensor" ? "active" : ""}" data-cat="sensor">🌡️ Capteurs</div>
          <div class="pill ${this._selectedCategory === "security" ? "active" : ""}" data-cat="security">🛡️ Sécurité</div>
          <div class="pill ${this._selectedCategory === "climate" ? "active" : ""}" data-cat="climate">❄️ Climatisation</div>
          <div class="pill ${this._selectedCategory === "cover" ? "active" : ""}" data-cat="cover">🪟 Volets</div>
        </div>

        <div class="search-box">
          <input type="text" class="search-input" id="search-devices" placeholder="🔍 Rechercher un appareil..." value="${this._escapeHtml(this._searchQuery)}" />
        </div>
      </div>

      <!-- Devices Grid -->
      ${devices.length === 0 ? `
        <div class="glass-panel" style="text-align: center; padding: 60px 20px;">
          <div style="font-size: 40px; margin-bottom: 12px;">🔍</div>
          <div style="font-size: 16px; font-weight: 600;">Aucun appareil correspondant</div>
          <div style="color: #8b949e; margin-top: 6px;">Vérifiez vos filtres ou ajoutez un compte depuis l'onglet Paramètres.</div>
        </div>
      ` : `
        <div class="device-grid">
          ${devices.map((dev) => this._renderDeviceCard(dev)).join("")}
        </div>
      `}
    `;
  }

  _renderDeviceCard(dev) {
    const rawDps = dev.raw_dps || {};
    const parsedDps = dev.parsed_dps || {};
    const isExpanded = this._expandedDps.has(dev.id);

    // Default icon by type
    const fallbackIcons = {
      light: "💡",
      switch: "🔌",
      camera: "📹",
      sensor: "🌡️",
      security: "🛡️",
      climate: "❄️",
      cover: "🪟",
    };
    const typeIcon = fallbackIcons[dev.device_type] || "📱";

    return `
      <div class="device-card" data-device-id="${dev.id}">
        <!-- Device Top Header -->
        <div class="device-top">
          <div class="product-img-box">
            ${dev.icon_url ? `
              <img src="${this._escapeHtml(dev.icon_url)}" class="product-img" alt="${this._escapeHtml(dev.name)}" />
            ` : `
              <span class="product-fallback-icon">${typeIcon}</span>
            `}
          </div>
          <div class="device-meta">
            <div class="device-name" title="${this._escapeHtml(dev.name)}">${this._escapeHtml(dev.name)}</div>
            <div class="device-sub">
              <span class="brand-badge">${this._escapeHtml(dev.brand_name)}</span>
              <div class="status-dot ${dev.online ? "online" : "offline"}" title="${dev.online ? "En ligne" : "Hors ligne"}"></div>
              ${dev.lan_active ? `<span class="lan-badge">⚡ LAN</span>` : ""}
            </div>
          </div>
        </div>

        <!-- Controls Box Tailored to Device Type -->
        <div class="controls-box">
          ${this._renderControlsByType(dev, rawDps)}
        </div>

        <!-- DP Inspector Accordion -->
        <div class="dp-inspector">
          <button class="dp-toggle-btn" data-toggle-dps="${dev.id}">
            <span>🔍 Inspecteur DPs (${Object.keys(parsedDps).length})</span>
            <span>${isExpanded ? "▲ Masquer" : "▼ Déplier"}</span>
          </button>

          ${isExpanded ? `
            <table class="dp-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Nom</th>
                  <th>Valeur</th>
                </tr>
              </thead>
              <tbody>
                ${Object.entries(parsedDps).map(([dpId, p]) => `
                  <tr>
                    <td class="dp-code">${dpId}</td>
                    <td>${this._escapeHtml(p.name || p.code || dpId)}</td>
                    <td style="font-weight: 600;">${this._escapeHtml(String(p.value))} ${p.unit || ""}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          ` : ""}
        </div>
      </div>
    `;
  }

  _renderControlsByType(dev, dps) {
    const caps = dev.light_caps || {};

    // 1. LIGHT CONTROLS
    if (dev.device_type === "light") {
      const swCode = caps.switch_dp || ("20" in dps ? "20" : "1");
      const isOn = Boolean(dps[swCode]);
      const brightVal = dps[caps.bright_dp] ? Math.round(dps[caps.bright_dp] / 10) : 100;
      const tempVal = dps[caps.temp_dp] || 500;
      const kelvin = Math.round(2700 + (tempVal / 1000.0) * (6500 - 2700));

      return `
        <div class="control-row">
          <span class="control-label">Alimentation</span>
          <label class="toggle-switch">
            <input type="checkbox" class="ctrl-light-power" data-dev-id="${dev.id}" ${isOn ? "checked" : ""} />
            <span class="slider-round"></span>
          </label>
        </div>

        ${caps.supports_brightness ? `
          <div class="control-row">
            <span class="control-label">Luminosité (${brightVal}%)</span>
            <input type="range" min="1" max="100" value="${brightVal}" class="range-slider ctrl-light-bright" data-dev-id="${dev.id}" />
          </div>
        ` : ""}

        ${caps.supports_color_temp ? `
          <div class="control-row">
            <span class="control-label">Chaleur (${kelvin}K)</span>
            <input type="range" min="2700" max="6500" value="${kelvin}" class="range-slider ctrl-light-temp" data-dev-id="${dev.id}" />
          </div>
        ` : ""}

        ${caps.supports_color ? `
          <div class="control-row">
            <span class="control-label">Couleur RVB</span>
            <input type="color" value="#ff9900" class="color-picker ctrl-light-color" data-dev-id="${dev.id}" />
          </div>
        ` : ""}
      `;
    }

    // 2. CAMERA CONTROLS
    if (dev.device_type === "camera") {
      const isPrivate = Boolean(dps["105"] || dps["basic_private"]);
      const motionActive = Boolean(dps["134"] || dps["motion_switch"]);
      const targetEntity = dev.linked_camera_entity_id || dev.camera_entity_id;
      const previewSrc = targetEntity ? `/api/camera_proxy/${targetEntity}?t=${Date.now()}` : (dev.icon_url || "");

      return `
        <div class="camera-preview-box">
          <img src="${previewSrc}" class="camera-img" alt="${this._escapeHtml(dev.name)}" onerror="this.onerror=null;this.src='${dev.icon_url || ''}';" />
          <button class="live-stream-btn" data-live-cam="${dev.id}">▶ FLUX DIRECT</button>
        </div>
        <div class="control-row">
          <span class="control-label">Mode privé (veille)</span>
          <label class="toggle-switch">
            <input type="checkbox" class="ctrl-cam-private" data-dev-id="${dev.id}" ${isPrivate ? "checked" : ""} />
            <span class="slider-round"></span>
          </label>
        </div>
        <div class="control-row">
          <span class="control-label">Alerte Mouvement</span>
          <label class="toggle-switch">
            <input type="checkbox" class="ctrl-cam-motion" data-dev-id="${dev.id}" ${motionActive ? "checked" : ""} />
            <span class="slider-round"></span>
          </label>
        </div>
      `;
    }

    // 3. SWITCH / PLUG CONTROLS
    if (dev.device_type === "switch") {
      const isOn = Boolean(dps["1"] || dps["switch"] || dps["switch_1"]);
      const powerW = dps["cur_power"] ? (dps["cur_power"] * 0.1).toFixed(1) : (dps["18"] ? (dps["18"] * 0.1).toFixed(1) : null);
      const voltV = dps["cur_voltage"] ? (dps["cur_voltage"] * 0.1).toFixed(1) : (dps["20"] && !is_bool(dps["20"]) ? (dps["20"] * 0.1).toFixed(1) : null);
      const energyKwh = dps["add_ele"] ? (dps["add_ele"] * 0.01).toFixed(2) : (dps["17"] ? (dps["17"] * 0.01).toFixed(2) : null);

      return `
        <div class="control-row">
          <span class="control-label">Interrupteur</span>
          <label class="toggle-switch">
            <input type="checkbox" class="ctrl-switch-power" data-dev-id="${dev.id}" ${isOn ? "checked" : ""} />
            <span class="slider-round"></span>
          </label>
        </div>

        ${powerW || voltV || energyKwh ? `
          <div class="metrics-grid">
            ${powerW ? `<div class="metric-item"><span class="metric-val">${powerW} W</span><span class="metric-lbl">Puissance</span></div>` : ""}
            ${voltV ? `<div class="metric-item"><span class="metric-val">${voltV} V</span><span class="metric-lbl">Tension</span></div>` : ""}
            ${energyKwh ? `<div class="metric-item"><span class="metric-val">${energyKwh} kWh</span><span class="metric-lbl">Consommation</span></div>` : ""}
          </div>
        ` : ""}
      `;
    }

    // 4. SENSORS & SECURITY
    const temp = dps["va_temperature"] ? (dps["va_temperature"] * 0.1).toFixed(1) : (dps["temp_current"] ? (dps["temp_current"] * 0.1).toFixed(1) : null);
    const hum = dps["va_humidity"] || dps["humidity_value"];
    const bat = dps["battery_percentage"] || dps["battery"];

    return `
      <div class="metrics-grid">
        ${temp ? `<div class="metric-item"><span class="metric-val">${temp} °C</span><span class="metric-lbl">Température</span></div>` : ""}
        ${hum ? `<div class="metric-item"><span class="metric-val">${hum} %</span><span class="metric-lbl">Humidité</span></div>` : ""}
        ${bat ? `<div class="metric-item"><span class="metric-val">${bat} %</span><span class="metric-lbl">Batterie</span></div>` : ""}
      </div>
    `;
  }

  _renderSettingsTab(accounts, profiles) {
    const devices = this._dashboardData.devices || [];

    return `
      <!-- Section 1: Connected Accounts -->
      <div class="glass-panel settings-section">
        <div class="section-title">
          <span>☁️</span> Comptes & Marques Connectés (${accounts.length})
        </div>

        ${accounts.length === 0 ? `
          <p style="color: #8b949e;">Aucun compte configuré. Ajoutez votre premier compte ci-dessous.</p>
        ` : accounts.map((acc) => `
          <div class="account-card">
            <div>
              <div style="font-weight: 700; font-size: 15px; color: #f0f6fc;">${this._escapeHtml(acc.title)}</div>
              <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">
                Mode: <b>${this._escapeHtml(acc.mode)}</b> | Appareils actifs: <b>${acc.device_count}</b>
              </div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="btn-action btn-sync-account" data-entry-id="${acc.entry_id}">🔄 Synchroniser</button>
              <button class="btn-action danger btn-remove-account" data-entry-id="${acc.entry_id}">🗑️ Supprimer</button>
            </div>
          </div>
        `).join("")}
      </div>

      <!-- Section 2: Add New Account Form -->
      <div class="glass-panel settings-section">
        <div class="section-title">
          <span>➕</span> Ajouter un Compte Mobile (Thank's, Tuya, Smart Life, Lidl...)
        </div>

        <form id="form-add-account">
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Marque / Écosystème</label>
              <select class="form-select" id="new-account-brand">
                ${profiles.map((p) => `
                  <option value="${p.key}">${p.name}</option>
                `).join("")}
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">Email / Identifiant</label>
              <input type="text" class="form-input" id="new-account-user" placeholder="ex: mon-email@domaine.com" required />
            </div>

            <div class="form-group">
              <label class="form-label">Mot de passe</label>
              <input type="password" class="form-input" id="new-account-pass" placeholder="Mot de passe de l'application" required />
            </div>

            <div class="form-group">
              <label class="form-label">Indicatif Pays (ex: 33 pour France)</label>
              <input type="text" class="form-input" id="new-account-cc" value="33" />
            </div>
          </div>

          <button type="submit" class="btn-action primary" style="padding: 10px 20px;">
            ${this._isAddingAccount ? "Connexion en cours..." : "🚀 Connecter le compte"}
          </button>
        </form>
      </div>

      <!-- Section 3: Device Management Table -->
      <div class="glass-panel settings-section">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <div class="section-title" style="margin-bottom: 0;">
            <span>🛠️</span> Gestion & Personnalisation des Appareils
          </div>
          <button class="btn-action" id="btn-scan-lan">
            ${this._isScanning ? "📡 Scan en cours..." : "📡 Scanner le réseau local LAN"}
          </button>
        </div>

        <div style="overflow-x: auto;">
          <table class="device-manage-table">
            <thead>
              <tr>
                <th>Appareil</th>
                <th>Nom personnalisé</th>
                <th>Type forcé</th>
                <th>IP LAN (Locale)</th>
                <th>Flux RTSP / Caméra HA</th>
                <th>Clé locale (AES)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${devices.map((dev) => `
                <tr data-manage-id="${dev.id}">
                  <td>
                    <div style="font-weight: 700; color: #f0f6fc;">${this._escapeHtml(dev.name)}</div>
                    <div style="font-size: 11px; color: #8b949e;">ID: ${dev.id}</div>
                  </td>
                  <td>
                    <input type="text" class="form-input input-custom-name" style="width: 130px;" value="${this._escapeHtml(dev.name)}" />
                  </td>
                  <td>
                    <select class="form-select select-forced-type" style="width: 120px;">
                      <option value="" ${dev.device_type === "" ? "selected" : ""}>Automatique</option>
                      <option value="light" ${dev.device_type === "light" ? "selected" : ""}>Éclairage</option>
                      <option value="switch" ${dev.device_type === "switch" ? "selected" : ""}>Prise / Switch</option>
                      <option value="camera" ${dev.device_type === "camera" ? "selected" : ""}>Caméra</option>
                      <option value="sensor" ${dev.device_type === "sensor" ? "selected" : ""}>Capteur</option>
                      <option value="security" ${dev.device_type === "security" ? "selected" : ""}>Sécurité</option>
                      <option value="climate" ${dev.device_type === "climate" ? "selected" : ""}>Climatisation</option>
                      <option value="cover" ${dev.device_type === "cover" ? "selected" : ""}>Volet</option>
                    </select>
                  </td>
                  <td>
                    <input type="text" class="form-input input-ip" style="width: 105px;" value="${this._escapeHtml(dev.ip || "")}" placeholder="192.168.1.X" />
                    ${dev.wan_ip ? `<div style="font-size: 10px; color: #8b949e;" title="IP Publique WAN box">WAN: ${this._escapeHtml(dev.wan_ip)}</div>` : ""}
                  </td>
                  <td>
                    <input type="text" class="form-input input-rtsp" style="width: 130px;" value="${this._escapeHtml(dev.rtsp_url || dev.linked_camera_entity_id || "")}" placeholder="rtsp:// ou camera.xxx" />
                  </td>
                  <td>
                    <span style="font-family: monospace; font-size: 11px; color: #8b949e;">${dev.local_key ? dev.local_key.substring(0, 8) + "..." : "Non extraite"}</span>
                  </td>
                  <td>
                    <button class="btn-action btn-save-device-meta" data-dev-id="${dev.id}">💾 Sauvegarder</button>
                  </td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    const root = this.shadowRoot;

    // Tab Navigation
    const tabDevices = root.querySelector("#tab-devices");
    const tabSettings = root.querySelector("#tab-settings");
    if (tabDevices) {
      tabDevices.onclick = () => {
        this._activeTab = "devices";
        this.render();
      };
    }
    if (tabSettings) {
      tabSettings.onclick = () => {
        this._activeTab = "settings";
        this.render();
      };
    }

    // Stats Online / Offline Filter Toggles
    const filterOnline = root.querySelector("#stat-filter-online");
    if (filterOnline) {
      filterOnline.onclick = () => {
        this._showOnline = !this._showOnline;
        this.render();
      };
    }

    const filterOffline = root.querySelector("#stat-filter-offline");
    if (filterOffline) {
      filterOffline.onclick = () => {
        this._showOffline = !this._showOffline;
        this.render();
      };
    }

    const filterTotal = root.querySelector("#stat-filter-total");
    if (filterTotal) {
      filterTotal.onclick = () => {
        this._showOnline = true;
        this._showOffline = true;
        this._selectedCategory = "all";
        this.render();
      };
    }

    // Category Filter Pills
    root.querySelectorAll(".pill").forEach((pill) => {
      pill.onclick = () => {
        this._selectedCategory = pill.dataset.cat;
        this.render();
      };
    });

    // Search Input
    const searchInput = root.querySelector("#search-devices");
    if (searchInput) {
      searchInput.oninput = (e) => {
        this._searchQuery = e.target.value;
        const grid = root.querySelector(".device-grid");
        if (grid) {
          const filtered = this._filterDevices(this._dashboardData.devices || []);
          grid.innerHTML = filtered.map((d) => this._renderDeviceCard(d)).join("");
          this._bindDynamicControls();
        }
      };
    }

    this._bindDynamicControls();

    // Settings Tab Handlers
    const formAdd = root.querySelector("#form-add-account");
    if (formAdd) {
      formAdd.onsubmit = (e) => {
        e.preventDefault();
        const brand = root.querySelector("#new-account-brand").value;
        const user = root.querySelector("#new-account-user").value;
        const pass = root.querySelector("#new-account-pass").value;
        const cc = root.querySelector("#new-account-cc").value;
        this._addAccount(brand, user, pass, cc);
      };
    }

    // Scan LAN button
    const btnScan = root.querySelector("#btn-scan-lan");
    if (btnScan) {
      btnScan.onclick = () => this._scanLan();
    }

    // Account sync and remove buttons
    root.querySelectorAll(".btn-sync-account").forEach((btn) => {
      btn.onclick = () => this._fetchDashboard(true);
    });
    root.querySelectorAll(".btn-remove-account").forEach((btn) => {
      btn.onclick = () => this._removeAccount(btn.dataset.entryId);
    });

    // Save device metadata rows
    root.querySelectorAll(".btn-save-device-meta").forEach((btn) => {
      btn.onclick = () => {
        const devId = btn.dataset.devId;
        const row = root.querySelector(`tr[data-manage-id="${devId}"]`);
        if (row) {
          const customName = row.querySelector(".input-custom-name").value;
          const forcedType = row.querySelector(".select-forced-type").value;
          const ip = row.querySelector(".input-ip").value;
          const rtsp = row.querySelector(".input-rtsp") ? row.querySelector(".input-rtsp").value : "";
          this._updateDeviceMeta(devId, customName, forcedType, ip, rtsp);
        }
      };
    });
  }

  _bindDynamicControls() {
    const root = this.shadowRoot;

    // Live Camera Stream Buttons
    root.querySelectorAll("[data-live-cam]").forEach((btn) => {
      btn.onclick = () => {
        const devId = btn.dataset.liveCam;
        const devices = (this._dashboardData && this._dashboardData.devices) || [];
        const dev = devices.find((d) => d.id === devId);
        if (!dev) return;
        const targetEntity = dev.linked_camera_entity_id || dev.camera_entity_id;
        if (targetEntity) {
          this.dispatchEvent(new CustomEvent("hass-more-info", {
            detail: { entityId: targetEntity },
            bubbles: true,
            composed: true,
          }));
        } else if (dev.rtsp_url) {
          window.open(dev.rtsp_url, "_blank");
        } else {
          this._showToast("⚠️ Aucun flux caméra associé trouvé");
        }
      };
    });

    // DP Inspector toggles
    root.querySelectorAll("[data-toggle-dps]").forEach((btn) => {
      btn.onclick = () => {
        const devId = btn.dataset.toggleDps;
        if (this._expandedDps.has(devId)) {
          this._expandedDps.delete(devId);
        } else {
          this._expandedDps.add(devId);
        }
        this.render();
      };
    });

    // Light Power Toggles
    root.querySelectorAll(".ctrl-light-power").forEach((chk) => {
      chk.onchange = () => {
        this._sendDpAction(chk.dataset.devId, chk.checked ? "turn_on" : "turn_off");
      };
    });

    // Light Brightness Sliders
    root.querySelectorAll(".ctrl-light-bright").forEach((rng) => {
      rng.onchange = () => {
        this._sendDpAction(rng.dataset.devId, "set_brightness", { brightness: Number(rng.value) });
      };
    });

    // Light Color Temp Sliders
    root.querySelectorAll(".ctrl-light-temp").forEach((rng) => {
      rng.onchange = () => {
        this._sendDpAction(rng.dataset.devId, "set_color_temp", { kelvin: Number(rng.value) });
      };
    });

    // Light RGB Pickers
    root.querySelectorAll(".ctrl-light-color").forEach((picker) => {
      picker.onchange = () => {
        this._sendDpAction(picker.dataset.devId, "set_color", { hex: picker.value });
      };
    });

    // Switch Power Toggles
    root.querySelectorAll(".ctrl-switch-power").forEach((chk) => {
      chk.onchange = () => {
        this._sendDpAction(chk.dataset.devId, chk.checked ? "turn_on" : "turn_off");
      };
    });

    // Camera Private Toggles
    root.querySelectorAll(".ctrl-cam-private").forEach((chk) => {
      chk.onchange = () => {
        this._sendRawDp(chk.dataset.devId, "105", chk.checked);
      };
    });

    // Camera Motion Toggles
    root.querySelectorAll(".ctrl-cam-motion").forEach((chk) => {
      chk.onchange = () => {
        this._sendRawDp(chk.dataset.devId, "134", chk.checked);
      };
    });
  }
}

function is_bool(val) {
  return typeof val === "boolean";
}

customElements.define("domolink-tuya-panel", DomolinkTuyaPanel);
