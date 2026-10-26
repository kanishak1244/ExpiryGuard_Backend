/**
 * Documents & OCR: side-by-side invoice review workspace.
 *   left  : the ORIGINAL uploaded bill (fetched with the user's login, never a public URL), zoom / open larger
 *   right : read-only supplier + invoice summary and the extracted medicine lines as a table
 *   bar   : Edit Bill Details (opens the correction editor, which saves corrections only) · Back · Confirm & Add to Stock
 * Reading and rendering here changes nothing. Stock is posted only by the explicit Confirm, on the server.
 * The pure render helpers are exported for Node tests.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  Object.keys(api).forEach(k => { root[k] = api[k]; });
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const money = (n) => (n == null || n === '' || isNaN(n) ? null : Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const MISSING = '<span class="dr-miss" title="Not read from the bill - add it with Edit Bill Details">Missing</span>';
  const NA = '<span class="dr-na">—</span>';

  function drFieldBlock(line, field) {
    return (line.blocking || []).find(b => b.field === field);
  }
  function drFieldWarn(line, field) {
    return (line.warnings || []).find(w => w.field === field);
  }

  // One table cell: the value, or Missing (critical field), or — (optional field). Problems get a tooltip and a mark.
  function drCell(line, field, text, opts) {
    opts = opts || {};
    const block = drFieldBlock(line, field);
    const warn = drFieldWarn(line, field);
    const cls = ['dr-c', opts.num ? 'num' : '', block ? 'bad' : '', !block && warn ? 'warn' : ''].filter(Boolean).join(' ');
    const title = block ? block.message : (warn ? warn.message : '');
    let inner;
    if (text == null || text === '') inner = (opts.critical || block) ? MISSING : NA;
    else inner = esc(text);
    return `<td class="${cls}"${title ? ` title="${esc(title)}"` : ''}>${inner}${!block && warn ? ' <span class="dr-wdot" aria-label="check">●</span>' : ''}</td>`;
  }

  function drTaxable(line) {
    if (line.quantity == null || line.purchase_price == null) return null;
    const gross = line.quantity * line.purchase_price;
    return gross - gross * ((line.discount_percent || 0) / 100);
  }

  // "2028-12-31" -> "12/2028" (compact, still unambiguous); anything else is shown as read.
  function drExpiryText(iso) {
    const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(String(iso || ''));
    return m ? m[2] + '/' + m[1] : (iso || null);
  }

  function drLinesTableHtml(lines) {
    if (!lines || !lines.length) {
      return '<div class="dr-empty">No medicine lines were extracted from this bill. Use <b>Edit Bill Details</b> to enter them from the original on the left.</div>';
    }
    const head = `<tr><th class="n">#</th><th class="name">Medicine</th><th class="num">GST %</th><th>Batch</th><th>Expiry</th>
      <th class="num">Qty</th><th class="num">Rate</th><th class="num">MRP</th>
      <th class="num" title="Quantity × rate after discount, before GST (calculated)">Taxable</th><th class="num" title="Line amount printed on the bill">Amount</th></tr>`;
    const rows = lines.map(l => {
      const bad = (l.blocking || []).length;
      const qty = l.quantity == null ? null : (l.quantity + (l.free_qty ? ` +${l.free_qty}` : ''));
      const taxable = drTaxable(l);
      const hsnBad = drFieldBlock(l, 'hsn_code');
      const matchLabel = l.match ? ({ inventory: 'In your stock', catalog: 'In catalog', new: 'New medicine' }[l.match.status] || '') : '';
      const sub = [
        hsnBad ? `<span class="dr-miss" title="${esc(hsnBad.message)}">HSN invalid</span>` : (l.hsn_code ? 'HSN ' + esc(l.hsn_code) : ''),
        l.discount_percent ? `Disc ${esc(l.discount_percent)}%` : '',
        l.match ? `<span class="dr-m ${esc(l.match.status)}" title="${esc(l.match.text)}">${matchLabel}</span>` : '',
      ].filter(Boolean).join(' · ');
      return `<tr class="${bad ? 'dr-rowbad' : ''}">
        <td class="n">${l.row}</td>
        <td class="name${drFieldBlock(l, 'product_name') ? ' bad' : ''}">${l.product_name ? esc(l.product_name) : MISSING}${sub ? `<small class="dr-match">${sub}</small>` : ''}</td>
        ${drCell(l, 'gst_rate', l.gst_rate == null ? null : l.gst_rate, { num: true, critical: true })}
        ${drCell(l, 'batch_number', l.batch_number, { critical: true })}
        ${drCell(l, 'expiry_date', drExpiryText(l.expiry_date), { critical: true })}
        ${drCell(l, 'quantity', qty, { num: true, critical: true })}
        ${drCell(l, 'purchase_price', money(l.purchase_price), { num: true, critical: true })}
        ${drCell(l, 'mrp', money(l.mrp), { num: true, critical: true })}
        <td class="dr-c num">${taxable == null ? NA : money(taxable)}</td>
        <td class="dr-c num">${l.total_price == null ? NA : money(l.total_price)}</td></tr>`;
    }).join('');
    return `<table class="dr-table"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
  }

  function drStatusBadge(status) {
    const s = String(status || '');
    const cls = { 'Verified': 'ok', 'Needs Review': 'warn', 'Failed': 'bad', 'Processing': 'info' }[s] || 'info';
    return `<span class="dr-badge ${cls}">${esc(s || 'Unknown')}</span>`;
  }

  function drSupplierHtml(v) {
    if (v.supplier) {
      const extra = [v.supplier.gstin, v.supplier.phone].filter(Boolean).map(esc).join(' · ');
      return `<div class="dr-sup"><b>${esc(v.supplier.name)}</b> <span class="dr-badge ok">Linked</span>${extra ? `<div class="dr-sub">${extra}</div>` : ''}</div>`;
    }
    const label = v.supplier_status === 'needs_matching' ? 'Needs supplier matching' : 'Unlinked';
    const read = v.extracted_supplier_name ? `Bill says: <b>${esc(v.extracted_supplier_name)}</b>. ` : '';
    return `<div class="dr-sup warn"><span class="dr-badge warn">${label}</span> <span class="dr-sub">${read}No supplier is linked, so this bill cannot be confirmed yet.</span>
      <button type="button" class="btn btn-secondary btn-sm" onclick="drEdit('supplier')">Link or create supplier</button></div>`;
  }

  function drSummaryHtml(v) {
    const comp = v.computed ? money(v.computed.total) : null;
    const item = (label, value) => `<div class="dr-f"><span>${label}</span><b>${value}</b></div>`;
    return `<div class="dr-summary">
      ${drSupplierHtml(v)}
      <div class="dr-fields">
        ${item('Supplier invoice no.', v.invoice_number ? esc(v.invoice_number) : MISSING)}
        ${item('Invoice date', v.invoice_date ? esc(v.invoice_date) : MISSING)}
        ${item('Invoice total', v.printed_total == null ? NA : '₹' + money(v.printed_total))}
        ${item('OCR status', drStatusBadge(v.status))}
        ${item('Medicine lines', v.line_count)}
        ${item('Calculated total', comp ? '₹' + comp : NA)}
      </div>
      ${v.verified ? '' : drReconHtml(v)}
      ${v.verified ? '' : (v.notes || []).map(n => `<div class="dr-note warn">${esc(n)}</div>`).join('')}
      ${v.draft ? `<div class="dr-note info">Saved as draft <b>${esc(v.draft.reference)}</b>. Find it under Purchase Management → Drafts. Nothing has been added to stock.</div>` : ''}
      ${v.corrected ? '<div class="dr-note info">Showing the corrected details saved for this bill. The original OCR reading is kept.</div>' : ''}
      ${v.ocr_error ? `<div class="dr-note bad">OCR could not read this bill: ${esc(v.ocr_error)}. The original is still available on the left.</div>` : ''}
    </div>`;
  }

  // How the total was calculated and where it differs from the bill: shown only when it does not reconcile.
  function drReconHtml(v) {
    const r = v.reconciliation;
    if (!r || r.status !== 'REVIEW') return '';
    const rows = (r.components || []).map(c => `<tr class="${c.ok ? '' : 'dr-rowbad'}"><td>${esc(c.label)}</td><td class="num">${money(c.printed)}</td>
      <td class="num">${money(c.calculated)}</td><td class="num">${c.difference > 0 ? '+' : ''}${money(c.difference)}</td></tr>`).join('');
    return `<div class="dr-note warn"><b>Total does not reconcile:</b> printed ₹${money(r.printed_total)}, calculated ₹${money(r.calculated_total)}, difference
      ${r.difference > 0 ? '+' : ''}₹${money(r.difference)} (tolerance ₹${money(r.tolerance)}).
      <table class="dr-table" style="margin-top:4px"><thead><tr><th>Part</th><th class="num">Bill</th><th class="num">Calculated</th><th class="num">Diff</th></tr></thead><tbody>${rows}</tbody></table>
      ${(r.likely_causes || []).map(c => `<div>• ${esc(c)}</div>`).join('')}</div>`;
  }

  function drProblemsHtml(v) {
    if (!v.blocking || !v.blocking.length || v.verified) return '';
    return `<div class="dr-problems" role="alert"><b>${v.blocking_count} problem${v.blocking_count === 1 ? '' : 's'} to fix before confirming</b>
      <ul>${v.blocking.slice(0, 5).map(b => `<li>${esc(b.field)}: ${esc(b.message)}</li>`).join('')}${v.blocking.length > 5 ? `<li>…and ${v.blocking.length - 5} more</li>` : ''}</ul></div>`;
  }

  // Which buttons make sense for the document's state.
  function drActions(v) {
    return {
      edit: v.can_edit,
      draft: !v.verified,
      confirm: !v.verified && !v.failed && String(v.status || '').toLowerCase() !== 'processing',
      ocr: !v.verified && (v.failed || String(v.status || '').toLowerCase() === 'processing'),
      back: true,
    };
  }

  const exported = { drReconHtml, drExpiryText, drLinesTableHtml, drSummaryHtml, drProblemsHtml, drStatusBadge, drActions, drCell, drTaxable };
  if (typeof document === 'undefined') return exported;

  // ------------------------------------------------------------------------------------------------ browser part
  const $ = (id) => document.getElementById(id);
  const S = { id: null, view: null, blobUrl: null, blobType: null, zoom: 1, busy: false };

  async function fetchOriginal(id) {
    const headers = await api.getHeaders(false);
    const res = await fetch(API_BASE_URL + '/documents/' + id + '/file', { headers, credentials: 'include' });
    if (!res.ok) {
      let msg = 'The original file could not be loaded.';
      try { msg = (await res.json()).detail || msg; } catch (e) { /* keep default */ }
      throw new Error(msg);
    }
    return res.blob();
  }

  function revoke() { if (S.blobUrl) { URL.revokeObjectURL(S.blobUrl); S.blobUrl = null; } }

  async function renderOriginal(id, target, fileType) {
    target.innerHTML = '<div class="dr-pv-msg">Loading original bill…</div>';
    try {
      const blob = await fetchOriginal(id);
      if (S.id !== id) return;
      revoke();
      S.blobUrl = URL.createObjectURL(blob);
      S.blobType = blob.type || fileType || '';
      if (/pdf/i.test(S.blobType)) {
        target.innerHTML = `<iframe class="dr-pdf" title="Original supplier bill" src="${S.blobUrl}#toolbar=1&navpanes=0&view=FitH"></iframe>`;
      } else {
        target.innerHTML = `<img class="dr-img" id="dr-img" alt="Original supplier bill" src="${S.blobUrl}">`;
        S.zoom = 1; applyZoom();
      }
    } catch (e) {
      target.innerHTML = `<div class="dr-pv-msg bad"><b>Original bill not available</b><br>${esc(e.message)}<br><button type="button" class="btn btn-secondary btn-sm" style="margin-top:8px" onclick="drReloadOriginal()">Retry</button></div>`;
    }
  }

  function applyZoom() {
    const img = $('dr-img');
    if (!img) return;
    img.style.width = (S.zoom * 100) + '%';
    img.style.maxWidth = S.zoom <= 1 ? '100%' : 'none';
    $('dr-zoom-label').textContent = Math.round(S.zoom * 100) + '%';
  }

  window.drZoom = function (d) {
    if ($('dr-img')) { S.zoom = d === 0 ? 1 : Math.min(4, Math.max(0.5, S.zoom + d)); applyZoom(); }
  };
  window.drOpenLarge = function () { if (S.blobUrl) window.open(S.blobUrl, '_blank', 'noopener'); };
  window.drReloadOriginal = function () { if (S.id) renderOriginal(S.id, $('dr-preview'), S.view && S.view.file_type); };

  function setBusy(b) {
    S.busy = b;
    ['dr-btn-confirm', 'dr-btn-edit', 'dr-btn-ocr', 'dr-btn-draft'].forEach(id => { const e = $(id); if (e) e.disabled = b; });
  }

  function paint() {
    const v = S.view;
    $('dr-title').textContent = v.title || 'Invoice';
    $('dr-meta').textContent = [v.file_type, v.file_size ? Math.round(v.file_size / 1024) + ' KB' : '', v.uploaded_at ? 'uploaded ' + v.uploaded_at.slice(0, 10) : ''].filter(Boolean).join(' · ');
    $('dr-right-top').innerHTML = drSummaryHtml(v);
    $('dr-lines').innerHTML = drLinesTableHtml(v.lines);
    $('dr-problems').innerHTML = drProblemsHtml(v);
    const a = drActions(v);
    $('dr-btn-edit').style.display = a.edit ? '' : 'none';
    $('dr-btn-draft').style.display = a.draft ? '' : 'none';
    $('dr-btn-confirm').style.display = a.confirm ? '' : 'none';
    $('dr-btn-ocr').style.display = a.ocr ? '' : 'none';
    $('dr-verified-note').style.display = v.verified ? '' : 'none';
    $('dr-btn-confirm').title = v.blocking_count ? 'Fix the listed problems first (Edit Bill Details)' : '';
  }

  async function loadView() {
    S.view = await api.request('/documents/' + S.id + '/review');
    paint();
    return S.view;
  }

  window.openReviewWorkspace = async function (id) {
    S.id = id;
    $('docs-list-view').style.display = 'none';
    $('dr-workspace').style.display = 'block';
    $('dr-preview').innerHTML = '<div class="dr-pv-msg">Loading original bill…</div>';
    $('dr-lines').innerHTML = '<div class="dr-empty">Loading…</div>';
    $('dr-right-top').innerHTML = '';
    $('dr-flash').style.display = 'none';
    try {
      await loadView();
      renderOriginal(id, $('dr-preview'), S.view.file_type);       // loads in parallel with nothing else blocking the data
    } catch (e) {
      $('dr-lines').innerHTML = `<div class="dr-empty bad">Could not open this document: ${esc(e.message)}</div>`;
    }
  };

  window.drBack = function () {
    revoke();
    S.id = null;
    $('dr-workspace').style.display = 'none';
    $('docs-list-view').style.display = '';
    if (typeof loadDocuments === 'function') loadDocuments();
  };

  function flash(text, kind) {
    const f = $('dr-flash');
    f.className = 'dr-note ' + (kind || 'info');
    f.textContent = text;
    f.style.display = 'block';
  }

  window.drRunOcr = async function () {
    if (!S.id || S.busy) return;
    setBusy(true);
    flash('Reading the bill with DawaiFlow AI…', 'info');
    try {
      await api.request('/documents/' + S.id + '/ocr', { method: 'POST' });
      await loadView();
      flash('OCR finished. Check the extracted lines against the original.', 'info');
    } catch (e) {
      const m = String(e.message || '');
      if (/HAS_CORRECTIONS/.test(m) && window.confirm('This bill has corrections saved by a user. Running OCR again replaces the reading they were made on (the corrections are kept as a backup). Run it anyway?')) {
        try { await api.request('/documents/' + S.id + '/ocr?force=true', { method: 'POST' }); await loadView(); flash('OCR finished.', 'info'); }
        catch (e2) { flash(apiMsg(e2), 'bad'); }
      } else { flash(apiMsg(e), 'bad'); }
    } finally { setBusy(false); }
  };

  function apiMsg(e) {
    const t = String((e && e.message) || e || '');
    const j = t.indexOf('{');
    if (j >= 0) { try { const d = JSON.parse(t.slice(j)).detail; if (typeof d === 'string') return d; } catch (_) { /* fall through */ } }
    return t.slice(0, 300);
  }
  window.drApiMsg = apiMsg;

  window.drConfirm = async function () {
    if (!S.id || S.busy) return;
    const v = S.view;
    if (v.blocking_count) {
      $('dr-problems').scrollIntoView({ block: 'nearest' });
      flash('This bill is not complete yet. Use Edit Bill Details to fix the problems listed, then confirm.', 'bad');
      $('dr-btn-edit').focus();
      return;
    }
    const lines = v.lines.length;
    const total = v.computed ? '₹' + money(v.computed.total) : '';
    let ack = false;
    let reason = null;
    const belowCost = v.lines.some(l => (l.warnings || []).some(w => w.field === 'mrp' && /lower than the purchase rate/.test(w.message)));
    if (v.total_differs) {
      // the calculated total does not match the bill: correct the details, or give a reason (kept in the audit trail)
      const r = v.reconciliation;
      reason = window.prompt(`The calculated total ₹${money(r.calculated_total)} does not match the printed total ₹${money(r.printed_total)} (difference ${r.difference > 0 ? '+' : ''}₹${money(r.difference)}).\n\n` +
        'Best: press Cancel, use Edit Bill Details and fix the figure that is wrong.\nTo add this bill to stock anyway, type the reason (it is recorded with your name and the time):');
      if (!reason || reason.trim().length < 5) return;
      reason = reason.trim();
    }
    if (belowCost) {
      if (!window.confirm('Some MRPs are lower than the purchase rate. Check the bill. Confirm and add to stock anyway?')) return;
      ack = true;
    } else if (v.total_differs) {
      // already confirmed through the reason above
    } else if (!window.confirm(`Add ${lines} medicine line(s) (${total}) from invoice ${v.invoice_number} to stock and to ${v.supplier.name}'s account?`)) {
      return;
    }
    setBusy(true);
    try {
      const res = await api.request('/documents/' + S.id + '/confirm-review', { method: 'POST', body: JSON.stringify({ acknowledge_warnings: ack, override_reason: reason }) });
      await loadView();
      flash(res.message + ' ' + 'The original bill stays saved.', 'ok');
    } catch (e) {
      const m = apiMsg(e);
      flash(m + ' Nothing was added to stock; you can fix this and try again.', 'bad');
      try { await loadView(); } catch (_) { /* keep what is shown */ }
    } finally { setBusy(false); }
  };

  window.drEdit = function (focus) {
    if (!S.id || !S.view || !S.view.can_edit) return;
    if (typeof openCorrectionEditor === 'function') openCorrectionEditor(S.id, S.view, focus);
  };

  function draftFlash(res) {
    const ref = res && res.draft ? res.draft.reference : 'the draft';
    flash(`Saved as draft ${ref}. It is listed under Purchase Management → Drafts. Nothing was added to stock.`, 'ok');
  }

  // Save as Draft from the read-only review: keeps the bill's current details as an open purchase draft.
  window.drSaveDraft = async function () {
    if (!S.id || S.busy) return;
    setBusy(true);
    try {
      const res = await api.request('/documents/' + S.id + '/save-draft', { method: 'POST' });
      S.view = res.review; paint();
      draftFlash(res);
    } catch (e) {
      flash(apiMsg(e) + ' The bill and its details are unchanged.', 'bad');
    } finally { setBusy(false); }
  };

  window.drAfterDraftSaved = async function (res) {
    await loadView();
    draftFlash(res);
  };

  window.drAfterCorrectionsSaved = async function () {
    await loadView();
    flash('Corrections saved. Nothing was added to stock yet; review the details and confirm when ready.', 'ok');
  };

  window.drCurrentOriginalUrl = function () { return S.blobUrl; };
  window.drCurrentId = function () { return S.id; };

  return exported;
});
