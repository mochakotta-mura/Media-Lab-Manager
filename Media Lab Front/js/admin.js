/* Live equipment management for the staff inventory page. */
const adminApiReady = window.mlmApi ? Promise.resolve() : new Promise((resolve, reject) => {
  const script = document.createElement('script'); script.src = '../../js/api.js'; script.onload = resolve; script.onerror = reject; document.head.appendChild(script);
});
adminApiReady.then(() => window.mlmSessionReady).then(() => mlmSession.requireStaff()).then(async () => {
  const rows = document.querySelector('#equipmentRows'); if (!rows) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const status = value => `<span class="status ${esc(String(value || '').toLowerCase())}">${esc(value || 'unknown')}</span>`;
  const classify = name => { const n = String(name || '').toLowerCase(); if (/camera|a6400|zv-e10|rx100/.test(n)) return 'Cameras'; if (/lens|mm f|art/.test(n)) return 'Lenses'; if (/mic|rode|røde|sennheiser|hollyland|zoom|headphone|mixer|recorder|audio/.test(n)) return 'Audio'; if (/light|godox|aputure|colbor|softbox|stand/.test(n)) return 'Lighting'; return 'Accessories'; };
  let equipment = [];
  const render = category => {
    const query = (document.querySelector('#equipmentSearch')?.value || '').toLowerCase();
    const filtered = equipment.filter(item => (category === 'All' || classify(item.name).toLowerCase() === category.toLowerCase()) && [item.name, item.asset_code, item.serial_number, item.description].join(' ').toLowerCase().includes(query));
    rows.innerHTML = filtered.map(item => `<tr><td><b>${esc(item.name)}</b><br><small>${esc(item.description || '')}</small></td><td>${esc(item.category || classify(item.name))}</td><td>${esc(item.location || '—')}</td><td>${esc(item.total_quantity ?? 1)}</td><td>${esc(item.available_quantity ?? (item.status === 'available' ? 1 : 0))}</td><td>${esc(item.checked_out_quantity ?? 0)}</td><td>${status(item.status)}</td><td><button class="btn btn-ghost btn-sm" data-equipment-edit="${item.id}">Edit</button></td></tr>`).join('') || '<tr><td colspan="8" class="empty">No equipment matches this filter.</td></tr>';
    document.querySelectorAll('[data-equipment-edit]').forEach(button => button.onclick = () => window.mlmUiError('Equipment editing is connected to the backend API; an edit form can be added without changing the endpoint contract.'));
  };
  try {
    const result = await mlmApi.equipment({ limit: 1000 }); equipment = Array.isArray(result) ? result : (result.equipment || result.items || []); render('All');
    document.querySelector('#equipmentSearch')?.addEventListener('input', () => render(document.querySelector('.admin-tabs .selected')?.dataset.filter || 'All'));
    document.querySelectorAll('.admin-tabs button').forEach(button => button.onclick = () => { document.querySelectorAll('.admin-tabs button').forEach(x => x.classList.remove('selected')); button.classList.add('selected'); render(button.dataset.filter || button.textContent.trim()); });
  } catch (error) { rows.innerHTML = `<tr><td colspan="8">${esc(error.message)}</td></tr>`; }
});
