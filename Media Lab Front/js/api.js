/* Same-origin adapter for the single Python backend. Authentication is
   cookie-only: the session value never enters localStorage or sessionStorage. */
(function () {
  const base = (window.MLM_API_BASE || '/api').replace(/\/$/, '');
  let userCache = null;
  try { userCache = JSON.parse(sessionStorage.getItem('mlmUser') || 'null'); } catch {}
  function redirectToLogin() {
    if (!/\/index\.html$|\/$/.test(location.pathname)) location.replace('/');
  }
  async function call(path, options = {}) {
    const method = String(options.method || 'GET').toUpperCase();
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) headers['X-MLM-CSRF'] = '1';
    const response = await fetch(base + path, { credentials: 'include', ...options, method, headers,
      body: options.body && typeof options.body !== 'string' ? JSON.stringify(options.body) : options.body });
    const data = await response.json().catch(() => null);
    if (response.status === 401) {
      userCache = null;
      try { sessionStorage.removeItem('mlmUser'); } catch {}
      redirectToLogin();
    }
    if (!response.ok) throw new Error(data?.error || data?.message || `Request failed (${response.status})`);
    return data;
  }
  const json = (method, path, body) => call(path, { method, body });
  window.mlmApi = {
    base,
    login: body => json('POST', '/auth/login', { email: body.email, pin: body.pin }).then(data => {
      userCache = data.user || null;
      try { sessionStorage.setItem('mlmUser', JSON.stringify(userCache)); } catch {}
      return data;
    }),
    logout: () => json('POST', '/auth/logout').finally(() => { userCache = null; try { sessionStorage.removeItem('mlmUser'); } catch {} }),
    me: () => call('/auth/me').then(data => { userCache = data.user || null; try { sessionStorage.setItem('mlmUser', JSON.stringify(userCache)); } catch {} return data; }),
    currentUser: () => userCache,
    createUser: body => json('POST', '/users', body),
    users: () => call('/users'),
    equipment: (filters = {}) => call('/equipment?' + new URLSearchParams(filters)),
    addEquipment: body => json('POST', '/equipment', body),
    updateEquipment: (id, body) => call(`/equipment/${id}`, { method: 'PATCH', body }),
    stats: () => call('/equipment/stats'),
    createRequest: body => json('POST', '/requests', body),
    requests: (query = '') => call('/requests' + query),
    approveRequest: (id, _actorId, notes) => json('POST', `/requests/${id}/approve`, { notes }),
    rejectRequest: (id, _actorId, reason) => json('POST', `/requests/${id}/reject`, { reason }),
    cancelRequest: (id, _actorId) => json('POST', `/requests/${id}/cancel`, {}),
    scheduleWindow: body => json('POST', `/requests/${body.requestId}/windows`, body),
    pickup: (id, body) => json('POST', `/requests/${id}/pickup`, body),
    return: (id, body) => json('POST', `/requests/${id}/return`, body),
    damage: body => json('POST', `/request-items/${body.requestItemId}/damage`, body),
    extension: body => json('POST', `/requests/${body.requestId}/extensions`, body),
    dashboard: () => call('/dashboard'),
    audit: (type, id) => call(`/audit/${encodeURIComponent(type)}/${id}`),
    outbox: () => call('/outbox'),
    settings: () => call('/settings'),
    updateSettings: body => call('/settings', { method: 'PATCH', body })
  };
  window.mlmUiError = message => { const toast = document.querySelector('#toast'); if (toast) { toast.textContent = message; toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 3500); } else console.error(message); };
  window.mlmSessionReady = new Promise((resolve, reject) => {
    if (window.mlmSession) return resolve();
    const script = document.createElement('script');
    script.src = new URL('session.js', document.currentScript?.src || location.href).href;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
})();
