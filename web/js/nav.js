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
    iconSvg: '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="16" rx="2"></rect><line x1="6" y1="8" x2="18" y2="8"></line><line x1="6" y1="12" x2="18" y2="12"></line><line x1="6" y1="16" x2="12" y2="16"></line></svg>'
  },
  {
    id: 'sales',
    href: 'sales.html',
    label: 'Billing / Live Sales',
    iconSvg: '<svg viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>'
  },
  {
    id: 'ai-billing',
    href: 'ai_billing.html',
    label: 'AI Camera Billing',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>'
  },
  {
    id: 'inventory',
    href: 'inventory.html',
    label: 'Live Inventory',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>'
  },
  {
    id: 'restock',
    href: 'restock.html',
    label: 'Restock Suggestions',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path><line x1="3" y1="6" x2="21" y2="6"></line><path d="M16 10a4 4 0 0 1-8 0"></path></svg>'
  },
  {
    id: 'add-inventory',
    href: 'javascript:void(0)',
    onclick: 'openAddInventoryModal()',
    label: '+ Add Inventory',
    iconSvg: '<svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
  },
  {
    id: 'documents',
    href: 'documents.html',
    label: 'Documents & OCR',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>'
  },
  {
    id: 'suppliers',
    href: 'suppliers.html',
    label: 'Suppliers',
    iconSvg: '<svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>'
  },
  {
    id: 'returns',
    href: 'returns.html',
    label: "Today's Returns",
    iconSvg: '<svg viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>'
  },
  {
    id: 'reports',
    href: 'reports.html',
    label: 'Reports & Analytics',
    iconSvg: '<svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>'
  },
  {
    id: 'settings',
    href: 'settings.html',
    label: 'Settings',
    iconSvg: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1 2.83 0l.06-.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
  }
];

window.ExpiryNav = {
  getActiveId() {
    const p = window.location.pathname.toLowerCase();
    if (p.includes('billing') && !p.includes('ai_billing') && !p.includes('ai-billing')) return 'billing';
    if (p.includes('sales')) return 'sales';
    if (p.includes('ai_billing') || p.includes('ai-billing')) return 'ai-billing';
    if (p.includes('restock')) return 'restock';
    if (p.includes('inventory') && !p.includes('add-inventory')) return 'inventory';
    if (p.includes('documents')) return 'documents';
    if (p.includes('suppliers')) return 'suppliers';
    if (p.includes('returns')) return 'returns';
    if (p.includes('reports')) return 'reports';
    if (p.includes('settings')) return 'settings';
    return 'dashboard';
  },

  render() {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    const activeId = this.getActiveId();

    sidebar.innerHTML = `
      <div class="sidebar-header">
        <a href="index.html" class="brand-logo">
          <div class="shield-icon">🛡️</div>
          <div class="brand-title">Expiry<span>Guard</span></div>
        </a>
      </div>

      <nav class="sidebar-menu">
        <div class="menu-category">Main Menu</div>
        ${window.CANONICAL_NAV_ITEMS.map(item => {
          const isActive = item.id === activeId;
          const clickAttr = item.onclick ? ` onclick="${item.onclick}"` : '';
          return `
            <a href="${item.href}" class="nav-item ${isActive ? 'active' : ''}" data-nav-id="${item.id}"${clickAttr}>
              ${item.iconSvg}
              <span class="nav-text">${item.label}</span>
            </a>
          `;
        }).join('')}
      </nav>

      <div class="sidebar-footer">
        <div class="user-profile-badge">
          <div class="user-avatar">P</div>
          <div class="user-info">
            <span class="user-name" id="shop-name-header">AI Pharmacy</span>
            <span class="user-role">Owner / Pharmacist</span>
          </div>
        </div>
      </div>
    `;
  }
};

// Auto-render
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => window.ExpiryNav.render());
} else {
  window.ExpiryNav.render();
}
