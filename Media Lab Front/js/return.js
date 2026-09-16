(async function () {
  if (!window.mlmApi) await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = '../js/api.js'; script.onload = resolve; script.onerror = reject; document.head.appendChild(script); });
  await window.mlmSessionReady;
  await mlmSession.requireAuth();
  document.querySelector('.returned-gear').innerHTML = '<h2>Loading booking…</h2>';
  const requestId = Number(new URLSearchParams(location.search).get('request'));
  try {
    const result = await mlmApi.requests();
    const requests = Array.isArray(result) ? result : (result.requests || []);
    const request = requests.find(item => Number(item.id) === requestId);
    if (!request) throw new Error('Request not found.');
    const gear = document.querySelector('.returned-gear');
    gear.innerHTML = `<h2>Confirm Equipment Being Returned</h2>${(request.items || []).map(item => `<div><span><b>${item.name || item.equipment_id}</b><small>${item.asset_code || ''} · Request #${request.id}</small></span></div>`).join('')}`;
    if (mlmSession.isStaff() && Number(request.requester_id) !== Number(mlmSession.currentUser()?.id)) document.querySelector('.verification').innerHTML = '<span><b>Staff processing mode</b><br>You are recording a return for another user.</span>';
    const form = document.querySelector('#returnForm');
    form.onsubmit = async event => {
      event.preventDefault();
      const user = await mlmApi.me().then(data => data.user);
      const condition = document.querySelector('input[name="condition"]:checked')?.parentElement.textContent.trim() || '';
      const notes = form.querySelector('textarea')?.value || '';
      try { await mlmApi.return(requestId, { condition, damageFlag: /damage|faulty/i.test(condition), notes, returnedAt: new Date().toISOString(), actorId: user.id }); location.href = 'history.html'; }
      catch (error) { mlmUiError(error.message); }
    };
  } catch (error) { mlmUiError(error.message); }
})();
