/**
 * LandRecord AI - Runtime Configuration
 * Can be overridden in production or staging deployments.
 */
window.__APP_CONFIG__ = Object.assign({
  // Deployment configuration. Override this value at build/deploy time if the
  // Render service receives a different public URL. It must not point to a
  // test server or browser-local fallback in production.
  API_BASE_URL: (typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'))
    ? 'http://localhost:8000'
    : 'https://land-record-backend.onrender.com'
}, window.__APP_CONFIG__ || {});
