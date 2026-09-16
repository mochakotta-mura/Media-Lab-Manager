/* One shared navigation renderer for every authenticated page. */
(async function () {
  const nav = document.querySelector('[data-shared-nav], .student-nav');
  if (!nav) return;
  const user = await window.mlmSession.getCurrentUser();
  if (!user) return;
  const staff = window.mlmSession.isStaff(user);
  document.querySelectorAll('.header-tools .admin-link').forEach(element => { if (!staff) element.remove(); });
  const initials = String(user.name || user.email || '').split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase();
  document.querySelectorAll('.avatar, .large-avatar').forEach(element => { element.textContent = initials; });
  document.querySelectorAll('.profile-name b').forEach(element => { element.textContent = user.name || user.email; });
  document.querySelectorAll('.profile-name small').forEach(element => { element.textContent = user.email || ''; });
  const profileHeading = document.querySelector('.student-profile h1');
  if (profileHeading?.firstChild) profileHeading.firstChild.nodeValue = `${user.name || user.email} `;
  const profileDetails = document.querySelector('.student-profile p');
  if (profileDetails) profileDetails.textContent = user.email || '';
  const adminPage = location.pathname.includes('/pages/admin/');
  const links = adminPage
    ? [['../../pages/catalog.html', 'Student Catalog'], ['../../pages/profile.html', 'Profile'], ['equipment.html', 'Admin Console'], ['frontend-health.html', 'Frontend Health']]
    : [['catalog.html', 'Catalog'], ['bookings.html', 'Bookings & Cart'], ['history.html', 'My History'], ['notifications.html', 'Notifications'], ['profile.html', 'Profile']];
  nav.innerHTML = links.map(([href, label]) => `<a href="${href}">${label}</a>`).join('') + (!adminPage && staff ? '<a class="admin-link" href="admin/equipment.html">Admin Console</a>' : '');
  if (adminPage) document.querySelectorAll('a[href="#"]').forEach(link => { if (/settings/i.test(link.textContent)) link.href = 'settings.html'; });
  document.querySelectorAll('.avatar, .large-avatar').forEach(element => { element.setAttribute('role', 'link'); element.setAttribute('tabindex', '0'); element.title = 'Open profile'; element.onclick = () => { location.href = adminPage ? '../../pages/profile.html' : 'profile.html'; }; element.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') element.click(); }; });
})();
