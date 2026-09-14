/* ==========================================================================
   EXPIRYGUARD WEB APP — STORE BRANCHES DIRECTORY CONTROLLER
   ========================================================================== */

window.BranchesApp = {
  branchList: [],
  canEdit: true,

  async init() {
    try {
      if (window.api) {
        await api.ensureAuthenticated();
      }
    } catch (e) {
      console.warn('Authentication check failed:', e);
    }

    const cached = localStorage.getItem('expiryguard_cached_user_profile');
    if (cached) {
      try {
        const u = JSON.parse(cached);
        const role = (u.role || 'OWNER').toUpperCase();
        const perms = u.permissions || [];
        this.canEdit = u.is_owner === true || role === 'OWNER' || role === 'ADMIN' || perms.includes('SETTINGS_EDIT') || perms.includes('*');
      } catch (e) {}
    }

    const addBtn = document.getElementById('btn-open-add-branch');
    if (addBtn && !this.canEdit) {
      addBtn.style.display = 'none';
    }

    await this.loadBranches();
  },

  async loadBranches() {
    const tbody = document.getElementById('branches-table-body');
    
    // Check 0ms cached branches first before network from AppDataPreloader or cache
    const preloaderBranches = window.AppDataPreloader ? window.AppDataPreloader.get('/branches') : null;
    const apiCached = window.api && typeof window.api.getCached === 'function' ? window.api.getCached('/branches') : null;
    const cachedBranches = preloaderBranches || (apiCached && apiCached.data !== undefined ? apiCached.data : apiCached);
    if (Array.isArray(cachedBranches) && cachedBranches.length > 0) {
      this.branchList = cachedBranches;
      this.renderStats();
      this.filterBranches();
    } else if (tbody && !tbody.children.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 36px;">Loading store branches...</td></tr>`;
    }

    try {
      const data = await api.getStoreBranches();
      this.branchList = Array.isArray(data) ? data : [];
      this.renderStats();
      this.filterBranches();
    } catch (err) {
      console.error('Failed to load branches:', err);
      if (tbody && (!this.branchList || this.branchList.length === 0)) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--status-danger, #EF4444); padding: 36px;">Failed to load store branches: ${escapeHtml(err.message || 'Unknown error')}</td></tr>`;
      }
    }
  },

  renderStats() {
    const total = this.branchList.length;
    const active = this.branchList.filter(b => (b.status || '').toUpperCase() === 'ACTIVE').length;
    const mainBranch = this.branchList.find(b => b.is_main === true);
    const cities = new Set(this.branchList.map(b => (b.city || '').trim()).filter(Boolean));

    const elTotal = document.getElementById('stat-total-branches');
    const elActive = document.getElementById('stat-active-branches');
    const elMain = document.getElementById('stat-main-branch-name');
    const elCities = document.getElementById('stat-cities-count');

    if (elTotal) elTotal.textContent = total;
    if (elActive) elActive.textContent = active;
    if (elMain) elMain.textContent = mainBranch ? mainBranch.branch_name : 'None';
    if (elCities) elCities.textContent = cities.size;
  },

  filterBranches() {
    const searchVal = (document.getElementById('branch-search-input')?.value || '').toLowerCase().trim();
    if (!searchVal) {
      this.renderBranchesTable(this.branchList);
      return;
    }

    const filtered = this.branchList.filter(b => {
      const name = (b.branch_name || '').toLowerCase();
      const code = (b.code || '').toLowerCase();
      const city = (b.city || '').toLowerCase();
      const phone = (b.phone || '').toLowerCase();
      const address = (b.address || '').toLowerCase();
      return name.includes(searchVal) || code.includes(searchVal) || city.includes(searchVal) || phone.includes(searchVal) || address.includes(searchVal);
    });

    this.renderBranchesTable(filtered);
  },

  renderBranchesTable(list) {
    const tbody = document.getElementById('branches-table-body');
    if (!tbody) return;

    if (!list || list.length === 0) {
      const emptyMsg = (!this.branchList || this.branchList.length === 0)
        ? 'No store branches yet.'
        : 'No branches match your search.';
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 36px;">${emptyMsg}</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(b => {
      const isActive = (b.status || 'ACTIVE').toUpperCase() === 'ACTIVE';
      const statusBadge = isActive
        ? `<span class="status-badge-active">● Active</span>`
        : `<span class="status-badge-inactive">○ Inactive</span>`;

      const mainBadge = b.is_main
        ? `<span class="main-branch-chip">★ Main Branch</span>`
        : '';

      const toggleActionLabel = isActive ? 'Deactivate' : 'Activate';
      const toggleActionColor = isActive ? 'color: var(--status-danger, #EF4444);' : 'color: var(--status-safe, #10B981);';

      let actions = '';
      if (this.canEdit) {
        actions = `
          <div style="display: flex; align-items: center; justify-content: flex-end; gap: 6px;">
            <button class="btn-xs" title="Edit Branch" onclick="BranchesApp.openEditModal(${b.id})">
              ✏️ Edit
            </button>
            <button class="btn-xs" style="${toggleActionColor}" title="${toggleActionLabel} Branch" onclick="BranchesApp.handleToggleStatus(${b.id}, '${escapeHtml(b.branch_name)}')">
              ${toggleActionLabel}
            </button>
            ${b.is_main ? '' : `
              <button class="btn-xs" style="color: var(--status-danger, #EF4444);" title="Delete Branch" onclick="BranchesApp.handleDeleteBranch(${b.id}, '${escapeHtml(b.branch_name)}')">
                🗑️
              </button>
            `}
          </div>
        `;
      } else {
        actions = `<span style="font-size: 12px; color: var(--color-text-muted);">View Only</span>`;
      }

      return `
        <tr>
          <td>
            <div style="font-weight: 600; color: var(--color-text-primary); display: flex; align-items: center; gap: 8px;">
              <span>${escapeHtml(b.branch_name)}</span>
              ${mainBadge}
            </div>
            <div style="font-size: 11.5px; color: var(--color-text-muted);">Branch ID: #${b.id}</div>
          </td>
          <td>
            <span class="branch-code-badge">${escapeHtml(b.code || '—')}</span>
          </td>
          <td style="font-size: 13px;">${escapeHtml(b.city || '—')}</td>
          <td style="font-size: 13px;">${escapeHtml(b.phone || '—')}</td>
          <td style="font-size: 12px; color: var(--color-text-secondary); max-width: 200px;">
            ${escapeHtml(b.address || '—')}
          </td>
          <td>${statusBadge}</td>
          <td style="text-align: right;">${actions}</td>
        </tr>
      `;
    }).join('');
  },

  openAddModal() {
    const modal = document.getElementById('modal-branch-form');
    document.getElementById('modal-branch-title').textContent = '+ Add Store Branch';
    document.getElementById('branch-form-id').value = '';
    document.getElementById('branch-form-name').value = '';
    
    // Auto-suggest next branch code
    const nextNum = (this.branchList.length + 1).toString().padStart(2, '0');
    document.getElementById('branch-form-code').value = `BR-${nextNum}`;
    document.getElementById('branch-form-city').value = '';
    document.getElementById('branch-form-phone').value = '';
    document.getElementById('branch-form-address').value = '';
    document.getElementById('branch-form-main').checked = this.branchList.length === 0;

    if (modal) modal.classList.add('active');
  },

  openEditModal(branchId) {
    const branch = this.branchList.find(b => b.id === branchId);
    if (!branch) return;

    const modal = document.getElementById('modal-branch-form');
    document.getElementById('modal-branch-title').textContent = `Edit Branch: ${branch.branch_name}`;
    document.getElementById('branch-form-id').value = branch.id;
    document.getElementById('branch-form-name').value = branch.branch_name || '';
    document.getElementById('branch-form-code').value = branch.code || '';
    document.getElementById('branch-form-city').value = branch.city || '';
    document.getElementById('branch-form-phone').value = branch.phone || '';
    document.getElementById('branch-form-address').value = branch.address || '';
    document.getElementById('branch-form-main').checked = Boolean(branch.is_main);

    if (modal) modal.classList.add('active');
  },

  closeFormModal() {
    const modal = document.getElementById('modal-branch-form');
    if (modal) modal.classList.remove('active');
  },

  async handleSaveBranch(e) {
    e.preventDefault();
    const branchId = document.getElementById('branch-form-id').value;
    const submitBtn = document.getElementById('branch-form-submit-btn');
    const origText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    const branchName = document.getElementById('branch-form-name').value.trim();
    const code = document.getElementById('branch-form-code').value.trim() || null;
    const city = document.getElementById('branch-form-city').value.trim() || null;
    const phone = document.getElementById('branch-form-phone').value.trim() || null;
    const address = document.getElementById('branch-form-address').value.trim() || null;
    const isMain = document.getElementById('branch-form-main').checked;

    if (!branchName) {
      alert('Branch Name is required.');
      submitBtn.disabled = false;
      submitBtn.textContent = origText;
      return;
    }

    try {
      if (!branchId) {
        const payload = {
          branch_name: branchName,
          code,
          city,
          phone,
          address,
          is_main: isMain,
          status: 'ACTIVE'
        };
        await api.createStoreBranch(payload);
        alert(`Branch '${branchName}' created successfully!`);
      } else {
        const payload = {
          branch_name: branchName,
          code,
          city,
          phone,
          address,
          is_main: isMain
        };
        await api.updateStoreBranch(branchId, payload);
        alert(`Branch '${branchName}' updated successfully!`);
      }

      this.closeFormModal();
      await this.loadBranches();
    } catch (err) {
      console.error('Save branch error:', err);
      alert('Failed to save store branch: ' + (err.message || 'Unknown error'));
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = origText;
    }
  },

  async handleToggleStatus(branchId, branchName) {
    const confirmed = confirm(`Are you sure you want to toggle the active status of branch '${branchName}'?`);
    if (!confirmed) return;

    try {
      const res = await api.toggleBranchStatus(branchId);
      alert(res.message || 'Branch status updated successfully.');
      await this.loadBranches();
    } catch (err) {
      alert('Failed to update branch status: ' + (err.message || 'Unknown error'));
    }
  },

  async handleDeleteBranch(branchId, branchName) {
    const confirmed = confirm(`WARNING: Are you sure you want to delete branch '${branchName}'? This action cannot be undone.`);
    if (!confirmed) return;

    try {
      await api.deleteStoreBranch(branchId);
      alert(`Branch '${branchName}' removed successfully.`);
      await this.loadBranches();
    } catch (err) {
      alert('Failed to delete store branch: ' + (err.message || 'Unknown error'));
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('branches-page')) {
    BranchesApp.init();
  }
});
