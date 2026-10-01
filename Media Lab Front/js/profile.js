const profileApiReady = window.mlmApi ? Promise.resolve() : new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = '../js/api.js'; script.onload = resolve; script.onerror = reject; document.head.appendChild(script); });
profileApiReady.then(() => window.mlmSessionReady).then(() => mlmSession.requireAuth()).then(async currentUser => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const format = value => value ? new Date(value).toLocaleString() : '—';
  // Only administrators may inspect another user's profile. Faculty and all
  // other roles are regular users for this view and are always scoped to their
  // own booking history, regardless of a userId query parameter.
  const canBrowseOthers = mlmSession.isAdmin(currentUser); const params = new URLSearchParams(location.search); let selected = currentUser;
  const select = document.querySelector('#profileUser');
  try {
    if (canBrowseOthers) {
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
    document.querySelector('#bookingTitle').textContent = `${selected.name || selected.email} — Bookings`;
    const result = await mlmApi.requests(`?requesterId=${encodeURIComponent(selected.id)}`); const requests = Array.isArray(result) ? result : (result.requests || []);
    const rows = document.querySelector('#profileBookings');
    const pickupWindow = request => [...(request.windows || [])].reverse().find(window => window.kind === 'pickup' && ['approved', 'accepted', 'rejected'].includes(window.status));
    const openPickupDecision = (request, pickup) => { const overlay = document.createElement('div'); overlay.style.cssText = 'position:fixed;inset:0;background:#121b317a;z-index:20;display:grid;place-items:center;padding:20px'; overlay.innerHTML = `<section class="card" style="max-width:460px;width:100%;padding:26px"><h2>Pickup pending</h2><p>Admin offered this pickup slot:</p><p><b>${esc(format(pickup.starts_at))} – ${esc(format(pickup.ends_at))}</b></p><p>Accept this time slot?</p><div style="display:flex;justify-content:flex-end;gap:10px"><button class="outline" data-pickup-close>Cancel</button><button class="outline" data-pickup-reject>Reject</button><button class="primary" data-pickup-accept>Accept</button></div></section>`; document.body.appendChild(overlay); const close = () => overlay.remove(); overlay.querySelector('[data-pickup-close]').onclick = close; overlay.querySelector('[data-pickup-accept]').onclick = async () => { try { await mlmApi.respondPickupSlot(request.id, 'accepted'); close(); location.reload(); } catch (error) { mlmUiError(error.message); } }; overlay.querySelector('[data-pickup-reject]').onclick = async () => { try { await mlmApi.respondPickupSlot(request.id, 'rejected', 'Student could not attend the assigned pickup slot.'); close(); alert('Pickup time rejected. Please email demo.admin to arrange a new pickup time.'); location.reload(); } catch (error) { mlmUiError(error.message); } }; };
    rows.innerHTML = requests.map(request => { const pickup = pickupWindow(request); const canRespond = Number(selected.id) === Number(currentUser.id) && request.status === 'pickup_pending' && pickup?.status === 'approved'; const pickupCell = canRespond ? `<button class="status pickup_pending" data-pickup-request="${request.id}">Pickup pending</button>` : `<span class="status ${esc(request.status)}">${esc(request.status === 'pickup_pending' ? `Pickup ${pickup?.status || 'pending'}` : request.status)}</span>`; return `<tr><td><b>${request.id}</b></td><td>${esc((request.items || []).map(item => item.name || item.equipment_id).join(', '))}</td><td>${format(request.windows?.find(window => window.kind === 'pickup' && window.status === 'requested')?.starts_at)}</td><td>${format(request.windows?.find(window => window.kind === 'return')?.ends_at)}</td><td>${pickupCell}</td><td><a href="return.html?request=${request.id}&from=profile">Return &amp; Damage</a></td></tr>`; }).join('') || '<tr><td colspan="6">No bookings found.</td></tr>';
    rows.querySelectorAll('[data-pickup-request]').forEach(button => { const request = requests.find(item => Number(item.id) === Number(button.dataset.pickupRequest)); const pickup = request && pickupWindow(request); if (request && pickup) button.onclick = () => openPickupDecision(request, pickup); });
    document.querySelector('#bookingSummary').textContent = `${requests.length} booking${requests.length === 1 ? '' : 's'} found.`;
  } catch (error) { document.querySelector('#bookingSummary').textContent = error.message; }
});
