const apiReady = window.mlmApi ? Promise.resolve() : new Promise(resolve => { const s = document.createElement('script'); s.src = '../js/api.js'; s.onload = resolve; document.head.appendChild(s); });
apiReady.then(() => window.mlmSessionReady).then(() => mlmSession.requireAuth()).then(async () => {
  let category = 'All';
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const cart = () => JSON.parse(localStorage.getItem('mlmCart') || '[]');
  const draw = async () => {
    const filters = { q: $('#search').value, limit: 1000 };
    if ($('#available').checked) filters.status = 'available';
    try {
      const result = await mlmApi.equipment(filters);
      const items = Array.isArray(result) ? result : (result.equipment || result.items || []);
      const selected = [...document.querySelectorAll('.brand-filter:checked')].map(x => x.value.toLowerCase());
      const list = items.filter(x => (!category || category === 'All' || (x.category || '').toLowerCase() === category.toLowerCase()) && (!selected.length || selected.includes(String(x.brand || '').toLowerCase())));
      const selectedIds = new Set(cart().map(x => Number(x.id)));
      let cartAction = document.querySelector('#cartAction');
      if (!cartAction) { cartAction = document.createElement('a'); cartAction.id = 'cartAction'; cartAction.className = 'primary'; cartAction.href = 'bookings.html'; document.querySelector('.page-heading')?.appendChild(cartAction); }
      cartAction.textContent = selectedIds.size ? `Proceed to Booking (${selectedIds.size})` : '';
      cartAction.style.display = selectedIds.size ? 'inline-block' : 'none';
      $('#equipmentGrid').innerHTML = list.map(item => `<article class="equipment-card"><div class="product-image">▱</div><div class="product-info"><span class="tag">${esc(item.category || item.status || 'Equipment')}</span><span class="availability">● ${esc(item.status || 'available')}</span><h3>${esc(item.name)}</h3><p>${esc(item.asset_code || item.assetCode || item.location || '')}</p><button class="${selectedIds.has(Number(item.id)) ? 'unavailable' : 'primary'}" ${selectedIds.has(Number(item.id)) ? 'disabled' : ''} data-add="${item.id}">${selectedIds.has(Number(item.id)) ? '✓ Added to Cart' : '＋ Add to Booking'}</button></div></article>`).join('') || '<p>No equipment matches these filters.</p>';
      $('#cartCount').textContent = cart().length;
      document.querySelectorAll('[data-add]').forEach(button => button.onclick = () => { const item = list.find(x => Number(x.id) === Number(button.dataset.add)); const next = cart(); if (item && !next.some(x => Number(x.id) === Number(item.id))) { next.push(item); localStorage.setItem('mlmCart', JSON.stringify(next)); draw(); } });
    } catch (error) { $('#equipmentGrid').innerHTML = '<p>Equipment is unavailable until the API is connected.</p>'; mlmUiError(error.message); }
  };
  $('#search').oninput = draw; $('#available').onchange = draw;
  document.querySelectorAll('.brand-filter').forEach(x => x.onchange = draw);
  document.querySelectorAll('[data-category]').forEach(x => x.onclick = () => { category = x.dataset.category; document.querySelectorAll('[data-category]').forEach(y => y.classList.toggle('selected', y === x)); draw(); });
  $('#clearFilters').onclick = () => { $('#search').value = ''; $('#available').checked = false; document.querySelectorAll('.brand-filter').forEach(x => x.checked = false); category = 'All'; draw(); };
  draw();
});
