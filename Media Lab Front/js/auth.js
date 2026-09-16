(function () {
  const form = document.querySelector('#loginForm');
  const error = document.querySelector('#loginError');
  form.addEventListener('submit', async event => {
    event.preventDefault(); error.textContent = '';
    const pin = form.pin.value;
    if (!/^\d{4}$/.test(pin)) { error.textContent = 'PIN must be exactly 4 digits.'; return; }
    try { await mlmApi.login(Object.fromEntries(new FormData(form))); location.href = 'pages/catalog.html'; }
    catch (cause) { error.textContent = cause.message; }
  });
})();
