// nav.js - ExpiryGuard Canonical Navigation & Sidebar Engine (Single Source of Truth)

window.CANONICAL_NAV_ITEMS = [
  {
    id: 'dashboard',
    href: 'index.html',
    label: 'Dashboard',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>'
  },
  {
    id: 'billing',
    href: 'billing.html',
    label: 'Create New Bill',
    permission: 'BILL_CREATE',
    iconSvg: '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="16" rx="2"></rect><line x1="6" y1="8" x2="18" y2="8"></line><line x1="6" y1="12" x2="18" y2="12"></line><line x1="6" y1="16" x2="12" y2="16"></line></svg>'
  },
  {
    id: 'sales',
    href: 'sales.html',
    label: 'Billing / Live Sales',
    permission: 'BILL_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>'
  },
  {
    id: 'smart-restock',
    href: 'smart_restock.html',
    label: 'Smart Restock',
    permission: 'INVENTORY_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"></path></svg>'
  },
  {
    id: 'inventory',
    href: 'inventory.html',
    label: 'Live Inventory',
    permission: 'INVENTORY_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 1-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>'
  },
  {
    id: 'add-inventory',
    href: 'javascript:void(0)',
    onclick: 'openAddInventoryModal()',
    label: '+ Add Inventory',
    permission: 'INVENTORY_CREATE',
    iconSvg: '<svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
  },
  {
    id: 'documents',
    href: 'documents.html',
    label: 'Documents & OCR',
    permission: 'PURCHASE_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>'
  },
  {
    id: 'suppliers',
    href: 'suppliers.html',
    label: 'Suppliers',
    permission: 'SUPPLIER_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>'
  },
  {
    id: 'returns',
    href: 'returns.html',
    label: "Returns & Refunds",
    permission: 'PURCHASE_RETURN',
    iconSvg: '<svg viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>'
  },
  {
    id: 'khata',
    href: 'khata.html',
    label: 'Customer Khata',
    permission: 'KHATA_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>'
  },
  {
    id: 'staff',
    href: 'staff.html',
    label: 'Staff & Users',
    permission: 'STAFF_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>'
  },
  {
    id: 'branches',
    href: 'branches.html',
    label: 'Store Branches',
    permission: 'SETTINGS_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>'
  },
  {
    id: 'gst-filing',
    href: 'gst_filing.html',
    label: 'GST Filing',
    permission: 'REPORT_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>'
  },
  {
    id: 'ca-connect',
    href: 'ca_connect.html',
    label: 'CA Connect',
    permission: 'REPORT_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><polyline points="16 11 18 13 22 9"></polyline></svg>'
  },
  {
    id: 'reports',
    href: 'reports.html',
    label: 'Reports & Analytics',
    permission: 'REPORT_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>'
  },
  {
    id: 'settings',
    href: 'settings.html',
    label: 'Settings',
    permission: 'SETTINGS_VIEW',
    iconSvg: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1 2.83 0l.06-.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
  }
];

