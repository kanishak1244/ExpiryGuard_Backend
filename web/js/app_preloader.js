/* ==========================================================================
   DAWAIFLOW — GLOBAL APP DATA PRELOADING & INSTANT NAVIGATION SYSTEM
   Provides 0ms perceived delay across all application modules:
   - Session restore & RBAC identity scoping
   - Tier 1: Instant /app/bootstrap preloading (Dashboard, Inventory KPIs, Khata, Sales)
   - Tier 2: Parallel background prefetch of permitted modules
   - Tier 3: Idle prefetch for secondary items (Intelligence, Documents)
   - SWR cache with request deduplication & automatic mutation invalidation
   ========================================================================== */

(function(window) {
  'use strict';

  class AppDataPreloaderEngine {
    constructor() {
      this.cache = new Map(); // in-memory Map: key -> { data, ts, ttl }
      this.inFlight = new Map(); // in-flight Promise deduplication: key -> Promise
      this.prefix = 'df_pre_';
      this.userProfile = null;
      this.allowedModules = new Set();
      this.isPreloaded = false;
      this.isPreloading = false;
      this.initPromise = null;

      // Identity-scoped key generator
      this._bindEvents();
    }

    _bindEvents() {
      // Automatic cache invalidation listener for system mutations
      window.addEventListener('dawaiflow:mutate', (e) => {
        if (e.detail && e.detail.tag) {
          this.invalidateTag(e.detail.tag);
        }
      });

      // Cross-tab synchronization
      window.addEventListener('storage', (e) => {
        if (e.key && e.key.startsWith(this.prefix)) {
          const raw = e.newValue;
          if (raw) {
            try {
              const entry = JSON.parse(raw);
              const key = e.key.replace(this.prefix, '');
              this.cache.set(key, entry);
            } catch (_) {}
          }
        }
      });
    }

    _getScopedPrefix() {
      const u = this.userProfile || this.getCachedProfile();
      const shopId = (u && (u.shop_id || u.id)) || 'default';
      const userId = (u && u.id) || 'guest';
      const branchId = (u && u.branch_id) || 'main';
      return `shop:${shopId}:user:${userId}:branch:${branchId}:`;
    }

    getCachedProfile() {
      try {
        const raw = localStorage.getItem('expiryguard_cached_user_profile');
        if (raw) return JSON.parse(raw);
      } catch (_) {}
      return null;
    }

    getCacheKey(endpoint) {
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
      return this._getScopedPrefix() + cleanEndpoint;
    }

    set(endpoint, data, ttlMs = 180000) {
      const key = this.getCacheKey(endpoint);
      const entry = { data, ts: Date.now(), ttl: ttlMs };
      this.cache.set(key, entry);

      // Also hydrate into api.js cache if available
      if (window.api && typeof window.api.setCached === 'function') {
        window.api.setCached(endpoint, data, ttlMs);
      }

      // Persist in sessionStorage for instant module navigation across pages
      try {
        sessionStorage.setItem(this.prefix + key, JSON.stringify(entry));
      } catch (_) {}
    }

    get(endpoint, maxAgeMs = null) {
      const key = this.getCacheKey(endpoint);
      let entry = this.cache.get(key);

      if (!entry) {
        // Try sessionStorage
        try {
          const raw = sessionStorage.getItem(this.prefix + key);
          if (raw) {
            entry = JSON.parse(raw);
            if (entry) this.cache.set(key, entry);
          }
        } catch (_) {}
      }

      if (!entry) {
        // Try api.js cache fallback
        if (window.api && typeof window.api.getCached === 'function') {
          const apiCached = window.api.getCached(endpoint);
          if (apiCached) return apiCached.data !== undefined ? apiCached.data : apiCached;
        }
        return null;
      }

      const limit = maxAgeMs !== null ? maxAgeMs : (entry.ttl || 180000);
      if (Date.now() - entry.ts > limit) {
        return null;
      }
      return entry.data;
    }

    has(endpoint, maxAgeMs = null) {
      return this.get(endpoint, maxAgeMs) !== null;
    }

    invalidateTag(tag) {
      const tagLower = String(tag).toLowerCase();
      const keysToPurge = [];

      // Determine endpoints affected by this mutation tag
      for (const [key] of this.cache.entries()) {
        const keyLower = key.toLowerCase();
        if (
          keyLower.includes(tagLower) ||
          (tagLower === 'sales' && (keyLower.includes('/sales') || keyLower.includes('/dashboard') || keyLower.includes('/app/bootstrap') || keyLower.includes('/reports'))) ||
          (tagLower === 'inventory' && (keyLower.includes('/products') || keyLower.includes('/inventory') || keyLower.includes('/app/bootstrap') || keyLower.includes('/dashboard'))) ||
          (tagLower === 'khata' && (keyLower.includes('/khata') || keyLower.includes('/customers') || keyLower.includes('/app/bootstrap'))) ||
          (tagLower === 'returns' && (keyLower.includes('/returns') || keyLower.includes('/billing/returns') || keyLower.includes('/app/bootstrap'))) ||
          (tagLower === 'staff' && keyLower.includes('/staff')) ||
          (tagLower === 'branches' && keyLower.includes('/branches')) ||
          (tagLower === 'ca' && keyLower.includes('/ca'))
        ) {
          keysToPurge.push(key);
        }
      }

      for (const k of keysToPurge) {
        this.cache.delete(k);
        try {
          sessionStorage.removeItem(this.prefix + k);
        } catch (_) {}
      }

      // Sync with api.js cache invalidator
      if (window.api && typeof window.api.invalidateCache === 'function') {
        window.api.invalidateCache([tagLower, 'bootstrap']);
      }
    }

    async preloadAll() {
      if (this.initPromise) return this.initPromise;

      this.initPromise = (async () => {
        const token = window.api ? window.api.getToken() : localStorage.getItem('expiryguard_token');
        if (!token) return;

        this.isPreloading = true;

        // Step 1: Session & Profile Check
        let profile = this.getCachedProfile();
        if (!profile && window.api && typeof window.api.getUserProfile === 'function') {
          try {
            profile = await window.api.getUserProfile();
            if (profile) {
              localStorage.setItem('expiryguard_cached_user_profile', JSON.stringify(profile));
            }
          } catch (_) {}
        }
        if (profile) {
          this.userProfile = profile;
        }

        // Step 2: Tier 1 - App Bootstrap (Highest Priority, Consolidated Single Call)
        let bootstrapData = null;
        try {
          const res = await (window.api ? window.api.request('/app/bootstrap') : fetch('/app/bootstrap', {
            headers: { 'Authorization': `Bearer ${token}` }
          }).then(r => r.json()));

          if (res && res.user) {
            bootstrapData = res;
            this.userProfile = res.user;
            localStorage.setItem('expiryguard_cached_user_profile', JSON.stringify(res.user));

            if (Array.isArray(res.allowed_modules)) {
              this.allowedModules = new Set(res.allowed_modules);
            }

            // Hydrate Tier 1 Module Caches immediately
            this.set('/app/bootstrap', res, 300000);

            if (res.dashboard_summary) {
              this.set('/dashboard/summary', res.dashboard_summary, 120000);
            }
            if (res.inventory_summary) {
              this.set('/inventory/summary', res.inventory_summary, 120000);
            }
            if (res.khata_summary) {
              this.set('/khata/dashboard', res.khata_summary, 120000);
            }
            if (res.recent_sales) {
              this.set('/sales?skip=0&limit=10', res.recent_sales, 120000);
              if (window.cacheSales) window.cacheSales(res.recent_sales);
            }
            if (res.today_returns) {
              this.set('/billing/returns/today', res.today_returns, 120000);
            }

            // Render Sidebar with fresh permitted modules
            if (window.ExpiryNav && typeof window.ExpiryNav.render === 'function') {
              window.ExpiryNav.render();
            }

            // Dispatch global event for ready components
            window.dispatchEvent(new CustomEvent('dawaiflow:bootstrap-ready', { detail: res }));
          }
        } catch (bootErr) {
          console.warn('[Preloader] Tier 1 bootstrap fallback:', bootErr);
        }

        // Step 3: Tier 2 - Module Data Parallel Prefetch (Filtered by RBAC permissions)
        const isPermitted = (modId) => {
          if (!this.allowedModules || this.allowedModules.size === 0) return true;
          return this.allowedModules.has(modId);
        };

        const tier2Tasks = [];

        // Products first page
        if (isPermitted('inventory') || isPermitted('billing')) {
          tier2Tasks.push(
            this._prefetchEndpoint('/products?page=1&limit=50', (prods) => {
              if (Array.isArray(prods)) {
                this.set('/products', prods, 180000);
                localStorage.setItem('expiryguard_cached_billing_products', JSON.stringify(prods));
                localStorage.setItem('expiryguard_cached_inventory', JSON.stringify(prods.slice(0, 50)));
              } else if (prods && Array.isArray(prods.items)) {
                this.set('/products', prods.items, 180000);
                localStorage.setItem('expiryguard_cached_billing_products', JSON.stringify(prods.items));
                localStorage.setItem('expiryguard_cached_inventory', JSON.stringify(prods.items));
              }
            })
          );
        }

        // Customers list
        if (isPermitted('billing') || isPermitted('khata')) {
          tier2Tasks.push(
            this._prefetchEndpoint('/customers', (custs) => {
              if (Array.isArray(custs)) {
                this.set('/customers', custs, 180000);
                localStorage.setItem('expiryguard_cached_billing_customers', JSON.stringify(custs));
                localStorage.setItem('expiryguard_cached_customers', JSON.stringify(custs));
              }
            })
          );
        }

        // Suppliers list
        if (isPermitted('suppliers') || isPermitted('documents')) {
          tier2Tasks.push(
            this._prefetchEndpoint('/suppliers', (sups) => {
              if (Array.isArray(sups)) {
                this.set('/suppliers', sups, 180000);
                localStorage.setItem('expiryguard_cached_suppliers', JSON.stringify(sups));
              }
            })
          );
        }

        // Full sales list (first 50)
        if (isPermitted('sales')) {
          tier2Tasks.push(
            this._prefetchEndpoint('/sales?skip=0&limit=50', (sales) => {
              if (Array.isArray(sales)) {
                this.set('/sales?skip=0&limit=50', sales, 120000);
                localStorage.setItem('expiryguard_cached_sales', JSON.stringify(sales));
                if (window.cacheSales) window.cacheSales(sales);
              }
            })
          );
        }

        // Staff members
        if (isPermitted('staff')) {
          tier2Tasks.push(
            this._prefetchEndpoint('/staff', (st) => {
              if (Array.isArray(st)) {
                this.set('/staff', st, 300000);
              }
            })
          );
        }

        // Branches list
        if (isPermitted('branches')) {
          tier2Tasks.push(
            this._prefetchEndpoint('/branches', (br) => {
              if (Array.isArray(br)) {
                this.set('/branches', br, 300000);
              }
            })
          );
        }

        // Reports summary & analytics today
        if (isPermitted('reports') || isPermitted('ca-connect')) {
          tier2Tasks.push(
            this._prefetchEndpoint('/reports/analytics?period=today', (rep) => {
              if (rep) {
                this.set('/reports/analytics?period=today', rep, 120000);
                localStorage.setItem('expiryguard_cached_reports', JSON.stringify(rep));
              }
            })
          );
          tier2Tasks.push(
            this._prefetchEndpoint('/reports/summary', (sum) => {
              if (sum) this.set('/reports/summary', sum, 120000);
            })
          );
          tier2Tasks.push(
            this._prefetchEndpoint('/ca/profile', (ca) => {
              if (ca) this.set('/ca/profile', ca, 300000);
            })
          );
        }

        // Execute all Tier 2 tasks in parallel
        await Promise.allSettled(tier2Tasks);

        this.isPreloaded = true;
        this.isPreloading = false;

        // Step 4: Tier 3 - Idle Prefetch for secondary items
        this._scheduleTier3IdlePrefetch(isPermitted);

        return bootstrapData;
      })();

      return this.initPromise;
    }

    _prefetchEndpoint(endpoint, onLoaded) {
      const flightKey = 'PREFETCH:' + endpoint;
      if (this.inFlight.has(flightKey)) {
        return this.inFlight.get(flightKey);
      }

      const p = (async () => {
        try {
          if (!window.api || !window.api.getToken()) return;
          const data = await window.api.request(endpoint).catch(() => null);
          if (data !== null && data !== undefined) {
            this.set(endpoint, data);
            if (typeof onLoaded === 'function') onLoaded(data);
          }
          return data;
        } finally {
          this.inFlight.delete(flightKey);
        }
      })();

      this.inFlight.set(flightKey, p);
      return p;
    }

    _scheduleTier3IdlePrefetch(isPermitted) {
      const runTier3 = () => {
        if (!window.api || !window.api.getToken()) return;

        const idleEndpoints = [];
        if (isPermitted('smart-restock') || isPermitted('inventory')) {
          idleEndpoints.push('/inventory/intelligence');
        }
        if (isPermitted('ca-connect')) {
          idleEndpoints.push('/ca/financial-summary?preset=current_month');
          idleEndpoints.push('/ca/share-history?limit=50');
        }

        idleEndpoints.forEach((ep, idx) => {
          setTimeout(() => {
            if (!this.has(ep)) {
              this._prefetchEndpoint(ep);
            }
          }, idx * 150);
        });
      };

      if ('requestIdleCallback' in window) {
        window.requestIdleCallback(runTier3, { timeout: 3000 });
      } else {
        setTimeout(runTier3, 1000);
      }
    }
  }

  // Create singleton instance
  window.AppDataPreloader = new AppDataPreloaderEngine();

  // Kick off preloading immediately upon script evaluation if user is authenticated
  if (typeof document !== 'undefined') {
    const startPreload = () => {
      const token = localStorage.getItem('expiryguard_token');
      const isLoggedOut = localStorage.getItem('expiryguard_logged_out') === 'true';
      if (token && !isLoggedOut) {
        window.AppDataPreloader.preloadAll().catch(e => console.warn('[Preloader] Startup notice:', e));
      }
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', startPreload);
    } else {
      startPreload();
    }
  }

})(typeof window !== 'undefined' ? window : this);
