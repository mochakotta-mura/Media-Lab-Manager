(async function () {
  if (!window.mlmApi) await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = '../../js/api.js'; script.onload = resolve; script.onerror = reject; document.head.appendChild(script); });
  await window.mlmSessionReady; await mlmSession.requireStaff();
  const target = document.querySelector('#reportRows'); if (!target) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const format = value => value ? new Date(value).toLocaleDateString() : '—';
  try { const result = await mlmApi.requests(); const requests = Array.isArray(result) ? result : (result.requests || []); target.innerHTML = requests.map(request => { const pickup = request.windows?.find(x => x.kind === 'pickup'); const returned = request.windows?.find(x => x.kind === 'return'); return `<tr><td><b>#${request.id}</b></td><td>${esc(request.requester_name || request.requesterName || request.requester_id)}</td><td>${esc((request.items || []).map(item => item.name || item.equipment_id).join(', '))}</td><td>${format(pickup?.starts_at)}</td><td>${format(returned?.ends_at)}</td><td><span class="status ${esc(request.status)}">${esc(request.status)}</span></td><td>${esc(request.return_notes || '—')}</td></tr>`; }).join('') || '<tr><td colspan="7" class="empty">No request history found.</td></tr>'; } catch (error) { target.innerHTML = `<tr><td colspan="7">${esc(error.message)}</td></tr>`; }
})();
