/* ==========================================================================
   EXPIRYGUARD WEB APP — STAFF & USERS (RBAC) CONTROLLER
   ========================================================================== */

window.StaffApp = {
  staffList: [],
  userProfile: null,
  isOwner: false,
  canManageStaff: false,
  currentRevealedPassword: '',
  isPasswordRevealed: false,

  async init() {
    // 1. Immediately read cached profile to configure permissions without network blocking
    const cached = localStorage.getItem('expiryguard_cached_user_profile');
    if (cached) {
      try {
        const u = JSON.parse(cached);
        this.userProfile = u;
        const role = (u.role || 'OWNER').toUpperCase();
        const perms = u.permissions || [];
        this.isOwner = u.is_owner === true || role === 'OWNER' || role === 'ADMIN';
        this.canManageStaff = this.isOwner || perms.includes('STAFF_MANAGE') || perms.includes('*');
      } catch (e) {}
    } else {
      this.isOwner = true;
      this.canManageStaff = true;
    }

    // Hide "+ Add Staff Member" button if not authorized
    const addBtn = document.getElementById('btn-open-add-staff');
    if (addBtn && !this.canManageStaff) {
      addBtn.style.display = 'none';
    }

    // 2. Synchronously refresh profile in background without blocking
    if (window.api) {
      api.getUserProfile().then(p => {
        if (p) {
          this.userProfile = p;
          localStorage.setItem('expiryguard_cached_user_profile', JSON.stringify(p));
        }
      }).catch(() => {});
    }

    // 3. Load staff directory
    await this.loadStaff();
  },

  async loadStaff() {
    const tbody = document.getElementById('staff-table-body');
    
    // Check 0ms cached staff list first before network from AppDataPreloader or cache
    const preloaderStaff = window.AppDataPreloader ? window.AppDataPreloader.get('/staff') : null;
    const apiCached = window.api && typeof window.api.getCached === 'function' ? window.api.getCached('/staff') : null;
    const cachedStaff = preloaderStaff || (apiCached && apiCached.data !== undefined ? apiCached.data : apiCached);
    if (Array.isArray(cachedStaff) && cachedStaff.length > 0) {
      this.staffList = cachedStaff;
      this.renderStats();
      this.filterStaff();
    } else if (tbody && !tbody.children.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 36px;">Loading staff directory...</td></tr>`;
    }

    try {
      const data = await api.getStaffMembers();
      this.staffList = Array.isArray(data) ? data : [];
      this.renderStats();
      this.filterStaff();
    } catch (err) {
      console.error('Failed to load staff list:', err);
      if (tbody && (!this.staffList || this.staffList.length === 0)) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--status-danger, #EF4444); padding: 36px;">Failed to load staff: ${escapeHtml(err.message || 'Unknown error')}</td></tr>`;
      }
    }
  },

  renderStats() {
    const total = this.staffList.length;
    const active = this.staffList.filter(s => (s.status || '').toUpperCase() === 'ACTIVE').length;
    const pharmacists = this.staffList.filter(s => (s.role || '').toUpperCase() === 'PHARMACIST').length;
    const otherStaff = this.staffList.filter(s => (s.role || '').toUpperCase() !== 'PHARMACIST').length;

    const elTotal = document.getElementById('stat-total-staff');
    const elActive = document.getElementById('stat-active-staff');
    const elPharmacists = document.getElementById('stat-pharmacists-count');
    const elOther = document.getElementById('stat-other-staff');

    if (elTotal) elTotal.textContent = total;
    if (elActive) elActive.textContent = active;
    if (elPharmacists) elPharmacists.textContent = pharmacists;
    if (elOther) elOther.textContent = otherStaff;
  },

  filterStaff() {
    const searchVal = (document.getElementById('staff-search-input')?.value || '').toLowerCase().trim();
    const roleVal = (document.getElementById('staff-role-filter')?.value || '').toUpperCase();
    const statusVal = (document.getElementById('staff-status-filter')?.value || '').toUpperCase();

    const filtered = this.staffList.filter(s => {
      if (roleVal && (s.role || '').toUpperCase() !== roleVal) return false;
      if (statusVal && (s.status || '').toUpperCase() !== statusVal) return false;

      if (searchVal) {
        const name = (s.name || '').toLowerCase();
        const username = (s.username || '').toLowerCase();
        const phone = (s.phone || '').toLowerCase();
        const email = (s.email || '').toLowerCase();
        if (!name.includes(searchVal) && !username.includes(searchVal) && !phone.includes(searchVal) && !email.includes(searchVal)) {
          return false;
        }
      }
      return true;
    });

    this.renderStaffTable(filtered);
  },

  getRoleBadge(role) {
    const r = (role || '').toUpperCase();
    switch (r) {
      case 'OWNER':
        return `<span class="role-badge role-owner">👑 Owner</span>`;
      case 'PHARMACIST':
        return `<span class="role-badge role-pharmacist">💊 Pharmacist</span>`;
      case 'BILLING_STAFF':
        return `<span class="role-badge role-billing">🧾 Billing</span>`;
      case 'INVENTORY_STAFF':
        return `<span class="role-badge role-inventory">📦 Inventory</span>`;
      case 'ACCOUNTANT':
        return `<span class="role-badge role-accountant">📊 Accountant</span>`;
      default:
        return `<span class="role-badge">${escapeHtml(role)}</span>`;
    }
  },

  formatDateTime(isoString) {
    if (!isoString) return '<span style="color: var(--color-text-muted);">Never</span>';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return '<span style="color: var(--color-text-muted);">Never</span>';
      return d.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return '<span style="color: var(--color-text-muted);">Never</span>';
    }
  },

  renderStaffTable(list) {
    const tbody = document.getElementById('staff-table-body');
    if (!tbody) return;

    if (!list || list.length === 0) {
      const emptyMsg = (!this.staffList || this.staffList.length === 0)
        ? 'No staff members registered yet. Click "+ Add Staff Member" to add team accounts.'
        : 'No staff members match your search or filter criteria.';
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 36px;">${emptyMsg}</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(s => {
      const isActive = (s.status || 'ACTIVE').toUpperCase() === 'ACTIVE';
      const statusBadge = isActive
        ? `<span class="status-badge-active">● Active</span>`
        : `<span class="status-badge-inactive">○ Inactive</span>`;

      const toggleActionLabel = isActive ? 'Deactivate' : 'Activate';
      const toggleActionColor = isActive ? 'color: var(--status-danger, #EF4444);' : 'color: var(--status-safe, #10B981);';

      // Action buttons
      let actions = '';
      if (this.isOwner) {
        actions += `
          <button class="btn-xs" title="View Plaintext Credentials" onclick="StaffApp.openRevealModal(${s.id}, '${escapeHtml(s.name)}')">
            🔑 Password
          </button>
        `;
      }

      if (this.canManageStaff) {
        actions += `
          <button class="btn-xs" title="Reset Staff Password" onclick="StaffApp.openResetModal(${s.id}, '${escapeHtml(s.name)}')">
            🔄 Reset
          </button>
          <button class="btn-xs" title="Edit Staff Details" onclick="StaffApp.openEditModal(${s.id})">
            ✏️ Edit
          </button>
          <button class="btn-xs" style="${toggleActionColor}" title="${toggleActionLabel} Account" onclick="StaffApp.handleToggleStatus(${s.id}, '${escapeHtml(s.name)}')">
            ${toggleActionLabel}
          </button>
          <button class="btn-xs" style="color: var(--status-danger, #EF4444);" title="Delete Staff Account" onclick="StaffApp.handleDeleteStaff(${s.id}, '${escapeHtml(s.name)}')">
            🗑️
          </button>
        `;
      }

      const contactInfo = [
        s.phone ? `📞 ${escapeHtml(s.phone)}` : '',
        s.email ? `✉️ ${escapeHtml(s.email)}` : ''
      ].filter(Boolean).join('<br>') || '<span style="color: var(--color-text-muted);">—</span>';

      return `
        <tr>
          <td>
            <div style="font-weight: 600; color: var(--color-text-primary);">${escapeHtml(s.name)}</div>
            <div style="font-size: 11.5px; color: var(--color-text-muted);">ID: #${s.id}</div>
          </td>
          <td>
            <code style="font-family: 'JetBrains Mono', monospace; font-size: 12.5px; background: var(--color-surface-bg); padding: 2px 6px; border-radius: 4px; border: 1px solid var(--color-border);">${escapeHtml(s.username || '—')}</code>
          </td>
          <td>${this.getRoleBadge(s.role)}</td>
          <td style="font-size: 12.5px;">${contactInfo}</td>
          <td>${statusBadge}</td>
          <td style="font-size: 12px;" class="num-tabular">${this.formatDateTime(s.last_login)}</td>
          <td style="text-align: right;">
            <div class="action-btn-group" style="justify-content: flex-end;">
              ${actions || '<span style="font-size: 12px; color: var(--color-text-muted);">View Only</span>'}
            </div>
          </td>
        </tr>
      `;
    }).join('');
  },

  openAddModal() {
    const modal = document.getElementById('modal-staff-form');
    document.getElementById('modal-staff-title').textContent = '+ Add New Staff Member';
    document.getElementById('staff-form-id').value = '';
    document.getElementById('staff-form-name').value = '';
    document.getElementById('staff-form-username').value = '';
    document.getElementById('staff-form-password').value = '';
    document.getElementById('staff-form-role').value = 'BILLING_STAFF';
    document.getElementById('staff-form-phone').value = '';
    document.getElementById('staff-form-email').value = '';

    document.getElementById('group-username').style.display = 'block';
    document.getElementById('group-password').style.display = 'block';
    document.getElementById('staff-form-username').required = true;
    document.getElementById('staff-form-password').required = true;

    if (modal) modal.classList.add('active');
  },

  openEditModal(staffId) {
    const staff = this.staffList.find(s => s.id === staffId);
    if (!staff) return;

    const modal = document.getElementById('modal-staff-form');
    document.getElementById('modal-staff-title').textContent = `Edit Staff: ${staff.name}`;
    document.getElementById('staff-form-id').value = staff.id;
    document.getElementById('staff-form-name').value = staff.name || '';
    document.getElementById('staff-form-role').value = (staff.role || 'BILLING_STAFF').toUpperCase();
    document.getElementById('staff-form-phone').value = staff.phone || '';
    document.getElementById('staff-form-email').value = staff.email || '';

    // In edit mode, username & password are not modified via standard PUT /staff/{id}
    document.getElementById('group-username').style.display = 'none';
    document.getElementById('group-password').style.display = 'none';
    document.getElementById('staff-form-username').required = false;
    document.getElementById('staff-form-password').required = false;

    if (modal) modal.classList.add('active');
  },

  closeFormModal() {
    const modal = document.getElementById('modal-staff-form');
    if (modal) modal.classList.remove('active');
  },

  async handleSaveStaff(e) {
    e.preventDefault();
    const staffId = document.getElementById('staff-form-id').value;
    const submitBtn = document.getElementById('staff-form-submit-btn');
    const origText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    const name = document.getElementById('staff-form-name').value.trim();
    const role = document.getElementById('staff-form-role').value;
    const phone = document.getElementById('staff-form-phone').value.trim() || null;
    const email = document.getElementById('staff-form-email').value.trim() || null;

    try {
      if (!staffId) {
        // Create new staff
        const username = document.getElementById('staff-form-username').value.trim();
        const password = document.getElementById('staff-form-password').value;

        if (!name || !username || !password) {
          alert('Name, username, and password are required.');
          submitBtn.disabled = false;
          submitBtn.textContent = origText;
          return;
        }

        const payload = { name, username, password, role, phone, email };
        await api.createStaffMember(payload);
        alert(`Staff member '${name}' created successfully!`);
      } else {
        // Update existing staff
        const payload = { name, role, phone, email };
        await api.updateStaffMember(staffId, payload);
        alert(`Staff member '${name}' updated successfully!`);
      }

      this.closeFormModal();
      await this.loadStaff();
    } catch (err) {
      console.error('Save staff error:', err);
      alert('Failed to save staff member: ' + (err.message || 'Unknown error'));
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = origText;
    }
  },

  async openRevealModal(staffId, staffName) {
    document.getElementById('reveal-staff-name').textContent = staffName;
    document.getElementById('reveal-username').textContent = 'Loading...';
    document.getElementById('reveal-password-text').textContent = '••••••••';
    document.getElementById('btn-toggle-reveal-pwd').textContent = 'Show';
    this.currentRevealedPassword = '';
    this.isPasswordRevealed = false;

    const modal = document.getElementById('modal-reveal-password');
    if (modal) modal.classList.add('active');

    try {
      const creds = await api.getStaffCredentials(staffId);
      document.getElementById('reveal-username').textContent = creds.username || '—';
      this.currentRevealedPassword = creds.password || '(No plaintext stored)';
    } catch (err) {
      console.error('Credentials reveal error:', err);
      document.getElementById('reveal-username').textContent = 'Access Denied';
      document.getElementById('reveal-password-text').textContent = err.message || 'Failed to fetch password';
    }
  },

  toggleRevealPlaintext() {
    const textEl = document.getElementById('reveal-password-text');
    const btn = document.getElementById('btn-toggle-reveal-pwd');
    if (!this.isPasswordRevealed) {
      textEl.textContent = this.currentRevealedPassword || '(None)';
      btn.textContent = 'Hide';
      this.isPasswordRevealed = true;
    } else {
      textEl.textContent = '••••••••';
      btn.textContent = 'Show';
      this.isPasswordRevealed = false;
    }
  },

  copyCredentials() {
    const username = document.getElementById('reveal-username').textContent;
    const pwd = this.currentRevealedPassword || '';
    const textToCopy = `Username: ${username}\nPassword: ${pwd}`;

    navigator.clipboard.writeText(textToCopy).then(() => {
      const copyBtnText = document.getElementById('copy-btn-text');
      if (copyBtnText) {
        const orig = copyBtnText.textContent;
        copyBtnText.textContent = '✓ Copied to Clipboard!';
        setTimeout(() => { copyBtnText.textContent = orig; }, 2000);
      }
    }).catch(() => {
      alert(`Username: ${username}\nPassword: ${pwd}`);
    });
  },

  closeRevealModal() {
    const modal = document.getElementById('modal-reveal-password');
    if (modal) modal.classList.remove('active');
    this.currentRevealedPassword = '';
    this.isPasswordRevealed = false;
  },

  openResetModal(staffId, staffName) {
    document.getElementById('reset-staff-id').value = staffId;
    document.getElementById('reset-staff-name').textContent = staffName;
    document.getElementById('reset-new-password').value = '';
    const modal = document.getElementById('modal-reset-password');
    if (modal) modal.classList.add('active');
  },

  closeResetModal() {
    const modal = document.getElementById('modal-reset-password');
    if (modal) modal.classList.remove('active');
  },

  async handleResetPassword(e) {
    e.preventDefault();
    const staffId = document.getElementById('reset-staff-id').value;
    const newPwd = document.getElementById('reset-new-password').value.trim();
    if (!newPwd || newPwd.length < 4) {
      alert('Password must be at least 4 characters.');
      return;
    }

    const btn = document.getElementById('btn-submit-reset');
    const orig = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Resetting...';

    try {
      await api.resetStaffPassword(staffId, newPwd);
      alert('Password reset successfully!');
      this.closeResetModal();
      await this.loadStaff();
    } catch (err) {
      alert('Failed to reset password: ' + (err.message || 'Unknown error'));
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  },

  async handleToggleStatus(staffId, staffName) {
    const confirmed = confirm(`Are you sure you want to toggle account status for '${staffName}'?`);
    if (!confirmed) return;

    try {
      const res = await api.toggleStaffStatus(staffId);
      alert(res.message || 'Status updated successfully.');
      await this.loadStaff();
    } catch (err) {
      alert('Failed to toggle staff status: ' + (err.message || 'Unknown error'));
    }
  },

  async handleDeleteStaff(staffId, staffName) {
    const confirmed = confirm(`WARNING: Are you sure you want to delete staff account '${staffName}'? This action cannot be undone.`);
    if (!confirmed) return;

    try {
      await api.deleteStaffMember(staffId);
      alert(`Staff member '${staffName}' deleted successfully.`);
      await this.loadStaff();
    } catch (err) {
      alert('Failed to delete staff member: ' + (err.message || 'Unknown error'));
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('staff-page')) {
    StaffApp.init();
  }
});
