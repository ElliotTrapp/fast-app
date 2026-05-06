function authForm() {
  return {
    email: '',
    password: '',
    confirm_password: '',
    mode: 'login',
    error: '',
    loading: false,

    toggleMode() {
      this.error = '';
      this.mode = this.mode === 'login' ? 'register' : 'login';
    },

    validate() {
      if (!this.email || !this.email.includes('@')) {
        this.error = 'Please enter a valid email address.';
        return false;
      }
      if (!this.password || this.password.length < 4) {
        this.error = 'Password must be at least 4 characters.';
        return false;
      }
      if (this.mode === 'register' && this.password !== this.confirm_password) {
        this.error = 'Passwords do not match.';
        return false;
      }
      return true;
    },

    async submitLogin() {
      this.error = '';
      if (!this.validate()) return;

      this.loading = true;
      try {
        const response = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: this.email, password: this.password })
        });

        const data = await response.json();

        if (!response.ok) {
          this.error = data.detail || 'Login failed.';
          return;
        }

        localStorage.setItem('fast_app_token', data.access_token);
        Alpine.store('auth').token = data.access_token;
        Alpine.store('auth').isLoggedIn = true;
        await Alpine.store('auth').checkAuth();
        window.location.href = '/';
      } catch (e) {
        this.error = 'Network error. Please try again.';
      } finally {
        this.loading = false;
      }
    },

    async submitRegister() {
      this.error = '';
      if (!this.validate()) return;

      this.loading = true;
      try {
        const response = await fetch('/api/auth/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: this.email, password: this.password })
        });

        const data = await response.json();

        if (!response.ok) {
          this.error = data.detail || 'Registration failed.';
          return;
        }

        localStorage.setItem('fast_app_token', data.access_token);
        Alpine.store('auth').token = data.access_token;
        Alpine.store('auth').isLoggedIn = true;
        await Alpine.store('auth').checkAuth();
        window.location.href = '/';
      } catch (e) {
        this.error = 'Network error. Please try again.';
      } finally {
        this.loading = false;
      }
    }
  };
}