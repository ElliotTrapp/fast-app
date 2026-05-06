/**
 * navbar.js — Initializes the navbar auth state on page load.
 */
document.addEventListener('alpine:init', async () => {
  await Alpine.store('auth').checkAuthEnabled();
  if (Alpine.store('auth').authEnabled) {
    await Alpine.store('auth').checkAuth();
  }
});