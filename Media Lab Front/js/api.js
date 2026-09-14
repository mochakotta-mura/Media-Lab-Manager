/* HTTP adapter for the database module. The browser must talk to an API
   service which imports MLM.Database.Commands.js; it must never open SQLite. */
(function () {
  const base = (window.MLM_API_BASE || localStorage.getItem('mlmApiBase') || '/api').replace(/\/$/, '');
  async function call(path, options = {}) {
    const response = await fetch(base + path, {
      // Development backend has placeholder authentication; avoid credentialed
      // CORS so the static file frontend can call localhost directly.
      credentials: 'omit',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
      body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error || payload?.message || `Request failed (${response.status})`);
    return payload;
  }
  const json = (method, path, body) => call(path, { method, body });
  window.mlmApi = {
    base,
    currentUser: () => JSON.parse(localStorage.getItem('mlmUser') || 'null'),
    createUser: body => json('POST', '/users', body),
    equipment: (filters = {}) => call('/equipment?' + new URLSearchParams(filters)),
    stats: () => call('/equipment/stats'),
    createRequest: body => json('POST', '/requests', body),
    requests: (query = '') => call('/requests' + query),
    approveRequest: (id, actorId, notes) => json('POST', `/requests/${id}/approve`, { actorId, notes }),
    rejectRequest: (id, actorId, reason) => json('POST', `/requests/${id}/reject`, { actorId, reason }),
    cancelRequest: (id, actorId) => json('POST', `/requests/${id}/cancel`, { actorId }),
    scheduleWindow: body => json('POST', `/requests/${body.requestId}/windows`, body),
    pickup: (id, body) => json('POST', `/requests/${id}/pickup`, body),
    return: (id, body) => json('POST', `/requests/${id}/return`, body),
    damage: body => json('POST', `/request-items/${body.requestItemId}/damage`, body),
    extension: body => json('POST', `/requests/${body.requestId}/extensions`, body),
    dashboard: () => call('/dashboard'),
    audit: (type, id) => call(`/audit/${encodeURIComponent(type)}/${id}`),
    outbox: () => call('/outbox')
  };
  window.mlmUiError = message => {
    const toast = document.querySelector('#toast');
    if (toast) { toast.textContent = message; toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 3500); }
    else console.error(message);
  };
})();
