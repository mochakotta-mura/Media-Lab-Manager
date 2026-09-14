/* Shared API adapter. Authentication adds a bearer token without removing
   the existing equipment, request, dashboard, audit, or outbox methods. */
(function () {
  const storage = (() => { try { const key = 'mlmStorageTest'; localStorage.setItem(key, '1'); localStorage.removeItem(key); return localStorage; } catch { return { getItem: () => null, setItem: () => {}, removeItem: () => {} }; } })();
  const base = (window.MLM_API_BASE || storage.getItem('mlmApiBase') || '/api').replace(/\/$/, '');
  async function call(path, options = {}) {
    const token = storage.getItem('mlmSessionToken');
    const response = await fetch(base + path, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
      ...options,
      body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.error || data?.message || `Request failed (${response.status})`);
    return data;
  }
  const json = (method, path, body) => call(path, { method, body });
  window.mlmApi = {
    base,
    login: body => json('POST', '/auth/login', body).then(data => { if (data.sessionToken) storage.setItem('mlmSessionToken', data.sessionToken); if (data.user) storage.setItem('mlmUser', JSON.stringify(data.user)); return data; }),
    logout: () => json('POST', '/auth/logout').finally(() => { storage.removeItem('mlmSessionToken'); storage.removeItem('mlmUser'); }),
    me: () => call('/auth/me'),
    currentUser: () => JSON.parse(storage.getItem('mlmUser') || 'null'),
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
  window.mlmUiError = message => { const toast = document.querySelector('#toast'); if (toast) { toast.textContent = message; toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 3500); } else console.error(message); };
})();
