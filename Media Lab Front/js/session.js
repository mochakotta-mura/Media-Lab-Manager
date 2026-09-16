/* Shared session and role gate. Pages load this before page-specific code. */
(function () {
  const STAFF_ROLES = new Set(['faculty', 'media_lab', 'staff', 'admin']);
  let userPromise;
  let currentUser = null;
  const isLoginPage = /\/index\.html$|\/$/.test(location.pathname);
  const redirect = target => { if (location.pathname !== target) location.replace(target); };
  async function getCurrentUser() {
    if (!userPromise) userPromise = window.mlmApi.me().then(data => { currentUser = data.user || null; return currentUser; }).catch(() => { currentUser = null; return null; });
    return userPromise;
  }
  function isStaff(user = currentUser) { return Boolean(user && STAFF_ROLES.has(user.role)); }
  function isAdmin(user = currentUser) { return Boolean(user && user.role === 'admin'); }
  async function requireAuth() {
    const user = await getCurrentUser();
    if (!user) { redirect('/'); throw new Error('Authentication required'); }
    return user;
  }
  async function requireStaff() {
    const user = await requireAuth();
    if (!isStaff(user)) { redirect('/pages/catalog.html'); throw new Error('Staff access required'); }
    return user;
  }
  async function requireAdmin() {
    const user = await requireAuth();
    if (!isAdmin(user)) { redirect('/pages/catalog.html'); throw new Error('Administrator access required'); }
    return user;
  }
  window.mlmSession = { getCurrentUser, currentUser: () => currentUser, isStaff, isAdmin, requireAuth, requireStaff, requireAdmin };
  if (!isLoginPage) {
    document.documentElement.classList.add('session-pending');
    document.documentElement.style.visibility = 'hidden';
    const required = document.body.dataset.requireRole || (location.pathname.includes('/admin/settings') ? 'admin' : location.pathname.includes('/admin/') ? 'staff' : 'auth');
    const gate = required === 'admin' ? requireAdmin() : required === 'staff' ? requireStaff() : requireAuth();
    window.mlmGateReady = gate;
  }
  const navScript = document.createElement('script');
  navScript.src = new URL('nav.js', document.currentScript?.src || location.href).href;
  window.mlmNavReady = new Promise(resolve => { navScript.onload = resolve; navScript.onerror = resolve; document.head.appendChild(navScript); });
  if (/\/pages\/admin\/requests\.html$/.test(location.pathname)) {
    const refreshScript = document.createElement('script');
    refreshScript.src = new URL('admin-refresh.js', document.currentScript?.src || location.href).href;
    document.head.appendChild(refreshScript);
  }
  if (!isLoginPage) Promise.all([window.mlmGateReady, window.mlmNavReady]).finally(() => { document.documentElement.classList.remove('session-pending'); document.documentElement.style.visibility = ''; });
})();
