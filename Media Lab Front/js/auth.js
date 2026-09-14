// Development placeholder: authentication is intentionally bypassed for now.
// This matches the seeded development user in dev-backend/server.js.
const loginButton = document.querySelector('#loginButton');
loginButton.textContent = 'Enter Media Lab Manager';
loginButton.addEventListener('click', () => {
  localStorage.setItem('mlmUser', JSON.stringify({
    id: 1,
    krea_id: 'dev-student',
    name: 'Alex Rivera',
    email: 'alex@example.edu',
    department: 'Communication & Film',
    role: 'lendee'
  }));
  location.href = 'pages/catalog.html';
});
