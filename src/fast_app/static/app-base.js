/**
 * app-base.js — Shared Alpine.js auth store and helpers.
 *
 * This file must be loaded BEFORE any page-specific Alpine components.
 * It registers Alpine.store('auth') which is used by navbar, login, and
 * the main app page.
 */

document.addEventListener('alpine:init', () => {
  Alpine.store('auth', {
    user: null,
    token: null,
    isLoggedIn: false,
    authEnabled: false,

    async checkAuth() {
      const token = localStorage.getItem('fast_app_token');
      if (!token) {
        this.isLoggedIn = false;
        this.user = null;
        this.token = null;
        return;
      }

      try {
        const response = await fetch('/api/auth/me', {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
          this.user = await response.json();
          this.token = token;
          this.isLoggedIn = true;
        } else {
          // Token invalid or expired
          localStorage.removeItem('fast_app_token');
          this.isLoggedIn = false;
          this.user = null;
          this.token = null;
        }
      } catch (e) {
        console.error('Auth check failed:', e);
        this.isLoggedIn = false;
        this.user = null;
        this.token = null;
      }
    },

    async checkAuthEnabled() {
      try {
        const response = await fetch('/api/auth/enabled');
        if (response.ok) {
          const data = await response.json();
          this.authEnabled = data.enabled;
        }
      } catch (e) {
        // If endpoint fails, assume auth is disabled
        this.authEnabled = false;
      }
    },

    fetchWithAuth(url, options = {}) {
      const token = localStorage.getItem('fast_app_token');
      if (token) {
        options.headers = options.headers || {};
        options.headers['Authorization'] = `Bearer ${token}`;
      }
      return fetch(url, options);
    },

    async logout() {
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch (e) {
        // Ignore errors on logout
      }
      localStorage.removeItem('fast_app_token');
      this.isLoggedIn = false;
      this.user = null;
      this.token = null;
      window.location.href = '/login';
    }
  });
});