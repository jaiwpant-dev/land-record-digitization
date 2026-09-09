/* Login shell only. Production processing is implemented in portal.js. */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('loginForm');
  if (form) form.addEventListener('submit', (event) => {
    event.preventDefault();
    location.href = 'dashboard.html';
  });
});
