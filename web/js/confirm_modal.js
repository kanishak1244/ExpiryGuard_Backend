/**
 * ExpiryGuard — ConfirmModal Component
 * 
 * Props / Options:
 * - isOpen: boolean (Controls modal visibility)
 * - title: string (Modal heading text)
 * - message: string (Confirmation message/body)
 * - onConfirm: function (Callback executed on confirm)
 * - onCancel: function (Callback executed on cancel/dismiss)
 * - confirmText: string (Optional, default: 'Confirm')
 * - cancelText: string (Optional, default: 'Cancel')
 * - icon: string (Optional icon/emoji, default: '🛡️')
 */

class ConfirmModalComponent {
  constructor() {
    this.state = {
      isOpen: false,
      title: 'Confirm Action',
      message: 'Are you sure you want to proceed?',
      onConfirm: null,
      onCancel: null,
      confirmText: 'Confirm',
      cancelText: 'Cancel',
      icon: '🛡️'
    };
    this.overlayEl = null;
    this.resolvePromise = null;
    this._handleKeyDown = this._handleKeyDown.bind(this);
  }

  init() {
    if (this.overlayEl || typeof document === 'undefined') return;

    this.overlayEl = document.createElement('div');
    this.overlayEl.id = 'confirm-modal-overlay';
    this.overlayEl.className = 'confirm-modal-overlay';
    this.overlayEl.setAttribute('role', 'dialog');
    this.overlayEl.setAttribute('aria-modal', 'true');
    this.overlayEl.style.display = 'none';

    this.overlayEl.innerHTML = `
      <div class="confirm-modal-backdrop"></div>
      <div class="confirm-modal-card">
        <div class="confirm-modal-header">
          <div class="confirm-modal-title-wrap">
            <span class="confirm-modal-icon" id="confirm-modal-icon">🛡️</span>
            <h3 id="confirm-modal-title" class="confirm-modal-title">Confirm Action</h3>
          </div>
          <button id="confirm-modal-close" class="confirm-modal-close" aria-label="Close modal">✕</button>
        </div>
        <div class="confirm-modal-body">
          <p id="confirm-modal-message" class="confirm-modal-message">Are you sure you want to proceed?</p>
        </div>
        <div class="confirm-modal-actions">
          <button id="confirm-modal-cancel" type="button" class="btn-confirm-cancel">Cancel</button>
          <button id="confirm-modal-confirm" type="button" class="btn-confirm-accept">Confirm</button>
        </div>
      </div>
    `;

    document.body.appendChild(this.overlayEl);

    // Event listeners
    const backdrop = this.overlayEl.querySelector('.confirm-modal-backdrop');
    const closeBtn = this.overlayEl.querySelector('#confirm-modal-close');
    const cancelBtn = this.overlayEl.querySelector('#confirm-modal-cancel');
    const confirmBtn = this.overlayEl.querySelector('#confirm-modal-confirm');

    if (backdrop) backdrop.addEventListener('click', () => this.handleCancel());
    if (closeBtn) closeBtn.addEventListener('click', () => this.handleCancel());
    if (cancelBtn) cancelBtn.addEventListener('click', () => this.handleCancel());
    if (confirmBtn) confirmBtn.addEventListener('click', () => this.handleConfirm());
  }

  render(props = {}) {
    this.init();
    this.state = {
      ...this.state,
      ...props
    };

    if (!this.overlayEl) return;

    const titleEl = this.overlayEl.querySelector('#confirm-modal-title');
    const msgEl = this.overlayEl.querySelector('#confirm-modal-message');
    const confirmBtn = this.overlayEl.querySelector('#confirm-modal-confirm');
    const cancelBtn = this.overlayEl.querySelector('#confirm-modal-cancel');
    const iconEl = this.overlayEl.querySelector('#confirm-modal-icon');

    if (titleEl) titleEl.textContent = this.state.title || 'Confirm Action';
    if (msgEl) msgEl.textContent = this.state.message || 'Are you sure you want to proceed?';
    if (confirmBtn) confirmBtn.textContent = this.state.confirmText || 'Confirm';
    if (cancelBtn) cancelBtn.textContent = this.state.cancelText || 'Cancel';
    if (iconEl) iconEl.textContent = this.state.icon || '🛡️';

    if (this.state.isOpen) {
      this.overlayEl.style.display = 'flex';
      // Force DOM reflow to trigger animation
      void this.overlayEl.offsetWidth;
      this.overlayEl.classList.add('is-open', 'active');
      window.addEventListener('keydown', this._handleKeyDown);
      setTimeout(() => {
        if (confirmBtn) confirmBtn.focus();
      }, 50);
    } else {
      this.overlayEl.classList.remove('is-open', 'active');
      window.removeEventListener('keydown', this._handleKeyDown);
      setTimeout(() => {
        if (!this.state.isOpen && this.overlayEl) {
          this.overlayEl.style.display = 'none';
        }
      }, 200);
    }
  }

  open(props = {}) {
    return new Promise((resolve) => {
      this.resolvePromise = resolve;
      this.render({
        isOpen: true,
        title: props.title || 'Confirm Action',
        message: props.message || 'Are you sure you want to proceed?',
        confirmText: props.confirmText || 'Confirm',
        cancelText: props.cancelText || 'Cancel',
        icon: props.icon || '🛡️',
        onConfirm: props.onConfirm || null,
        onCancel: props.onCancel || null,
      });
    });
  }

  close() {
    this.render({ isOpen: false });
  }

  handleConfirm() {
    const cb = this.state.onConfirm;
    const resolver = this.resolvePromise;
    this.close();
    if (typeof cb === 'function') {
      try {
        cb();
      } catch (err) {
        console.error('Error in onConfirm callback:', err);
      }
    }
    if (typeof resolver === 'function') {
      resolver(true);
      this.resolvePromise = null;
    }
  }

  handleCancel() {
    const cb = this.state.onCancel;
    const resolver = this.resolvePromise;
    this.close();
    if (typeof cb === 'function') {
      try {
        cb();
      } catch (err) {
        console.error('Error in onCancel callback:', err);
      }
    }
    if (typeof resolver === 'function') {
      resolver(false);
      this.resolvePromise = null;
    }
  }

  _handleKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      this.handleCancel();
    }
  }
}

// Global Singleton Instance & Functional Component Interface
const confirmModalInstance = new ConfirmModalComponent();

function ConfirmModal(props = {}) {
  if (props.isOpen !== undefined) {
    confirmModalInstance.render(props);
  } else {
    return confirmModalInstance.open(props);
  }
}

// Static helper methods matching React / JS conventions
ConfirmModal.open = (props) => confirmModalInstance.open(props);
ConfirmModal.show = (props) => confirmModalInstance.open(props);
ConfirmModal.close = () => confirmModalInstance.close();
ConfirmModal.confirm = (props) => confirmModalInstance.open(props);

// Auto-initialize when DOM is ready
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => confirmModalInstance.init());
  } else {
    confirmModalInstance.init();
  }
}

// Export to window
window.ConfirmModal = ConfirmModal;
window.confirmModal = ConfirmModal;
window.showConfirmModal = (props) => confirmModalInstance.open(props);
