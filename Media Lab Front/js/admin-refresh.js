(async function () {
  const list = document.querySelector('#requestList');
  if (!list) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const render = requests => {
    list.innerHTML = requests.map(x => `<article class="request-card"><div class="request-head"><div><h2>Request #${x.id}</h2><p>${esc(x.requester_name || '')}</p></div><span class="status pending">pending</span></div><div class="request-details"><article><b>Equipment</b><p>${(x.items || []).map(i => esc(i.name || i.equipment_id)).join(', ')}</p></article><article><b>Purpose</b><p>${esc(x.purpose)}</p></article></div><div class="request-actions"><button class="reject" data-refresh-action="reject" data-id="${x.id}">Reject</button><button class="primary" data-refresh-action="approve" data-id="${x.id}">Approve</button></div></article>`).join('') || '<p>No pending requests.</p>';
    list.querySelectorAll('[data-refresh-action]').forEach(button => button.onclick = async () => {
      try {
        if (button.dataset.refreshAction === 'approve') await mlmApi.approveRequest(button.dataset.id);
        else await mlmApi.rejectRequest(button.dataset.id, undefined, prompt('Reason for rejection') || '');
        await load();
      } catch (error) { mlmUiError(error.message); }
    });
  };
  const load = async () => {
    try { const result = await mlmApi.requests('?status=pending'); render(Array.isArray(result) ? result : (result.requests || [])); }
    catch (error) { if (error.message) mlmUiError(error.message); }
  };
  const start = async () => { await load(); let button = document.querySelector('[data-refresh-requests]'); if (!button) { button = document.createElement('button'); button.className = 'outline'; button.dataset.refreshRequests = 'true'; button.textContent = 'Refresh requests'; document.querySelector('.page-heading')?.appendChild(button); } button.onclick = load; window.setInterval(load, 10000); };
  if (window.mlmApi) start(); else window.addEventListener('load', start, { once: true });
})();
