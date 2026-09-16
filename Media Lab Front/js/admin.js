const adminApiReady = window.mlmApi ? Promise.resolve() : new Promise(resolve => { const s = document.createElement('script'); s.src = '../../js/api.js'; s.onload = resolve; document.head.appendChild(s); });
adminApiReady.then(() => window.mlmSessionReady).then(() => mlmSession.requireStaff()).then(async user => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  if (document.querySelector('#equipmentRows')) {
    const render = async () => {
      const result = await mlmApi.equipment({ limit: 1000 });
      const items = Array.isArray(result) ? result : (result.equipment || result.items || []);
      document.querySelector('#equipmentRows').innerHTML = items.map(x => `<tr><td><b>${esc(x.name)}</b></td><td>${esc(x.category || '—')}</td><td>${esc(x.serial_number || x.serialNumber || '—')}</td><td>1</td><td>${x.status === 'available' ? 1 : 0}</td><td>${x.status === 'picked_up' ? 1 : 0}</td><td><span class="status ${esc(x.status)}">${esc(x.status)}</span></td><td><button class="outline" data-edit-equipment="${x.id}">Edit</button></td></tr>`).join('') || '<tr><td colspan="8">No equipment found.</td></tr>';
      document.querySelectorAll('[data-edit-equipment]').forEach(button => button.onclick = async () => {
        const item = items.find(x => Number(x.id) === Number(button.dataset.editEquipment));
        const name = prompt('Equipment name', item.name); if (!name) return;
        const status = prompt('Status', item.status) || item.status;
        try { await mlmApi.updateEquipment(item.id, { name, status }); await render(); } catch (error) { mlmUiError(error.message); }
      });
    };
    try { await render(); const add = document.querySelector('.page-heading .primary'); if (add) add.onclick = async () => { const name = prompt('Equipment name'); if (!name) return; const assetCode = prompt('Asset code'); if (!assetCode) return; try { await mlmApi.addEquipment({ name, assetCode, status: 'available' }); await render(); } catch (error) { mlmUiError(error.message); } }; } catch (error) { mlmUiError(error.message); }
  }
  if (document.querySelector('#requestList')) {
    try { const result = await mlmApi.requests('?status=pending'); const requests = Array.isArray(result) ? result : (result.requests || []); document.querySelector('#requestList').innerHTML = requests.map(x => `<article class="request-card"><div class="request-head"><div><h2>Request #${x.id}</h2><p>${esc(x.requester_name || '')}</p></div><span class="status pending">pending</span></div><div class="request-details"><article><b>Equipment</b><p>${(x.items || []).map(i => esc(i.name || i.equipment_id)).join(', ')}</p></article><article><b>Purpose</b><p>${esc(x.purpose)}</p></article></div><div class="request-actions"><button class="reject" data-action="reject" data-id="${x.id}">Reject</button><button class="primary" data-action="approve" data-id="${x.id}">Approve</button></div></article>`).join('') || '<p>No pending requests.</p>'; document.querySelectorAll('[data-action]').forEach(button => button.onclick = async () => { try { if (button.dataset.action === 'approve') await mlmApi.approveRequest(button.dataset.id, user.id); else await mlmApi.rejectRequest(button.dataset.id, user.id, prompt('Reason for rejection') || ''); button.closest('.request-card').remove(); } catch (error) { mlmUiError(error.message); } }); } catch (error) { mlmUiError(error.message); }
  }
  if (document.querySelector('#reportRows')) { try { const result = await mlmApi.requests(); const requests = Array.isArray(result) ? result : (result.requests || []); document.querySelector('#reportRows').innerHTML = requests.map(x => `<tr><td>${x.id}</td><td>${esc(x.requester_name || '')}</td><td>${(x.items || []).map(i => esc(i.name || i.equipment_id)).join(', ')}</td><td>${esc(x.created_at)}</td><td>${esc(x.updated_at)}</td><td><span class="status ${esc(x.status)}">${esc(x.status)}</span></td><td>—</td></tr>`).join(''); } catch (error) { mlmUiError(error.message); } }
});
