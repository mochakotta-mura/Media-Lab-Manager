const profileApiReady = window.mlmApi ? Promise.resolve() : new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = '../js/api.js'; script.onload = resolve; script.onerror = reject; document.head.appendChild(script); });
profileApiReady.then(() => window.mlmSessionReady).then(() => mlmSession.requireAuth()).then(async currentUser => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const format = value => value ? new Date(value).toLocaleString() : '—';
  const isStaff = mlmSession.isStaff(currentUser); const params = new URLSearchParams(location.search); let selected = currentUser;
  const select = document.querySelector('#profileUser');
  try {
    if (isStaff) {
      const users = await mlmApi.users();
      select.innerHTML = users.map(user => `<option value="${user.id}">${esc(user.name || user.email)} — ${esc(user.email)}</option>`).join('');
      document.querySelector('#staffLookup').style.display = 'block';
      const requestedId = Number(params.get('userId')); if (requestedId && users.some(user => Number(user.id) === requestedId)) select.value = String(requestedId);
      selected = users.find(user => Number(user.id) === Number(select.value)) || currentUser;
      select.onchange = () => { location.href = `profile.html?userId=${encodeURIComponent(select.value)}`; };
    }
    document.querySelector('#profileName').textContent = selected.name || selected.email;
    document.querySelector('#profileEmail').textContent = selected.email || '';
    document.querySelector('#profileRole').textContent = `Role: ${selected.role || 'student'}`;
    document.querySelector('#bookingTitle').textContent = `${selected.name || selected.email} — past bookings`;
    const result = await mlmApi.requests(`?requesterId=${encodeURIComponent(selected.id)}`); const requests = Array.isArray(result) ? result : (result.requests || []);
    const rows = document.querySelector('#profileBookings');
    rows.innerHTML = requests.map(request => `<tr><td><b>${request.id}</b></td><td>${esc((request.items || []).map(item => item.name || item.equipment_id).join(', '))}</td><td>${format(request.windows?.find(window => window.kind === 'pickup')?.starts_at)}</td><td>${format(request.windows?.find(window => window.kind === 'return')?.ends_at)}</td><td><span class="status ${esc(request.status)}">${esc(request.status)}</span></td><td><a href="return.html?request=${request.id}">View Details</a></td></tr>`).join('') || '<tr><td colspan="6">No bookings found.</td></tr>';
    document.querySelector('#bookingSummary').textContent = `${requests.length} booking${requests.length === 1 ? '' : 's'} found.`;
  } catch (error) { document.querySelector('#bookingSummary').textContent = error.message; }
});
