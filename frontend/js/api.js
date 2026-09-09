/**
 * LandRecord AI - Unified API Client
 * Connects frontend UI to the FastAPI backend with configurable API_BASE_URL.
 */
(function () {
  // 1. Resolve API Base URL
  // The deploy-time runtime configuration is the single source of truth.
  function resolveApiBaseUrl() {
    if (typeof window === 'undefined') return 'http://localhost:8000';
    if (window.__APP_CONFIG__ && window.__APP_CONFIG__.API_BASE_URL) {
      return window.__APP_CONFIG__.API_BASE_URL.replace(/\/+$/, '');
    }
    const isLocal =
      window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1' ||
      window.location.protocol === 'file:';

    return isLocal ? 'http://localhost:8000' : 'https://land-record-backend.onrender.com';
  }

  // 2. HTTP Helper
  async function request(path, options = {}) {
    const baseUrl = resolveApiBaseUrl();
    const url = `${baseUrl}${path}`;
    const headers = Object.assign({}, options.headers || {});

    if (options.body && !(options.body instanceof FormData) && typeof options.body === 'object') {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    const response = await fetch(url, {
      ...options,
      headers
    });

    if (response.status === 204) {
      return null;
    }

    let payload;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      payload = await response.text();
    }

    if (!response.ok) {
      const message =
        (payload && typeof payload === 'object' && (payload.detail || payload.message)) ||
        `Request failed with status ${response.status}`;
      const err = new Error(typeof message === 'string' ? message : JSON.stringify(message));
      err.status = response.status;
      err.payload = payload;
      throw err;
    }

    return payload;
  }

  // 3. API Client Definition
  const apiClient = {
    getBaseUrl: resolveApiBaseUrl,

    setBaseUrl(url) {
      const clean = (url || '').replace(/\/+$/, '');
      if (window.__APP_CONFIG__) window.__APP_CONFIG__.API_BASE_URL = clean;
    },

    // Health check
    async health() {
      return request('/health', { method: 'GET' });
    },

    // Upload document & execute full OCR pipeline
    async uploadAndProcess(file, language = 'eng') {
      const formData = new FormData();
      formData.append('document', file);
      formData.append('language', language);
      return request('/api/v1/records/process', {
        method: 'POST',
        body: formData
      });
    },

    // List persisted records
    async listRecords(limit = 50, offset = 0) {
      return request(`/api/v1/records?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`, {
        method: 'GET'
      });
    },

    // Get a specific land record
    async getRecord(recordId) {
      return request(`/api/v1/records/${encodeURIComponent(recordId)}`, {
        method: 'GET'
      });
    },

    // Create a new record directly
    async createRecord(recordData) {
      return request('/api/v1/records', {
        method: 'POST',
        body: recordData
      });
    },

    // Partially update a record
    async updateRecord(recordId, updateData) {
      return request(`/api/v1/records/${encodeURIComponent(recordId)}`, {
        method: 'PATCH',
        body: updateData
      });
    },

    // Delete a record
    async deleteRecord(recordId) {
      return request(`/api/v1/records/${encodeURIComponent(recordId)}`, {
        method: 'DELETE'
      });
    }
  };

  // Expose globally
  window.apiClient = apiClient;
  window.api = apiClient;
})();
