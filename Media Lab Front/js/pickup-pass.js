(async function () {
  if (!window.mlmApi) await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = '../js/api.js'; script.onload = resolve; script.onerror = reject; document.head.appendChild(script); });
  await window.mlmSessionReady;
  await mlmSession.requireAuth();
  document.querySelectorAll('.pass-grid > div b').forEach(field => { field.textContent = 'Loading…'; });
  document.querySelector('#passEquipment').innerHTML = '<li>Loading…</li>';
  const id = Number(new URLSearchParams(location.search).get('booking'));
  try {
    const data = await mlmApi.requests();
    const request = (Array.isArray(data) ? data : (data.requests || [])).find(item => Number(item.id) === id);
    if (!request) throw new Error('Booking not found.');
    const user = await mlmApi.me().then(result => result.user);
    const pickup = request.windows?.find(window => window.kind === 'pickup');
    const returned = request.windows?.find(window => window.kind === 'return');
    const ownerName = request.requester_name || user.name;
    const fields = document.querySelectorAll('.pass-grid > div b');
    fields[0].textContent = ownerName;
    fields[1].textContent = `#${request.id}`;
    fields[2].textContent = pickup ? `${new Date(pickup.starts_at).toLocaleString()} – ${new Date(pickup.ends_at).toLocaleTimeString()}` : 'Not scheduled';
    fields[3].textContent = returned ? new Date(returned.ends_at).toLocaleString() : 'Not scheduled';
    document.querySelector('#passEquipment').innerHTML = (request.items || []).map(item => `<li>${item.name || item.equipment_id}</li>`).join('');
    if (mlmSession.isStaff(user) && Number(request.requester_id) !== Number(user.id)) document.querySelector('.pass-note').textContent = `Staff view: verify pickup for ${ownerName} before releasing the equipment.`;
    document.querySelector('.pass-code').textContent = `MLM · #${request.id} · ${user.name.toUpperCase()}`;
  } catch (error) { document.querySelector('.pass').innerHTML = `<p>${error.message}</p>`; }
})();
