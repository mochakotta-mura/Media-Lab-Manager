const historyApiReady = window.mlmApi ? Promise.resolve() : new Promise(resolve => { const s = document.createElement('script'); s.src = '../js/api.js'; s.onload = resolve; document.head.appendChild(s); });
historyApiReady.then(async () => {
  const tbody = document.querySelector('#historyRows'); const user = mlmApi.currentUser();
  const format = value => value ? new Date(value).toLocaleString() : '—';
  try {
    if (!user?.id) throw new Error('Sign in before viewing booking history.');
    const result = await mlmApi.requests(`?requesterId=${encodeURIComponent(user.id)}`); const rows = Array.isArray(result) ? result : (result.requests || []);
    tbody.innerHTML = rows.map(request => `<tr><td><b>${request.id}</b></td><td>${(request.items || []).map(item => item.name || item.equipment_id).join(', ')}</td><td>${format(request.windows?.find(x => x.kind === 'pickup')?.starts_at)}</td><td>${format(request.windows?.find(x => x.kind === 'return')?.ends_at)}</td><td><span class="status ${request.status}">${request.status}</span></td><td><a href="return.html?request=${request.id}">View Details</a> ${['approved','pickup_pending','picked_up'].includes(request.status) ? `<button class="extend" data-id="${request.id}">Extend</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="6">No requests found.</td></tr>';
    document.querySelectorAll('.extend').forEach(button => button.onclick = async () => { const startsAt = prompt('Requested extension start (ISO-8601)', new Date().toISOString()); const endsAt = prompt('Requested extension end (ISO-8601)'); if (!startsAt || !endsAt) return; try { await mlmApi.extension({ requestId: Number(button.dataset.id), startsAt, endsAt, actorId: Number(user.id), notes: 'Requested from booking history' }); alert('Extension request submitted.'); } catch (error) { mlmUiError(error.message); } });
  } catch (error) { tbody.innerHTML = `<tr><td colspan="6">${error.message}</td></tr>`; }
});
