/**
 * ExpiryGuard - Historical Bills Bulk Import Controller.
 * Rebuilt from scratch: clean 5-state UI, real progress tracking,
 * zero fake loaders, and background job polling.
 */

let selectedMigrationFile = null;
let currentMigrationId = null;
let currentJobCode = null;
let migrationPollTimer = null;
let migrationWs = null;

function initMigrationModule() {
  initDropzone();
  loadMigrationHistory();
  checkActiveMigrationOnLoad();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMigrationModule);
} else {
  initMigrationModule();
}

window.initMigrationModule = initMigrationModule;

function initDropzone() {
  const dropzone = document.getElementById('migration-dropzone');
  const fileInput = document.getElementById('migration-file-input');
  if (!dropzone || !fileInput) return;

  ['dragenter', 'dragover'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.style.borderColor = '#10B981';
      dropzone.style.backgroundColor = 'rgba(16, 185, 129, 0.05)';
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.style.borderColor = '#CBD5E1';
      dropzone.style.backgroundColor = 'transparent';
    });
  });

  dropzone.addEventListener('drop', (e) => {
    const files = e.dataTransfer ? e.dataTransfer.files : null;
    if (files && files.length > 0) {
      onMigrationFileSelected(files);
    }
  });
}

function onMigrationFileSelected(files) {
  if (!files || !files.length) return;
  const file = files[0];
  const validExts = ['.pdf', '.csv', '.xlsx', '.xls'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();

  if (!validExts.includes(ext)) {
    alert(`Unsupported file format '${ext}'. Please select a PDF, CSV, or Excel file.`);
    return;
  }

  if (file.size > 50 * 1024 * 1024) {
    alert('File exceeds maximum size limit of 50 MB.');
    return;
  }

  selectedMigrationFile = file;

  // Show Selected Screen
  document.getElementById('m-selected-name').textContent = file.name;
  const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
  document.getElementById('m-selected-size').textContent = `${sizeMb} MB`;

  switchMigrationView('selected');
}

function switchMigrationView(viewName) {
  const views = ['initial', 'selected', 'processing', 'completed', 'failed'];
  views.forEach(v => {
    const el = document.getElementById(`m-view-${v}`);
    if (el) el.style.display = (v === viewName) ? 'block' : 'none';
  });
}

function resetMigrationToInitial() {
  stopMigrationTracking();
  selectedMigrationFile = null;
  currentMigrationId = null;
  currentJobCode = null;
  const fileInput = document.getElementById('migration-file-input');
  if (fileInput) fileInput.value = '';
  switchMigrationView('initial');
}

async function startMigrationUpload() {
  if (!selectedMigrationFile) return;

  switchMigrationView('processing');
  updateProgressUi({
    message: 'Reading file...',
    processed: 0,
    total: 0,
    percentage: 10
  });

  const formData = new FormData();
  formData.append('file', selectedMigrationFile);

  try {
    const token = localStorage.getItem('token');
    const resp = await fetch('/api/migration/upload', {
      method: 'POST',
      headers: {
        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
      },
      body: formData
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Upload failed');
    }

    const data = await resp.json();
    currentMigrationId = data.migration_id;
    currentJobCode = data.job_id || data.migration_code;

    startMigrationTracking(currentMigrationId);

  } catch (err) {
    showMigrationFailure(err.message, 0, 0);
  }
}

function startMigrationTracking(migrationId) {
  stopMigrationTracking();

  // 1. WebSocket for low latency push
  try {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/migration/${migrationId}`;
    migrationWs = new WebSocket(wsUrl);

    migrationWs.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleMigrationProgressPayload(payload);
      } catch (e) {}
    };

    migrationWs.onerror = () => {
      // Fallback handles it
    };
  } catch (e) {}

  // 2. HTTP Polling every 1.5 seconds as robust fallback
  migrationPollTimer = setInterval(async () => {
    try {
      const token = localStorage.getItem('token');
      const resp = await fetch(`/api/migration/status/${migrationId}`, {
        headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
      });
      if (resp.ok) {
        const data = await resp.json();
        handleMigrationProgressPayload(data);
      }
    } catch (e) {}
  }, 1500);
}

function stopMigrationTracking() {
  if (migrationPollTimer) {
    clearInterval(migrationPollTimer);
    migrationPollTimer = null;
  }
  if (migrationWs) {
    try { migrationWs.close(); } catch (e) {}
    migrationWs = null;
  }
}

function handleMigrationProgressPayload(data) {
  if (!data) return;

  const status = (data.status || '').toLowerCase();

  if (status === 'completed') {
    stopMigrationTracking();
    showMigrationCompleted(data);
    loadMigrationHistory();
    return;
  }

  if (status === 'failed') {
    stopMigrationTracking();
    showMigrationFailure(data.error_message || data.message || 'Import failed', data.processed, data.total);
    return;
  }

  // Active progress update
  updateProgressUi(data);
}

function mapStatusToMessage(status, rawMsg) {
  const st = (status || '').toLowerCase();
  switch (st) {
    case 'uploading':
    case 'reading_file':
      return 'Reading file...';
    case 'extracting':
      return 'Capturing bill information...';
    case 'processing':
      return 'Identifying medicines...';
    case 'validating':
      return 'Checking your bills...';
    case 'deduplicating':
      return 'Checking for duplicate bills...';
    case 'importing':
      return 'Preparing your historical data...';
    case 'completed':
      return 'Historical bills imported successfully.';
    default:
      return rawMsg || 'Processing your historical bills...';
  }
}

function updateProgressUi(data) {
  const msgEl = document.getElementById('m-status-message');
  const countEl = document.getElementById('m-progress-counter');
  const pctEl = document.getElementById('m-progress-percentage');
  const barEl = document.getElementById('m-progress-bar');

  const message = mapStatusToMessage(data.stage || data.status, data.message);
  if (msgEl) msgEl.textContent = message;

  const processed = data.processed || 0;
  const total = data.total || 0;

  if (countEl) {
    if (total > 0) {
      countEl.textContent = `${processed.toLocaleString()} / ${total.toLocaleString()} bills`;
    } else {
      countEl.textContent = 'Analyzing document...';
    }
  }

  const pct = Math.min(100, Math.max(0, data.percentage || (total > 0 ? Math.floor((processed / total) * 100) : 10)));
  if (pctEl) pctEl.textContent = `${pct}%`;
  if (barEl) barEl.style.width = `${pct}%`;
}

function showMigrationCompleted(data) {
  switchMigrationView('completed');

  const summary = data.summary || {};
  const total = data.total || summary.total_processed || 0;
  const imported = summary.imported || total;
  const review = summary.needs_review || 0;
  const dups = summary.duplicates_skipped || 0;

  const totalEl = document.getElementById('m-comp-total');
  if (totalEl) totalEl.textContent = total.toLocaleString();

  const importedEl = document.getElementById('m-comp-imported');
  if (importedEl) importedEl.textContent = imported.toLocaleString();

  const reviewEl = document.getElementById('m-comp-review');
  if (reviewEl) reviewEl.textContent = review.toLocaleString();

  const dupsEl = document.getElementById('m-comp-duplicates');
  if (dupsEl) dupsEl.textContent = dups.toLocaleString();

  const reviewBtn = document.getElementById('m-btn-review');
  if (reviewBtn) {
    reviewBtn.style.display = (review > 0) ? 'inline-block' : 'none';
  }
}

function showMigrationFailure(errorMsg, processed, total) {
  switchMigrationView('failed');

  const reasonEl = document.getElementById('m-fail-reason');
  if (reasonEl) reasonEl.textContent = errorMsg || 'An error occurred during historical bills extraction.';

  const partialEl = document.getElementById('m-fail-partial');
  if (partialEl) {
    if (processed && total && total > 0) {
      partialEl.style.display = 'block';
      partialEl.textContent = `${processed.toLocaleString()} / ${total.toLocaleString()} bills processed`;
    } else {
      partialEl.style.display = 'none';
    }
  }
}

function retryMigrationUpload() {
  if (selectedMigrationFile) {
    startMigrationUpload();
  } else {
    resetMigrationToInitial();
  }
}

async function checkActiveMigrationOnLoad() {
  try {
    const token = localStorage.getItem('token');
    const resp = await fetch('/api/migration/active', {
      headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
    });
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.active) {
        currentMigrationId = data.active.migration_id;
        currentJobCode = data.active.job_id || data.active.migration_code;
        switchMigrationView('processing');
        updateProgressUi(data.active);
        startMigrationTracking(currentMigrationId);
      }
    }
  } catch (e) {}
}

async function loadMigrationHistory() {
  const tbody = document.getElementById('migration-history-tbody');
  if (!tbody) return;

  try {
    const token = localStorage.getItem('token');
    const resp = await fetch('/api/migration/history', {
      headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
    });
    if (!resp.ok) return;

    const history = await resp.json();
    if (!history || !history.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--color-text-muted); padding: 24px;">No historical migration batches found.</td></tr>';
      return;
    }

    tbody.innerHTML = history.map(h => {
      const isRolledBack = h.status === 'ROLLED_BACK';
      const statusBadge = isRolledBack
        ? '<span class="status-badge" style="background: #FEE2E2; color: #DC2626;">Rolled Back</span>'
        : h.status === 'COMPLETED'
        ? '<span class="status-badge" style="background: #DCFCE7; color: #059669;">Completed</span>'
        : `<span class="status-badge" style="background: #EFF6FF; color: #2563EB;">${h.status}</span>`;

      const actionBtn = isRolledBack
        ? '<span style="font-size: 12px; color: #94A3B8;">Rolled back</span>'
        : `<button type="button" class="btn btn-secondary btn-sm" onclick="rollbackMigrationBatch(${h.id}, '${h.migration_code}')" style="color: #DC2626;">Rollback</button>`;

      return `
        <tr>
          <td><strong>${h.migration_code}</strong></td>
          <td>${h.file_name}</td>
          <td>${h.created_at || '-'}</td>
          <td>${(h.total_imported || 0).toLocaleString()} bills</td>
          <td>₹${(h.total_amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
          <td>${statusBadge}</td>
          <td>${actionBtn}</td>
        </tr>
      `;
    }).join('');

  } catch (e) {
    console.error('Failed to load migration history', e);
  }
}

async function rollbackMigrationBatch(migrationId, code) {
  if (!confirm(`Are you sure you want to rollback batch ${code}? All imported historical sales in this batch will be safely deleted without affecting live inventory.`)) {
    return;
  }

  try {
    const token = localStorage.getItem('token');
    const resp = await fetch(`/api/migration/rollback/${migrationId}`, {
      method: 'POST',
      headers: { ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
    });
    if (resp.ok) {
      alert(`Batch ${code} successfully rolled back.`);
      loadMigrationHistory();
    } else {
      const err = await resp.json().catch(() => ({}));
      alert(`Rollback failed: ${err.detail || 'Unknown error'}`);
    }
  } catch (e) {
    alert(`Rollback error: ${e.message}`);
  }
}
