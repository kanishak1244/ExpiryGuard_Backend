/* ==========================================================================
   EXPIRYGUARD WEB APP — UNIFIED API CLIENT & POLLING ENGINE
   Handles Authentication, Requests, Errors, and 5-Second Real-Time Polling
   ========================================================================== */

const API_BASE_URL = (window.location.origin && window.location.origin !== 'null' && window.location.protocol.startsWith('http'))
  ? window.location.origin
  : 'http://127.0.0.1:8000';

class ApiClient {
  constructor() {
    this.tokenKey = 'expiryguard_token';
    this.cache = new Map(); // in-memory Map: key -> { data, ts, ttl }
    this.inFlight = new Map(); // in-flight Promises for deduplication: key -> Promise
    this.cachePrefix = 'eg_swr_';
    this._prefetchScheduled = false;
    this._initPersistentCache();
    
    // Auto-schedule background idle prefetch when token is present
    if (this.getToken()) {
      this.scheduleIdlePrefetch();
    }
  }

  _initPersistentCache() {
    try {
      // Rehydrate in-memory cache from sessionStorage for instant cross-page module switching
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k && k.startsWith(this.cachePrefix)) {
          const itemKey = k.substring(this.cachePrefix.length);
          const raw = sessionStorage.getItem(k);
          if (raw) {
            const entry = JSON.parse(raw);
            if (entry && (Date.now() - entry.ts) < (entry.ttl || 120000)) {
              this.cache.set(itemKey, entry);
            } else {
              sessionStorage.removeItem(k);
            }
          }
        }
      }
    } catch (e) {}
  }

  getCached(endpoint) {
    const key = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
    const mem = this.cache.get(key);
    if (mem && (Date.now() - mem.ts) < (mem.ttl || 120000)) {
      return mem;
    }
    try {
      const raw = sessionStorage.getItem(this.cachePrefix + key) || localStorage.getItem(this.cachePrefix + key);
      if (raw) {
        const entry = JSON.parse(raw);
        if (entry && (Date.now() - entry.ts) < (entry.ttl || 120000)) {
          this.cache.set(key, entry);
          return entry;
        }
      }
    } catch (e) {}
    return null;
  }

  setCached(endpoint, data, ttlMs = 120000) {
    const key = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
    const entry = { data, ts: Date.now(), ttl: ttlMs };
    this.cache.set(key, entry);
    try {
      const raw = JSON.stringify(entry);
      sessionStorage.setItem(this.cachePrefix + key, raw);
    } catch (e) {}
  }

  invalidateCache(patterns) {
    const list = Array.isArray(patterns) ? patterns : [patterns];
    const keysToPurge = [];
    for (const key of this.cache.keys()) {
      for (const p of list) {
        if (typeof p === 'string' && key.includes(p)) {
          keysToPurge.push(key);
          break;
        } else if (p instanceof RegExp && p.test(key)) {
          keysToPurge.push(key);
          break;
        }
      }
    }
    for (const k of keysToPurge) {
      this.cache.delete(k);
      try {
        sessionStorage.removeItem(this.cachePrefix + k);
        localStorage.removeItem(this.cachePrefix + k);
      } catch (e) {}
    }
  }

  async swrRequest(endpoint, options = {}, config = {}) {
    const opts = options || {};
    const method = (opts.method || 'GET').toUpperCase();
    if (method !== 'GET') {
      return await this.request(endpoint, opts);
    }

    const ttlMs = config.ttlMs || 120000; // 2 minutes max cache lifetime
    const staleAfterMs = config.staleAfterMs !== undefined ? config.staleAfterMs : 3000; // 3 seconds freshness window
    const onUpdate = config.onUpdate || null;
    const force = config.force || false;

    if (!force) {
      const cached = this.getCached(endpoint);
      if (cached && cached.data !== undefined) {
        const isStale = (Date.now() - cached.ts) > staleAfterMs;
        if (isStale) {
          // Trigger background silent revalidation
          this._fetchAndCache(endpoint, opts, ttlMs)
            .then(freshData => {
              if (freshData !== undefined) {
                const changed = JSON.stringify(freshData) !== JSON.stringify(cached.data);
                if (changed) {
                  if (typeof onUpdate === 'function') onUpdate(freshData);
                  window.dispatchEvent(new CustomEvent('api:cache-updated', {
                    detail: { endpoint, data: freshData }
                  }));
                }
              }
            })
            .catch(() => {});
        }
        return cached.data;
      }
    }

    return await this._fetchAndCache(endpoint, opts, ttlMs);
  }

  _fetchAndCache(endpoint, options, ttlMs) {
    const flightKey = 'GET:' + endpoint;
    if (this.inFlight.has(flightKey)) {
      return this.inFlight.get(flightKey);
    }

    const promise = this.request(endpoint, options)
      .then(data => {
        this.setCached(endpoint, data, ttlMs);
        this.inFlight.delete(flightKey);
        return data;
      })
      .catch(err => {
        this.inFlight.delete(flightKey);
        throw err;
      });

    this.inFlight.set(flightKey, promise);
    return promise;
  }

  scheduleIdlePrefetch() {
    if (this._prefetchScheduled) return;
    this._prefetchScheduled = true;

    const runPrefetch = () => {
      if (!this.getToken()) return;
      const endpoints = [
        '/dashboard/summary',
        '/products',
        '/customers',
        '/suppliers',
        '/sales?skip=0&limit=50',
        '/branches',
        '/staff',
        '/billing/returns/today'
      ];
      endpoints.forEach((ep, idx) => {
        setTimeout(() => {
          if (this.getToken() && !this.getCached(ep)) {
            this.swrRequest(ep, {}, { ttlMs: 180000, staleAfterMs: 30000 }).catch(() => {});
          }
        }, idx * 100);
      });
    };

    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(runPrefetch, { timeout: 2000 });
    } else {
      setTimeout(runPrefetch, 600);
    }
  }

  getToken() {
    return localStorage.getItem(this.tokenKey);
  }

  setToken(token) {
    localStorage.setItem(this.tokenKey, token);
  }

  logout() {
    this.requestLogout();
  }

  async ensureAuthenticated(forceRefresh = false) {
    if (!forceRefresh && this.getToken()) return this.getToken();
    try {
      if (forceRefresh) {
        localStorage.removeItem(this.tokenKey);
      }
      const res = await fetch(`${API_BASE_URL}/auth/session`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        if (data.access_token) {
          this.setToken(data.access_token);
          return data.access_token;
        }
      }
    } catch (e) {
      console.warn('Auto session initialization error:', e);
    }
    return null;
  }

  async getHeaders(isMultipart = false) {
    let token = this.getToken();
    if (!token) {
      token = await this.ensureAuthenticated();
    }
    const headers = {};
    if (!isMultipart) {
      headers['Content-Type'] = 'application/json';
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  async request(endpoint, options = {}) {
    const isMultipart = options.body instanceof FormData;
    let headers = await this.getHeaders(isMultipart);

    const isFileOrigin = (window.location.protocol === 'file:' || !window.location.origin || window.location.origin === 'null');
    const config = {
      credentials: isFileOrigin ? 'omit' : 'include',
      ...options,
      headers: {
        ...headers,
        ...(options.headers || {})
      }
    };

    try {
      let response = await fetch(`${API_BASE_URL}${endpoint}`, config);

      if (response.status === 401) {
        localStorage.removeItem(this.tokenKey);
        const newToken = await this.ensureAuthenticated(true);
        if (newToken) {
          config.headers['Authorization'] = `Bearer ${newToken}`;
          response = await fetch(`${API_BASE_URL}${endpoint}`, config);
        }
        if (response.status === 401) {
          this.showLoginModal();
          throw new Error('Authentication required');
        }
      }

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`API Error (${response.status}): ${errText}`);
      }

      // Auto-invalidate matching cache tags on successful mutations
      const method = (config.method || 'GET').toUpperCase();
      if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
        let mutationTag = 'general';
        if (endpoint.startsWith('/sales') || endpoint.startsWith('/billing')) {
          mutationTag = 'sales';
          this.invalidateCache(['/sales', '/dashboard', '/inventory', '/products', '/khata', '/reports', '/app/bootstrap']);
        } else if (endpoint.startsWith('/products') || endpoint.startsWith('/inventory') || endpoint.startsWith('/api/inventory')) {
          mutationTag = 'inventory';
          this.invalidateCache(['/products', '/inventory', '/dashboard', '/smart_restock', '/app/bootstrap']);
        } else if (endpoint.startsWith('/customers') || endpoint.startsWith('/khata')) {
          mutationTag = 'khata';
          this.invalidateCache(['/customers', '/khata', '/dashboard', '/app/bootstrap']);
        } else if (endpoint.startsWith('/suppliers')) {
          mutationTag = 'suppliers';
          this.invalidateCache(['/suppliers', '/documents']);
        } else if (endpoint.startsWith('/staff')) {
          mutationTag = 'staff';
          this.invalidateCache(['/staff']);
        } else if (endpoint.startsWith('/branches')) {
          mutationTag = 'branches';
          this.invalidateCache(['/branches']);
        } else if (endpoint.startsWith('/billing/returns') || endpoint.startsWith('/returns')) {
          mutationTag = 'returns';
          this.invalidateCache(['/returns', '/sales', '/dashboard', '/app/bootstrap']);
        }
        
        // Notify window.AppDataPreloader and active page components
        if (window.AppDataPreloader && typeof window.AppDataPreloader.invalidateTag === 'function') {
          window.AppDataPreloader.invalidateTag(mutationTag);
        }
        window.dispatchEvent(new CustomEvent('dawaiflow:mutate', { detail: { tag: mutationTag, endpoint } }));
      }

      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await response.json();
      }
      return await response.blob();
    } catch (err) {
      console.error(`Request failed to ${endpoint}:`, err);
      throw err;
    }
  }

  async login(email, password) {
    const res = await fetch(`${API_BASE_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), password: password })
    });

    const data = await res.json();
    if (!res.ok || !data.access_token) {
      throw new Error(data.message || data.detail || 'Invalid email/username or password');
    }

    this.setToken(data.access_token);
    try {
      localStorage.setItem('expiryguard_cached_user_profile', JSON.stringify({
        shop_name: data.shop_name,
        owner_name: data.owner_name,
        name: data.name,
        role: data.role,
        staff_id: data.staff_id,
        is_owner: !data.staff_id,
        permissions: data.permissions || [],
      }));
    } catch (e) {}
    return data;
  }

  requestLogout() {
    if (window.ConfirmModal) {
      ConfirmModal({
        isOpen: true,
        title: 'Want to log out?',
        message: 'Are you sure you want to log out of ExpiryGuard ERP? You will need to enter your credentials to log back in.',
        confirmText: 'Logout',
        cancelText: 'Cancel',
        icon: '🔒',
        onConfirm: () => this.executeLogout()
      });
    } else if (confirm('Want to log out?')) {
      this.executeLogout();
    }
  }

  async executeLogout() {
    try {
      if (window.ExpiryNav && typeof window.ExpiryNav.closeDrawer === 'function') {
        window.ExpiryNav.closeDrawer();
      }
    } catch (e) {}

    try {
      await fetch(`${API_BASE_URL}/logout`, { method: 'POST', credentials: 'include' }).catch(() => {});
    } catch (e) {
      console.warn('Logout endpoint call warning:', e);
    }

    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem('expiryguard_token');
    localStorage.removeItem('expiryguard_user');
    localStorage.removeItem('expiryguard_session');
    localStorage.setItem('expiryguard_logged_out', 'true');
    try { sessionStorage.clear(); } catch(e){}

    // Clear history stack to prevent Back button dashboard restoration
    window.history.pushState(null, '', window.location.pathname);
    
    // Redirect to index.html to clean URL and protect routes
    const isRoot = window.location.pathname.endsWith('index.html') || window.location.pathname === '/' || window.location.pathname.endsWith('/');
    if (!isRoot) {
      window.location.replace('index.html');
    } else {
      window.location.reload();
    }
  }

  showLoginModal(isForced = false) {
    const appContainer = document.querySelector('.app-container');
    if (appContainer) {
      appContainer.style.display = 'none';
    }

    const self = this;
    let modal = document.getElementById('login-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'login-modal';
      modal.className = 'modal-overlay active';
      modal.style.zIndex = '999999';
      modal.style.backgroundColor = 'rgba(15, 23, 42, 0.85)';
      modal.style.backdropFilter = 'blur(8px)';
      modal.style.display = 'flex';
      modal.style.alignItems = 'center';
      modal.style.justifyContent = 'center';
      modal.style.position = 'fixed';
      modal.style.top = '0';
      modal.style.left = '0';
      modal.style.right = '0';
      modal.style.bottom = '0';
      modal.style.overflowY = 'auto';
      modal.style.padding = '20px 0';

      modal.innerHTML = `
        <div class="modal-card" style="max-width: 440px; width: 90%; background: #0F172A; color: #F8FAFC; border: 1px solid #334155; border-radius: 20px; padding: 32px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); margin: auto;">
          <div style="text-align: center; margin-bottom: 24px;">
            <div style="width: 56px; height: 56px; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 16px; display: flex; align-items: center; justify-content: center; margin: 0 auto 12px; font-size: 28px;">
              🛡️
            </div>
            <h2 id="auth-title" style="font-size: 24px; font-weight: 800; color: #FFFFFF; margin-bottom: 4px; letter-spacing: -0.5px;">ExpiryGuard</h2>
            <p id="auth-subtitle" style="font-size: 13px; color: #94A3B8;">Sign in to access pharmacy counter & inventory</p>
          </div>

          <div id="auth-error" style="color: #F87171; background: rgba(220, 38, 38, 0.15); border: 1px solid rgba(220, 38, 38, 0.3); padding: 10px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 16px; display: none;"></div>
          <div id="auth-success" style="color: #34D399; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); padding: 10px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 16px; display: none;"></div>

          <!-- LOGIN PANEL -->
          <div id="login-panel">
            <form id="web-login-form">
              <div class="form-group" style="margin-bottom: 16px;">
                <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Email Address</label>
                <input type="email" id="login-email" class="form-input" required placeholder="name@pharmacy.com" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
              </div>
              <div class="form-group" style="margin-bottom: 20px;">
                <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Password</label>
                <input type="password" id="login-password" class="form-input" required placeholder="Enter password" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
              </div>
              <button type="submit" id="btn-submit-login" class="btn btn-primary" style="width: 100%; padding: 12px; background: #10B981; border: none; border-radius: 10px; color: #FFFFFF; font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.2s ease;">
                Log In to ExpiryGuard →
              </button>
            </form>
            <div style="margin-top: 20px; text-align: center; font-size: 13px; color: #94A3B8;">
              Don't have an account? <a href="javascript:void(0)" id="link-show-register" style="color: #10B981; font-weight: 600; text-decoration: none;">Create New Account</a>
            </div>
          </div>

          <!-- REGISTRATION PANEL -->
          <div id="register-panel" style="display: none;">
            <div id="reg-step-indicator" style="display: flex; gap: 8px; margin-bottom: 20px; justify-content: center; font-size: 12px; font-weight: 600;">
              <span id="step-1-badge" style="color: #10B981; border-bottom: 2px solid #10B981; padding-bottom: 4px;">1. Account Details</span>
              <span style="color: #475569;">&rarr;</span>
              <span id="step-2-badge" style="color: #64748B; padding-bottom: 4px;">2. Pharmacy Details</span>
            </div>

            <form id="web-register-form">
              <!-- STEP 1 FIELDS -->
              <div id="reg-step-1">
                <div class="form-group" style="margin-bottom: 16px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Owner Full Name *</label>
                  <input type="text" id="reg-owner-name" class="form-input" placeholder="e.g. Ramesh Kumar" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <div class="form-group" style="margin-bottom: 16px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Email Address *</label>
                  <input type="email" id="reg-email" class="form-input" placeholder="e.g. ramesh@example.com" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <div class="form-group" style="margin-bottom: 16px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Password * (min. 6 chars)</label>
                  <input type="password" id="reg-password" class="form-input" placeholder="Create password" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <div class="form-group" style="margin-bottom: 20px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Confirm Password *</label>
                  <input type="password" id="reg-confirm-password" class="form-input" placeholder="Verify password" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <button type="button" id="btn-reg-next" class="btn btn-primary" style="width: 100%; padding: 12px; background: #10B981; border: none; border-radius: 10px; color: #FFFFFF; font-size: 14px; font-weight: 700; cursor: pointer;">
                  Continue to Step 2 &rarr;
                </button>
              </div>

              <!-- STEP 2 FIELDS -->
              <div id="reg-step-2" style="display: none;">
                <div class="form-group" style="margin-bottom: 16px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Pharmacy / Shop Name *</label>
                  <input type="text" id="reg-shop-name" class="form-input" placeholder="e.g. Om Medical Agencies" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <div class="form-group" style="margin-bottom: 16px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Contact Phone Number *</label>
                  <input type="text" id="reg-phone" class="form-input" placeholder="e.g. 9876543210" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <div class="form-group" style="margin-bottom: 16px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">Business Address *</label>
                  <input type="text" id="reg-address" class="form-input" placeholder="e.g. Block C, Okhla, New Delhi" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <div class="form-group" style="margin-bottom: 20px;">
                  <label class="form-label" style="display: block; font-size: 12px; font-weight: 700; color: #CBD5E1; margin-bottom: 6px;">GSTIN (Optional)</label>
                  <input type="text" id="reg-gstin" class="form-input" placeholder="07AABCE1234F1Z5" style="width: 100%; padding: 11px 14px; background: #1E293B; border: 1px solid #475569; border-radius: 10px; color: #FFFFFF; font-size: 13px; box-sizing: border-box;">
                </div>
                <div style="display: flex; gap: 10px;">
                  <button type="button" id="btn-reg-back" class="btn btn-secondary" style="flex: 1; padding: 12px; background: #334155; border: none; border-radius: 10px; color: #E2E8F0; font-size: 14px; font-weight: 700; cursor: pointer;">
                    &larr; Back
                  </button>
                  <button type="submit" id="btn-submit-register" class="btn btn-primary" style="flex: 2; padding: 12px; background: #10B981; border: none; border-radius: 10px; color: #FFFFFF; font-size: 14px; font-weight: 700; cursor: pointer;">
                    Register Account &rarr;
                  </button>
                </div>
              </div>
            </form>
            <div style="margin-top: 20px; text-align: center; font-size: 13px; color: #94A3B8;">
              Already have an account? <a href="javascript:void(0)" id="link-show-login" style="color: #10B981; font-weight: 600; text-decoration: none;">Log In</a>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      const loginPanel = modal.querySelector('#login-panel');
      const registerPanel = modal.querySelector('#register-panel');
      const authTitle = modal.querySelector('#auth-title');
      const authSubtitle = modal.querySelector('#auth-subtitle');
      const authError = modal.querySelector('#auth-error');
      const authSuccess = modal.querySelector('#auth-success');

      // Link toggling
      modal.querySelector('#link-show-register').addEventListener('click', () => {
        loginPanel.style.display = 'none';
        registerPanel.style.display = 'block';
        authTitle.textContent = 'Create ExpiryGuard Account';
        authSubtitle.textContent = 'Step-by-step owner & pharmacy registration';
        authError.style.display = 'none';
        authSuccess.style.display = 'none';
      });

      modal.querySelector('#link-show-login').addEventListener('click', () => {
        registerPanel.style.display = 'none';
        loginPanel.style.display = 'block';
        authTitle.textContent = 'ExpiryGuard';
        authSubtitle.textContent = 'Sign in to access pharmacy counter & inventory';
        authError.style.display = 'none';
        authSuccess.style.display = 'none';
      });

      // Multi-step Navigation
      const step1Div = modal.querySelector('#reg-step-1');
      const step2Div = modal.querySelector('#reg-step-2');
      const step1Badge = modal.querySelector('#step-1-badge');
      const step2Badge = modal.querySelector('#step-2-badge');

      modal.querySelector('#btn-reg-next').addEventListener('click', () => {
        authError.style.display = 'none';
        
        const ownerName = modal.querySelector('#reg-owner-name').value.trim();
        const email = modal.querySelector('#reg-email').value.trim();
        const password = modal.querySelector('#reg-password').value;
        const confirmPassword = modal.querySelector('#reg-confirm-password').value;

        if (!ownerName) {
          authError.textContent = 'Please enter Owner Full Name.';
          authError.style.display = 'block';
          return;
        }
        if (!email) {
          authError.textContent = 'Please enter Email Address.';
          authError.style.display = 'block';
          return;
        }
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
          authError.textContent = 'Please enter a valid Email Address.';
          authError.style.display = 'block';
          return;
        }
        if (!password) {
          authError.textContent = 'Please enter a password.';
          authError.style.display = 'block';
          return;
        }
        if (password.length < 6) {
          authError.textContent = 'Password must be at least 6 characters long.';
          authError.style.display = 'block';
          return;
        }
        if (password !== confirmPassword) {
          authError.textContent = 'Passwords do not match.';
          authError.style.display = 'block';
          return;
        }

        step1Div.style.display = 'none';
        step2Div.style.display = 'block';
        step1Badge.style.color = '#64748B';
        step1Badge.style.borderBottom = 'none';
        step2Badge.style.color = '#10B981';
        step2Badge.style.borderBottom = '2px solid #10B981';
      });

      modal.querySelector('#btn-reg-back').addEventListener('click', () => {
        authError.style.display = 'none';
        step2Div.style.display = 'none';
        step1Div.style.display = 'block';
        step2Badge.style.color = '#64748B';
        step2Badge.style.borderBottom = 'none';
        step1Badge.style.color = '#10B981';
        step1Badge.style.borderBottom = '2px solid #10B981';
      });

      // Submit Login
      document.getElementById('web-login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('login-email').value;
        const pass = document.getElementById('login-password').value;
        const submitBtn = document.getElementById('btn-submit-login');
        
        authError.style.display = 'none';
        authSuccess.style.display = 'none';
        submitBtn.disabled = true;
        submitBtn.textContent = 'Authenticating...';

        try {
          const data = await self.login(email, pass);
          localStorage.removeItem('expiryguard_logged_out');
          localStorage.setItem('expiryguard_user', JSON.stringify(data));
          modal.style.display = 'none';
          
          if (window.location.pathname.includes('index.html') || window.location.pathname.endsWith('/')) {
            window.location.reload();
          } else {
            window.location.href = 'index.html';
          }
        } catch (err) {
          authError.textContent = err.message || 'Invalid User ID / Password';
          authError.style.display = 'block';
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Log In to ExpiryGuard →';
        }
      });

      // Submit Registration
      modal.querySelector('#web-register-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        authError.style.display = 'none';
        authSuccess.style.display = 'none';

        const submitBtn = modal.querySelector('#btn-submit-register');
        const originalText = submitBtn.textContent;

        const ownerName = modal.querySelector('#reg-owner-name').value.trim();
        const email = modal.querySelector('#reg-email').value.trim();
        const password = modal.querySelector('#reg-password').value;
        
        const shopName = modal.querySelector('#reg-shop-name').value.trim();
        const phone = modal.querySelector('#reg-phone').value.trim();
        const address = modal.querySelector('#reg-address').value.trim();
        const gstin = modal.querySelector('#reg-gstin').value.trim();

        if (!shopName) {
          authError.textContent = 'Please enter Pharmacy / Shop Name.';
          authError.style.display = 'block';
          return;
        }
        if (!phone) {
          authError.textContent = 'Please enter Contact Phone Number.';
          authError.style.display = 'block';
          return;
        }
        const phoneRegex = /^\d{10,12}$/;
        if (!phoneRegex.test(phone)) {
          authError.textContent = 'Please enter a valid 10-12 digit phone number.';
          authError.style.display = 'block';
          return;
        }
        if (!address) {
          authError.textContent = 'Please enter Business Address.';
          authError.style.display = 'block';
          return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Registering Account...';

        const payload = {
          shop_name: shopName,
          owner_name: ownerName,
          email: email,
          password: password,
          phone: phone,
          address: address,
          gstin: gstin || "07AABCE1234F1Z5"
        };

        try {
          const regRes = await fetch(`${API_BASE_URL}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });

          const regData = await regRes.json();
          if (!regRes.ok) {
            throw new Error(regData.message || regData.detail || 'Registration failed.');
          }

          authSuccess.textContent = 'Registration successful! Logging in...';
          authSuccess.style.display = 'block';

          // Auto-login
          const loginData = await self.login(email, password);
          localStorage.removeItem('expiryguard_logged_out');
          localStorage.setItem('expiryguard_user', JSON.stringify(loginData));
          
          setTimeout(() => {
            modal.style.display = 'none';
            if (window.location.pathname.includes('index.html') || window.location.pathname.endsWith('/')) {
              window.location.reload();
            } else {
              window.location.href = 'index.html';
            }
          }, 1500);

        } catch (err) {
          authError.textContent = err.message || 'Registration failed.';
          authError.style.display = 'block';
          submitBtn.disabled = false;
          submitBtn.textContent = originalText;
        }
      });

    } else {
      modal.style.display = 'flex';
    }
  }

  // Dashboard API
  async getDashboardSummary(onUpdate = null) {
    return await this.swrRequest('/dashboard/summary', {}, { staleAfterMs: 4000, ttlMs: 60000, onUpdate });
  }

  // Inventory API
  async getProducts(params = {}, onUpdate = null, options = {}) {
    let endpoint = '/products';
    if (params && typeof params === 'object' && Object.keys(params).length > 0) {
      const cleanParams = {};
      for (const [k, v] of Object.entries(params)) {
        if (v !== null && v !== undefined && v !== '') {
          cleanParams[k] = v;
        }
      }
      const q = new URLSearchParams(cleanParams).toString();
      endpoint = `/products?${q}`;
    }
    const isDefault = !params || (Object.keys(params).length === 0) || (params.page === 1 && !params.search && !params.filter && !params.filter_key);
    if (isDefault) {
      return await this.swrRequest(endpoint, options, { staleAfterMs: 8000, ttlMs: 180000, onUpdate });
    }
    return await this.request(endpoint, options);
  }

  async searchCatalog(query, limit = 20) {
    return await this.request(`/catalog/search?query=${encodeURIComponent(query)}&limit=${limit}`);
  }


  // Inventory Soft-Delete & 60-Day Recovery API
  async deleteInventoryStock(stockIds) {
    const res = await this.request('/inventory/delete', {
      method: 'POST',
      body: JSON.stringify({ stock_ids: stockIds })
    });
    this.invalidateCache(['products', 'inventory', 'dashboard', 'reports', 'analytics']);
    localStorage.removeItem('expiryguard_cached_inventory');
    localStorage.removeItem('expiryguard_cached_billing_products');
    return res;
  }

  async deleteAllInventoryStock() {
    const res = await this.request('/inventory/delete-all', {
      method: 'POST',
      body: JSON.stringify({ confirm: true })
    });
    this.invalidateCache(['products', 'inventory', 'dashboard', 'reports', 'analytics']);
    localStorage.removeItem('expiryguard_cached_inventory');
    localStorage.removeItem('expiryguard_cached_billing_products');
    return res;
  }

  async getRecentlyDeletedStock() {
    return await this.request('/inventory/deleted');
  }

  async restoreInventoryStock(stockIds) {
    const res = await this.request('/inventory/restore', {
      method: 'POST',
      body: JSON.stringify({ stock_ids: stockIds })
    });
    this.invalidateCache(['products', 'inventory', 'dashboard', 'reports', 'analytics']);
    localStorage.removeItem('expiryguard_cached_inventory');
    localStorage.removeItem('expiryguard_cached_billing_products');
    return res;
  }

  // Bulk Inventory Import Template
  getImportTemplateUrl() {
    return `${API_BASE_URL}/api/inventory/import-template`;
  }

  async uploadInventorySpreadsheet(file) {
    const formData = new FormData();
    formData.append('file', file);
    return await this.request('/api/inventory/import', {
      method: 'POST',
      body: formData
    });
  }

  // Sales Feed API
  async getSales(skip = 0, limit = 50, onUpdate = null, options = {}) {
    const params = new URLSearchParams({ skip, limit });
    if (options.period) params.append('period', options.period);
    if (options.search) params.append('search', options.search);
    if (options.from_date) params.append('from_date', options.from_date);
    if (options.to_date) params.append('to_date', options.to_date);
    if (options.sales_type) params.append('sales_type', options.sales_type);
    if (options.include_exported) params.append('include_exported', 'true');

    const endpoint = `/sales?${params.toString()}`;
    if (skip === 0 && !options.search && (!options.period || options.period === 'today')) {
      return await this.swrRequest(endpoint, {}, { staleAfterMs: 4000, ttlMs: 60000, onUpdate });
    }
    return await this.request(endpoint);
  }

  async getSale(saleId) {
    return await this.request(`/sales/${saleId}`);
  }

  // Bill Invoice PDF
  getInvoicePdfUrl(saleId) {
    return `${API_BASE_URL}/billing/${saleId}/pdf`;
  }

  // Export Sales CSV and notify system of mutation
  async exportSalesCsv(reExport = false) {
    const endpoint = `/reports/export/sales?re_export=${reExport}`;
    const headers = await this.getHeaders(false);
    const isFileOrigin = (window.location.protocol === 'file:' || !window.location.origin || window.location.origin === 'null');
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'GET',
      credentials: isFileOrigin ? 'omit' : 'include',
      headers
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Export failed (${response.status}): ${errText}`);
    }

    const exportedCount = parseInt(response.headers.get('X-Exported-Count') || '0', 10);
    const blob = await response.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = 'expiryguard_sales_export.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);

    // Invalidate client-side caches and notify all listeners
    this.invalidateCache();
    localStorage.removeItem('expiryguard_cached_sales');
    if (window.AppDataPreloader && typeof window.AppDataPreloader.clear === 'function') {
      window.AppDataPreloader.clear();
    }
    window.dispatchEvent(new CustomEvent('dawaiflow:mutate', { detail: { tag: 'sales' } }));

    return { success: true, count: exportedCount };
  }

  // Returns API
  async getTodaysReturns(onUpdate = null) {
    return await this.swrRequest('/billing/returns/today', {}, { staleAfterMs: 4000, ttlMs: 60000, onUpdate });
  }

  async processReturn(payload) {
    return await this.request('/billing/returns', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // Reports & Intelligence API
  async getReportsSummary(onUpdate = null) {
    return await this.swrRequest('/reports/summary', {}, { staleAfterMs: 15000, ttlMs: 120000, onUpdate });
  }

  async getInventoryIntelligence(params = {}, onUpdate = null) {
    const query = new URLSearchParams();
    if (params.category && params.category !== 'all') query.append('category', params.category);
    if (params.supplier_id) query.append('supplier_id', params.supplier_id);
    if (params.priority_level && params.priority_level !== 'ALL') query.append('priority_level', params.priority_level);
    if (params.debug) query.append('debug', 'true');
    if (params.limit) query.append('limit', params.limit);
    if (params.offset) query.append('offset', params.offset);
    
    const qs = query.toString();
    const endpoint = `/inventory/intelligence${qs ? '?' + qs : ''}`;
    return await this.swrRequest(endpoint, {}, { staleAfterMs: 15000, ttlMs: 120000, onUpdate });
  }

  // AI Scanning API
  async scanLabel(file) {
    const formData = new FormData();
    formData.append('file', file);
    return await this.request('/scan-label', {
      method: 'POST',
      body: formData
    });
  }

  async scanMultiItem(file) {
    const formData = new FormData();
    formData.append('file', file);
    return await this.request('/scan-multi-item', {
      method: 'POST',
      body: formData
    });
  }

  async completeSale(payload) {
    return await this.request('/billing/confirm', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // User Profile & Settings API
  async getUserProfile() {
    return await this.request('/user/profile');
  }

  async updateUserProfile(payload) {
    return await this.request('/user/profile', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  async changePassword(payload) {
    return await this.request('/user/change-password', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async deleteSale(saleId) {
    return await this.request(`/sales/${saleId}`, {
      method: 'DELETE'
    });
  }

  async getHsnRates() {
    return await this.request('/hsn/rates');
  }

  async lookupHsn(code) {
    return await this.request(`/hsn/lookup?hsn_code=${code}`);
  }

  async getUnmappedHsnLogs() {
    return await this.request('/hsn/unmapped-logs');
  }

  // Supplier Management API
  async getSuppliers(query = '', status = 'ALL', onUpdate = null) {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    if (status && status !== 'ALL') params.append('status', status);
    const qs = params.toString();
    const endpoint = `/suppliers${qs ? '?' + qs : ''}`;
    if (!query && (!status || status === 'ALL')) {
      return await this.swrRequest(endpoint, {}, { staleAfterMs: 20000, ttlMs: 600000, onUpdate });
    }
    return await this.request(endpoint);
  }

  async getSupplierDetail(supplierId) {
    return await this.request(`/suppliers/${supplierId}`);
  }

  async matchSupplier(name, gstin = '') {
    const params = new URLSearchParams();
    if (name) params.append('name', name);
    if (gstin) params.append('gstin', gstin);
    return await this.request(`/suppliers/match?${params.toString()}`);
  }

  async createSupplier(payload) {
    return await this.request('/suppliers', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updateSupplier(supplierId, payload) {
    return await this.request(`/suppliers/${supplierId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  async deleteSupplier(supplierId) {
    return await this.request(`/suppliers/${supplierId}`, {
      method: 'DELETE'
    });
  }

  async getSupplierPurchases(supplierId) {
    return await this.request(`/suppliers/${supplierId}/purchases`);
  }

  async getSupplierInventory(supplierId) {
    return await this.request(`/suppliers/${supplierId}/inventory`);
  }

  // Document Management API
  async uploadDocument(formData) {
    return await this.request('/documents/upload', {
      method: 'POST',
      body: formData
    });
  }

  async triggerDocumentOcr(documentId) {
    return await this.request(`/documents/${documentId}/ocr`, {
      method: 'POST'
    });
  }

  async getDocuments(query = '', docType = 'all', status = 'all', supplierId = '', onUpdate = null) {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    if (docType && docType !== 'all') params.append('doc_type', docType);
    if (status && status !== 'all') params.append('status', status);
    if (supplierId) params.append('supplier_id', supplierId);
    const qs = params.toString();
    const endpoint = `/documents${qs ? '?' + qs : ''}`;
    if (!query && (!docType || docType === 'all') && (!status || status === 'all') && !supplierId) {
      return await this.swrRequest(endpoint, {}, { staleAfterMs: 15000, ttlMs: 120000, onUpdate });
    }
    return await this.request(endpoint);
  }

  async getDocumentDetail(documentId) {
    return await this.request(`/documents/${documentId}`);
  }

  async confirmDocument(documentId, payload) {
    return await this.request(`/documents/${documentId}/confirm`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async deleteDocument(documentId) {
    return await this.request(`/documents/${documentId}`, {
      method: 'DELETE'
    });
  }

  // Inventory Flow Helper APIs
  async checkDuplicateBatch(productName, batchNumber) {
    return await this.request('/inventory/check-duplicate', {
      method: 'POST',
      body: JSON.stringify({ product_name: productName, batch_number: batchNumber })
    });
  }

  async createCustomMedicine(payload) {
    return await this.request('/catalog/create-custom', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async batchAddInventory(items) {
    return await this.request('/inventory/batch-add', {
      method: 'POST',
      body: JSON.stringify({ items: items })
    });
  }

  async uploadInventorySpreadsheet(file, onDuplicate = 'update') {
    const formData = new FormData();
    formData.append('file', file);
    return await this.request(`/inventory/import?on_duplicate=${encodeURIComponent(onDuplicate)}`, {
      method: 'POST',
      body: formData
    });
  }

  // Real-Time Polling Engine (5 seconds default)
  startPolling(fn, intervalMs = 5000) {
    fn(); // Immediate execution
    return setInterval(fn, intervalMs);
  }

  // Billing & Customer Methods
  async createSale(payload) {
    const customHeaders = {};
    if (payload && payload.idempotency_key) {
      customHeaders['X-Idempotency-Key'] = payload.idempotency_key;
    }
    return await this.request('/sales', {
      method: 'POST',
      headers: customHeaders,
      body: JSON.stringify(payload)
    });
  }

  async getCustomers(onUpdate = null) {
    return await this.swrRequest('/customers', {}, { staleAfterMs: 15000, ttlMs: 300000, onUpdate });
  }

  async searchCustomer(phone) {
    return await this.request(`/customers/search?phone=${encodeURIComponent(phone)}`);
  }

  async getKhataDashboard(onUpdate = null) {
    return await this.swrRequest('/khata/dashboard', {}, { staleAfterMs: 5000, ttlMs: 60000, onUpdate });
  }

  async createCustomer(payload) {
    return await this.request('/customers', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getCustomerLedger(customerId) {
    return await this.request(`/customers/${customerId}/ledger`);
  }

  async createCustomerPayment(customerId, payload) {
    return await this.request(`/customers/${customerId}/payments`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // ==========================================
  // HELD BILLS (PARK / RESUME)
  // ==========================================

  async createHeldBill(payload) {
    return await this.request('/billing/held', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getHeldBills(status = 'HELD', search = '') {
    let url = `/billing/held?status=${encodeURIComponent(status)}`;
    if (search && search.trim()) {
      url += `&search=${encodeURIComponent(search.trim())}`;
    }
    return await this.request(url);
  }

  async getHeldBillsCount() {
    return await this.request('/billing/held/count');
  }

  async getHeldBillById(heldBillId) {
    return await this.request(`/billing/held/${heldBillId}`);
  }

  async resumeHeldBill(heldBillId) {
    return await this.request(`/billing/held/${heldBillId}/resume`, {
      method: 'POST'
    });
  }

  async cancelHeldBill(heldBillId) {
    return await this.request(`/billing/held/${heldBillId}`, {
      method: 'DELETE'
    });
  }

  // ==========================================
  // CA CONNECT & TAX REPORTING
  // ==========================================

  async getCaProfile() {
    return await this.request('/ca-connect/profile');
  }

  async saveCaProfile(payload) {
    return await this.request('/ca-connect/profile', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async deleteCaProfile() {
    return await this.request('/ca-connect/profile', {
      method: 'DELETE'
    });
  }

  async getCaShareHistory() {
    return await this.request('/ca-connect/history');
  }

  async shareReportsWithCa(payload) {
    return await this.request('/ca-connect/share', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getGstFinancialSummary(preset = 'this_month', startDate = null, endDate = null) {
    let url = `/reports/gst-financial-summary?preset=${encodeURIComponent(preset)}`;
    if (startDate && endDate) {
      url += `&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`;
    }
    return await this.request(url);
  }

  async getGmailStatus() {
    return await this.request('/ca-connect/gmail/status');
  }

  async disconnectGmail() {
    return await this.request('/ca-connect/gmail/disconnect', {
      method: 'DELETE'
    });
  }

  // ==========================================
  // STAFF & RBAC MANAGEMENT
  // ==========================================

  async getStaffMembers(onUpdate = null) {
    return await this.swrRequest('/staff', {}, { staleAfterMs: 20000, ttlMs: 600000, onUpdate });
  }

  async createStaffMember(payload) {
    return await this.request('/staff', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updateStaffMember(staffId, payload) {
    return await this.request(`/staff/${staffId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  async deleteStaffMember(staffId) {
    return await this.request(`/staff/${staffId}`, {
      method: 'DELETE'
    });
  }

  async toggleStaffStatus(staffId) {
    return await this.request(`/staff/${staffId}/toggle-status`, {
      method: 'PATCH'
    });
  }

  async resetStaffPassword(staffId, newPassword) {
    return await this.request(`/staff/${staffId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword })
    });
  }

  async getStaffCredentials(staffId) {
    return await this.request(`/staff/${staffId}/credentials`);
  }

  async updateStaffCredentials(staffId, payload) {
    return await this.request(`/staff/${staffId}/credentials`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  // ==========================================
  // STORE BRANCHES
  // ==========================================

  async getStoreBranches(onUpdate = null) {
    return await this.swrRequest('/branches', {}, { staleAfterMs: 20000, ttlMs: 600000, onUpdate });
  }

  async createStoreBranch(payload) {
    return await this.request('/branches', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updateStoreBranch(branchId, payload) {
    return await this.request(`/branches/${branchId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  async toggleBranchStatus(branchId) {
    return await this.request(`/branches/${branchId}/toggle-status`, {
      method: 'PATCH'
    });
  }

  async deleteStoreBranch(branchId) {
    return await this.request(`/branches/${branchId}`, {
      method: 'DELETE'
    });
  }

  // ==========================================
  // REPORTS & ANALYTICS
  // ==========================================

  async getReportsAnalytics(period = 'this_month', startDate = null, endDate = null, onUpdate = null) {
    let url = `/reports/analytics?period=${encodeURIComponent(period)}`;
    if (startDate) {
      url += `&start_date=${encodeURIComponent(startDate)}`;
    }
    if (endDate) {
      url += `&end_date=${encodeURIComponent(endDate)}`;
    }
    return await this.swrRequest(url, {}, { staleAfterMs: 10000, ttlMs: 120000, onUpdate });
  }

  // ==========================================
  // BACKUP & RESTORE
  // ==========================================

  async createBackup(notes = '') {
    return await this.request('/backup/create', {
      method: 'POST',
      body: JSON.stringify({ notes: notes || '' })
    });
  }

  async getBackupHistory(limit = 50) {
    return await this.request(`/backup/history?limit=${limit}`);
  }

  getBackupDownloadUrl(backupId) {
    const token = this.getToken();
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : '';
    return `${API_BASE_URL}/backup/download/${encodeURIComponent(backupId)}${tokenQuery}`;
  }

  async restoreBackup(backupId) {
    return await this.request('/backup/restore', {
      method: 'POST',
      body: JSON.stringify({ backup_id: backupId })
    });
  }

  async uploadAndRestoreBackup(file) {
    const formData = new FormData();
    formData.append('file', file);
    return await this.request('/backup/upload-restore', {
      method: 'POST',
      body: formData
    });
  }

  async deleteBackup(backupId) {
    return await this.request(`/backup/${encodeURIComponent(backupId)}`, {
      method: 'DELETE'
    });
  }

  // Data Migration & Historical Bill Import
  async uploadMigrationFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    return await this.request('/api/migration/upload', {
      method: 'POST',
      body: formData
    });
  }

  async getMigrationPreview(migrationId) {
    return await this.request(`/api/migration/preview/${encodeURIComponent(migrationId)}`);
  }

  async confirmMigration(migrationId) {
    return await this.request(`/api/migration/confirm/${encodeURIComponent(migrationId)}`, {
      method: 'POST'
    });
  }

  async getMigrationStatus(migrationId) {
    return await this.request(`/api/migration/status/${encodeURIComponent(migrationId)}`);
  }

  async rollbackMigration(migrationId) {
    return await this.request(`/api/migration/rollback/${encodeURIComponent(migrationId)}`, {
      method: 'POST'
    });
  }

  async getMigrationHistory() {
    return await this.request('/api/migration/history');
  }

  async getActiveMigration() {
    return await this.request('/api/migration/active');
  }

  getMigrationErrorExportUrl(migrationId) {
    return `${API_BASE_URL}/api/migration/errors/${encodeURIComponent(migrationId)}/export`;
  }

  async searchBillingProducts(query, searchMode = 'name', limit = 15, signal = null) {
    const ep = `/billing/search-products?query=${encodeURIComponent(query)}&search_mode=${encodeURIComponent(searchMode)}&limit=${limit}`;
    const opts = signal ? { signal } : {};
    const res = await this.request(ep, opts);
    return Array.isArray(res) ? res : (res && Array.isArray(res.items) ? res.items : []);
  }
}

const api = new ApiClient();
window.api = api;