window.ExpiryNav = {
  getActiveId() {
    const p = window.location.pathname.toLowerCase();
    const s = window.location.search.toLowerCase();
    if (p.includes('billing')) return 'billing';
    if (p.includes('sales')) return 'sales';
    if (p.includes('smart_restock') || p.includes('smart-restock')) return 'smart-restock';
    if (p.includes('inventory') && !p.includes('add-inventory')) return 'inventory';
    if (p.includes('documents')) return 'documents';
    if (p.includes('suppliers')) return 'suppliers';
    if (p.includes('returns')) return 'returns';
    if (p.includes('staff')) return 'staff';
    if (p.includes('branch')) return 'branches';
    if (p.includes('gst_filing') || p.includes('gst-filing')) return 'gst-filing';
    if (p.includes('ca_connect') || p.includes('ca-connect')) return 'ca-connect';
    if (p.includes('khata')) return 'khata';
    if (p.includes('reports')) return 'reports';
    if (p.includes('settings')) return 'settings';
    return 'dashboard';
  },

  isDrawerOpen: false,

  toggleDrawer(forceState) {
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.querySelector('.sidebar-backdrop');
    const btn = document.querySelector('.hamburger-btn');
    
    this.isDrawerOpen = typeof forceState === 'boolean' ? forceState : !this.isDrawerOpen;

    if (sidebar) {
      sidebar.classList.toggle('drawer-open', this.isDrawerOpen);
    }
    if (backdrop) {
      backdrop.classList.toggle('active', this.isDrawerOpen);
    }
    if (btn) {
      btn.setAttribute('aria-expanded', this.isDrawerOpen ? 'true' : 'false');
      btn.setAttribute('aria-label', this.isDrawerOpen ? 'Close main menu' : 'Open main menu');
      btn.innerHTML = this.isDrawerOpen
        ? `<svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`
        : `<svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="1.5" fill="currentColor"></circle><circle cx="12" cy="12" r="1.5" fill="currentColor"></circle><circle cx="12" cy="19" r="1.5" fill="currentColor"></circle></svg>`;
    }
  },

  openDrawer() {
    this.toggleDrawer(true);
  },

  closeDrawer() {
    this.toggleDrawer(false);
  },

  updateShopName(shopName, roleName) {
    if (!shopName) return;
    const elements = document.querySelectorAll('#shop-name-header, #topbar-shop-name, .topbar-shop-name');
    elements.forEach(el => {
      el.textContent = shopName;
    });
    const avatar = document.querySelector('.user-avatar');
    if (avatar && shopName) {
      avatar.textContent = shopName[0].toUpperCase();
    }
    const roleEl = document.querySelector('.user-role');
    if (roleEl && roleName) {
      roleEl.textContent = roleName;
    }
  },

  injectHamburgerAndBackdrop() {
    // 1. Ensure Backdrop exists
    let backdrop = document.querySelector('.sidebar-backdrop');
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.className = 'sidebar-backdrop';
      backdrop.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.closeDrawer();
      });
      document.body.appendChild(backdrop);
    }

    // 2. Inject Single Menu Button & Shop Name Brand into Topbar Header if not already present
    const topbar = document.querySelector('.topbar');
    if (topbar && !topbar.querySelector('.topbar-brand-container')) {
      const brandContainer = document.createElement('div');
      brandContainer.className = 'topbar-brand-container';
      brandContainer.style.cssText = 'align-items: center; gap: 10px; min-width: 0; position: relative; z-index: 1001;';

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hamburger-btn';
      btn.setAttribute('aria-label', 'Open main menu');
      btn.setAttribute('aria-expanded', 'false');
      btn.setAttribute('aria-controls', 'main-sidebar-drawer');
      btn.style.cssText = 'cursor: pointer; position: relative; z-index: 1002; pointer-events: auto;';
      btn.innerHTML = `
        <svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="5" r="1.5" fill="currentColor"></circle>
          <circle cx="12" cy="12" r="1.5" fill="currentColor"></circle>
          <circle cx="12" cy="19" r="1.5" fill="currentColor"></circle>
        </svg>
      `;
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.toggleDrawer();
      });

      brandContainer.appendChild(btn);

      // Insert as the very first element inside topbar header
      topbar.insertBefore(brandContainer, topbar.firstChild);
    }
  },

  render() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    sidebar.id = 'main-sidebar-drawer';
    const activeId = this.getActiveId();

    sidebar.innerHTML = `
      <div class="sidebar-header">
        <a href="index.html" class="brand-logo">
          <div class="shield-icon">🛡️</div>
          <div class="brand-title">Dawai<span>Flow</span></div>
        </a>
        <button type="button" class="drawer-close-btn" onclick="event.preventDefault(); event.stopPropagation(); window.ExpiryNav.closeDrawer();" aria-label="Close main menu" style="margin-left: auto; background: none; border: none; color: var(--color-text-muted); cursor: pointer; padding: 8px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); position: relative; z-index: 1002; pointer-events: auto;">
          <svg viewBox="0 0 24 24" width="22" height="22" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <nav class="sidebar-menu">
        <div class="menu-category">Main Menu</div>
        ${(() => {
          let userPerms = [];
          let userRole = 'OWNER';
          let isOwner = true;
          try {
            const cached = localStorage.getItem('expiryguard_cached_user_profile');
            if (cached) {
              const u = JSON.parse(cached);
              userRole = (u.role || 'OWNER').toUpperCase();
              userPerms = u.permissions || [];
              isOwner = u.is_owner === true || userRole === 'OWNER' || userRole === 'ADMIN' || !u.role;
            }
          } catch (e) {}

          return window.CANONICAL_NAV_ITEMS.filter(item => {
            if (isOwner || !item.permission) return true;
            return userPerms.includes(item.permission) || userPerms.includes('*');
          }).map(item => {
            const isActive = item.id === activeId;
            const clickAttr = item.onclick 
              ? ` onclick="${item.onclick}; window.ExpiryNav.closeDrawer();"` 
              : ` onclick="window.ExpiryNav.closeDrawer();"`;
            return `
              <a href="${item.href}" class="nav-item ${isActive ? 'active' : ''}" data-nav-id="${item.id}"${clickAttr}>
                ${item.iconSvg}
                <span class="nav-text">${item.label}</span>
              </a>
            `;
          }).join('');
        })()}
      </nav>

      <div class="sidebar-footer">
        <div class="user-profile-badge" style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
          <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
            <div class="user-avatar">P</div>
            <div class="user-info">
              <span class="user-name" id="shop-name-header">Pharmacy</span>
              <span class="user-role">Owner / Pharmacist</span>
            </div>
          </div>
          <button type="button" onclick="api.logout()" title="Logout" style="background: rgba(220, 38, 38, 0.1); border: 1px solid rgba(220, 38, 38, 0.3); color: #EF4444; cursor: pointer; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; transition: all 0.2s ease;">
            Logout
          </button>
        </div>
      </div>
    `;

    this.injectHamburgerAndBackdrop();

    setTimeout(() => {
      try {
        const cached = localStorage.getItem('expiryguard_cached_user_profile');
        if (cached) {
          const u = JSON.parse(cached);
          if (u && u.shop_name) {
            const roleLabel = u.is_owner ? 'Owner' : `${u.name || 'Staff'} (${u.role || 'Staff'})`;
            this.updateShopName(u.shop_name, roleLabel);
          }
        }
        
        if (window.api && typeof api.getUserProfile === 'function' && api.getToken()) {
          api.getUserProfile().then(u => {
            if (u && u.shop_name) {
              localStorage.setItem('expiryguard_cached_user_profile', JSON.stringify(u));
              const roleLabel = u.is_owner ? 'Owner' : `${u.name || 'Staff'} (${u.role || 'Staff'})`;
              this.updateShopName(u.shop_name, roleLabel);
            }
          }).catch(() => {});
        }
      } catch (e) {}
    }, 0);
  }
};

// Global Event Delegation (Capture Phase) for Menu Toggle and Close Buttons
document.addEventListener('click', (e) => {
  const closeBtn = e.target.closest('.drawer-close-btn');
  const menuBtn = e.target.closest('.hamburger-btn');
  if (closeBtn) {
    e.preventDefault();
    e.stopPropagation();
    if (window.ExpiryNav) window.ExpiryNav.closeDrawer();
  } else if (menuBtn) {
    e.preventDefault();
    e.stopPropagation();
    if (window.ExpiryNav) window.ExpiryNav.toggleDrawer();
  }
}, true);

// Global Keyboard Accessibility: Close drawer on Escape press
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && window.ExpiryNav && window.ExpiryNav.isDrawerOpen) {
    window.ExpiryNav.closeDrawer();
  }
});

// Auto-render
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => window.ExpiryNav.render());
} else {
  window.ExpiryNav.render();
}
