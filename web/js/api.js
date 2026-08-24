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
  }

  getToken() {
    return localStorage.getItem(this.tokenKey);
  }

  setToken(token) {
    localStorage.setItem(this.tokenKey, token);
  }

  logout() {
    localStorage.removeItem(this.tokenKey);
    window.location.reload();
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
        // Clear stale/expired token and force refresh session token
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

  // Auth Methods
  async login(email, password) {
    const res = await fetch(`${API_BASE_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), password: password })
    });

    const data = await res.json();
    if (!res.ok || !data.access_token) {
      throw new Error(data.message || data.detail || 'Invalid email or password');
    }

    this.setToken(data.access_token);
    return data;
  }

  showLoginModal() {
    let modal = document.getElementById('login-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'login-modal';
      modal.className = 'modal-overlay active';
      modal.innerHTML = `
        <div class="modal-card" style="max-width: 400px;">
          <div class="modal-header">
            <h3 class="panel-title">ExpiryGuard Login</h3>
          </div>
          <form id="web-login-form">
            <div class="form-group">
              <label class="form-label">Email Address</label>
              <input type="email" id="login-email" class="form-input" required placeholder="doctor@pharmacy.com">
            </div>
            <div class="form-group">
              <label class="form-label">Password</label>
              <input type="password" id="login-password" class="form-input" required placeholder="••••••••">
            </div>
            <div id="login-error" style="color: var(--error-red); font-size: 13px; margin-bottom: 12px; display: none;"></div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Sign In</button>
          </form>
        </div>
      `;
      document.body.appendChild(modal);

      document.getElementById('web-login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('login-email').value;
        const pass = document.getElementById('login-password').value;
        const errDiv = document.getElementById('login-error');
        errDiv.style.display = 'none';

        try {
          await this.login(email, pass);
          modal.classList.remove('active');
          window.location.reload();
        } catch (err) {
          errDiv.textContent = err.message;
          errDiv.style.display = 'block';
        }
      });
    } else {
      modal.classList.add('active');
    }
  }

  // Dashboard API
  async getDashboardSummary() {
    return await this.request('/dashboard/summary');
  }

  // Inventory API
  async getProducts() {
    return await this.request('/products');
  }

  async searchCatalog(query, limit = 20) {
    return await this.request(`/catalog/search?query=${encodeURIComponent(query)}&limit=${limit}`);
  }

  // Inventory Soft-Delete & 60-Day Recovery API
  async deleteInventoryStock(stockIds) {
    return await this.request('/inventory/delete', {
      method: 'POST',
      body: JSON.stringify({ stock_ids: stockIds })
    });
  }

  async deleteAllInventoryStock() {
    return await this.request('/inventory/delete-all', {
      method: 'POST',
      body: JSON.stringify({ confirm: true })
    });
  }

  async getRecentlyDeletedStock() {
    return await this.request('/inventory/deleted');
  }

  async restoreInventoryStock(stockIds) {
    return await this.request('/inventory/restore', {
      method: 'POST',
      body: JSON.stringify({ stock_ids: stockIds })
    });
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
  async getSales(skip = 0, limit = 50) {
    return await this.request(`/sales?skip=${skip}&limit=${limit}`);
  }

  // Bill Invoice PDF
  getInvoicePdfUrl(saleId) {
    return `${API_BASE_URL}/sales/${saleId}/pdf`;
  }

  // Returns API
  async getTodaysReturns() {
    return await this.request('/billing/returns/today');
  }

  async processReturn(payload) {
    return await this.request('/billing/returns', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // Reports API
  async getReportsSummary() {
    return await this.request('/reports/summary');
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
  async getSuppliers(query = '', status = 'ALL') {
    return await this.request(`/suppliers?query=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`);
  }

  async getSupplierDetail(supplierId) {
    return await this.request(`/suppliers/${supplierId}`);
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

  async getDocuments(query = '', docType = 'all', status = 'all', supplierId = '') {
    return await this.request(`/documents?query=${encodeURIComponent(query)}&doc_type=${encodeURIComponent(docType)}&status=${encodeURIComponent(status)}&supplier_id=${supplierId}`);
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

  // Real-Time Polling Engine (5 seconds default)
  startPolling(fn, intervalMs = 5000) {
    fn(); // Immediate execution
    return setInterval(fn, intervalMs);
  }

  // Billing & Customer Methods
  async createSale(payload) {
    return await this.request('/sales', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getCustomers() {
    return await this.request('/customers');
  }

  async searchCustomer(phone) {
    return await this.request(`/customers/search?phone=${encodeURIComponent(phone)}`);
  }

  // Restock Suggestions API
  async getRestockSuggestions(reasonFilter = 'all', sortBy = 'demand', search = '', multiplier = 3.0) {
    const params = new URLSearchParams({
      reason_filter: reasonFilter,
      sort_by: sortBy,
      search: search,
      multiplier: multiplier
    });
    return await this.request(`/inventory/restock-suggestions?${params.toString()}`);
  }
}

const api = new ApiClient();
window.api = api;
