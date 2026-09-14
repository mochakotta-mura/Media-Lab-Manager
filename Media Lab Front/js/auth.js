(function () {
  const form = document.querySelector('#loginForm');
  const error = document.querySelector('#loginError');
  const typeInput = document.querySelector('#accountType');
  document.querySelectorAll('[data-account-type]').forEach(button => button.onclick = () => {
    typeInput.value = button.dataset.accountType;
    document.querySelectorAll('[data-account-type]').forEach(item => item.classList.toggle('selected', item === button));
    document.querySelector('[name="email"]').placeholder = button.dataset.accountType === 'student' ? 'you@krea.ac.in' : 'you@krea.edu.in';
    error.textContent = '';
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); error.textContent = '';
    const pin = form.pin.value;
    if (!/^\d{4}$/.test(pin)) { error.textContent = 'PIN must be exactly 4 digits.'; return; }
    try { await mlmApi.login(Object.fromEntries(new FormData(form))); location.href = 'pages/catalog.html'; }
    catch (cause) { error.textContent = cause.message; }
  });
})();
