(async function () {
  if (!window.mlmApi) await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = '../js/api.js'; script.onload = resolve; script.onerror = reject; document.head.appendChild(script); });
  await window.mlmSessionReady;
  const user = await mlmSession.requireAuth();
  const params = new URLSearchParams(location.search);
  const requestId = Number(params.get('request'));
  const gear = document.querySelector('.returned-gear');
  const form = document.querySelector('#returnForm');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
  const conditions = [['excellent', 'Excellent', 'No visible wear'], ['good', 'Good', 'Standard use'], ['minor', 'Minor Damage', 'Small repair or cosmetic issue'], ['major', 'Major Damage / Faulty', 'Requires staff inspection']];
  const severityFor = condition => ({ minor: 'minor', major: 'major' }[condition] || '');
  const returnable = item => !['returned', 'damaged'].includes(String(item.status || '').toLowerCase());
  const goBack = () => { location.href = params.get('from') === 'profile' ? 'profile.html' : 'history.html'; };
  try {
    if (!requestId) throw new Error('A booking is required to submit a return report.');
    gear.innerHTML = '<h2>Loading booking…</h2>';
    const result = await mlmApi.requests();
    const request = (Array.isArray(result) ? result : (result.requests || [])).find(item => Number(item.id) === requestId);
    if (!request) throw new Error('Request not found.');
    const items = request.items || [];
    gear.innerHTML = `<h2>Request #${request.id}${request.purpose ? ` · ${esc(request.purpose)}` : ''}</h2>${items.map(item => `<div class="return-gear-item"><span aria-hidden="true">◈</span><span><b>${esc(item.name || item.equipment_id)}</b><small>${esc(item.asset_code || '')} · Request item #${esc(item.id)}</small></span></div>`).join('')}`;
    if (mlmSession.isStaff(user) && Number(request.requester_id) !== Number(user.id)) document.querySelector('.verification').innerHTML = '<span><b>Staff processing mode</b><br>You are recording a return for another user.</span>';
    if (request.return_submission) {
      form.innerHTML = '<h2>Return report already submitted</h2><p class="return-intro">This booking already has a return submission. Each equipment item can only be reported once.</p><div class="form-actions"><button type="button" class="outline" data-cancel-return>Back to history</button></div>';
      form.querySelector('[data-cancel-return]')?.addEventListener('click', goBack);
      return;
    }
    form.innerHTML = `<h2>Return Checklist &amp; Status</h2><p class="return-intro">Complete one condition report for each equipment item. This keeps damage reports tied to the correct unit.</p><div class="return-item-forms">${items.map(item => { const editable = returnable(item); return `<fieldset class="return-item" data-item-id="${esc(item.id)}"><legend>${esc(item.name || item.equipment_id)}</legend>${editable ? `<div class="conditions">${conditions.map(([value, label, hint]) => `<label><input type="radio" name="condition-${esc(item.id)}" value="${value}" ${value === 'good' ? 'checked' : ''}><span><b>${label}</b><small>${hint}</small></span></label>`).join('')}</div><label class="item-notes">Describe issues or missing items (optional)<textarea data-notes placeholder="Notes for this equipment..."></textarea></label>` : '<p class="item-complete">A return report has already been submitted for this equipment.</p>'}</fieldset>`; }).join('')}</div><label class="upload">▧<br><strong>Click to upload photos or drag and drop</strong><small>PNG, JPG up to 10MB each</small><input type="file" multiple hidden></label><div class="form-actions"><button type="button" class="outline" data-cancel-return>Cancel</button><button class="primary" type="submit">Submit Return Report</button></div>`;
    form.querySelector('[data-cancel-return]')?.addEventListener('click', goBack);
    form.querySelectorAll('input[type="radio"]').forEach(input => input.addEventListener('change', () => {
      input.closest('.conditions').querySelectorAll('label').forEach(label => label.classList.toggle('selected', label.contains(input)));
    }));
    form.querySelectorAll('.conditions').forEach(group => group.querySelector('input:checked')?.closest('label')?.classList.add('selected'));
    form.onsubmit = async event => {
      event.preventDefault();
      const reports = items.filter(returnable).map(item => { const selected = form.querySelector(`input[name="condition-${item.id}"]:checked`); return { item, condition: selected?.value || '', notes: form.querySelector(`[data-item-id="${item.id}"] [data-notes]`)?.value.trim() || '' }; });
      if (reports.some(report => !report.condition)) return mlmUiError('Choose a condition for every equipment item.');
      try {
        const itemConditions = reports.map(report => ({ requestItemId: report.item.id, equipment: report.item.name || report.item.equipment_id, condition: report.condition, severity: severityFor(report.condition) || 'none', notes: report.notes }));
        await mlmApi.return(requestId, { studentCondition: JSON.stringify(itemConditions), damageDescription: JSON.stringify(itemConditions.filter(report => report.severity)), claimedReturnedAt: new Date().toISOString(), photoReferences: [] });
        location.href = 'history.html';
      } catch (error) { mlmUiError(error.message); }
    };
  } catch (error) { mlmUiError(error.message); }
})();
