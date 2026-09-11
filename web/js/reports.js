/* ==========================================================================
   EXPIRYGUARD WEB APP — REPORTS & ANALYTICS CONTROLLER
   ========================================================================== */

window.ReportsApp = {
  currentPeriod: 'today',
  customStartDate: null,
  customEndDate: null,
  analyticsData: null,

  async init() {
    // Set default dates for custom inputs
    const todayStr = new Date().toISOString().split('T')[0];
    const startInput = document.getElementById('rep-start-date');
    const endInput = document.getElementById('rep-end-date');
    if (startInput) startInput.value = todayStr;
    if (endInput) endInput.value = todayStr;

    await this.fetchAndRender();
  },

  selectPeriod(period) {
    this.currentPeriod = period;
    document.querySelectorAll('.period-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-period') === period);
    });

    const customBox = document.getElementById('custom-date-inputs');
    if (period === 'custom') {
      if (customBox) customBox.classList.add('active');
    } else {
      if (customBox) customBox.classList.remove('active');
      this.fetchAndRender();
    }
  },

  applyCustomDates() {
    const start = document.getElementById('rep-start-date')?.value;
    const end = document.getElementById('rep-end-date')?.value;
    if (!start || !end) {
      alert('Please select both start and end dates.');
      return;
    }
    if (start > end) {
      alert('Start date cannot be after end date.');
      return;
    }
    this.customStartDate = start;
    this.customEndDate = end;
    this.fetchAndRender();
  },

  refresh() {
    this.fetchAndRender();
  },

  async fetchAndRender() {
    const periodLabel = document.getElementById('period-display-label');
    const periodNameMap = {
      'today': 'Today',
      'yesterday': 'Yesterday',
      'this_week': 'This Week (7 Days)',
      'this_month': 'This Month (30 Days)',
      'last_month': 'Last Month',
      'custom': `Custom: ${this.customStartDate || ''} to ${this.customEndDate || ''}`
    };
    if (periodLabel) periodLabel.textContent = periodNameMap[this.currentPeriod] || this.currentPeriod;

    // 0ms instant cached render from AppDataPreloader / memory cache before network
    const qParams = new URLSearchParams({ period: this.currentPeriod });
    if (this.currentPeriod === 'custom') {
      if (this.customStartDate) qParams.append('start_date', this.customStartDate);
      if (this.customEndDate) qParams.append('end_date', this.customEndDate);
    }
    const endpoint = `/reports/analytics?${qParams.toString()}`;
    const preloaderCached = window.AppDataPreloader ? window.AppDataPreloader.get(endpoint) : null;
    const apiCached = window.api && typeof window.api.getCached === 'function' ? window.api.getCached(endpoint) : null;
    const cached = preloaderCached || (apiCached && apiCached.data !== undefined ? apiCached.data : apiCached);
    if (cached) {
      this.analyticsData = cached;
      this.renderAll(cached);
    }

    try {
      const data = await api.getReportsAnalytics(
        this.currentPeriod,
        this.currentPeriod === 'custom' ? this.customStartDate : null,
        this.currentPeriod === 'custom' ? this.customEndDate : null
      );
      this.analyticsData = data;
      this.renderAll(data);
    } catch (err) {
      console.error('Failed to fetch analytics:', err);
    }
  },

  formatCurrency(val) {
    const num = Number(val) || 0;
    return '₹' + num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },

  renderAll(data) {
    if (!data) return;

    const sales = data.sales_metrics || {};
    const purchases = data.purchases_metrics || {};
    const profit = data.profit_metrics || {};
    const inv = data.inventory_analytics || {};
    const rp = data.receivables_payables || {};
    const insights = data.actionable_insights || [];

    // 1. KPI Cards
    const elSales = document.getElementById('rep-total-sales');
    const elBillsSub = document.getElementById('rep-bills-sub');
    if (elSales) elSales.textContent = this.formatCurrency(sales.total_sales);
    if (elBillsSub) elBillsSub.textContent = `${sales.bill_count || 0} Bills (Avg ${this.formatCurrency(sales.avg_bill_value)})`;

    const elProfit = document.getElementById('rep-gross-profit');
    const elMarginSub = document.getElementById('rep-margin-sub');
    if (elProfit) elProfit.textContent = this.formatCurrency(profit.gross_profit);
    if (elMarginSub) elMarginSub.textContent = `Margin: ${(profit.margin_percent || 0).toFixed(1)}%`;

    const elPurchases = document.getElementById('rep-total-purchases');
    const elPurchasesSub = document.getElementById('rep-purchases-sub');
    if (elPurchases) elPurchases.textContent = this.formatCurrency(purchases.total_purchases);
    if (elPurchasesSub) elPurchasesSub.textContent = `${purchases.purchase_count || 0} Invoices (Avg ${this.formatCurrency(purchases.avg_purchase_value)})`;

    const elStockCost = document.getElementById('rep-stock-cost');
    const elStockMrp = document.getElementById('rep-stock-mrp-sub');
    if (elStockCost) elStockCost.textContent = this.formatCurrency(inv.cost_value);
    if (elStockMrp) elStockMrp.textContent = `MRP: ${this.formatCurrency(inv.mrp_value)}`;

    const elExpiring = document.getElementById('rep-expiring-count');
    const elExpiryRisk = document.getElementById('rep-expiry-risk-sub');
    if (elExpiring) elExpiring.textContent = inv.expiring_soon_count || 0;
    if (elExpiryRisk) elExpiryRisk.textContent = `${this.formatCurrency(inv.expiry_risk_value)} at Risk`;

    const elReceivables = document.getElementById('rep-receivables');
    const elPayables = document.getElementById('rep-payables-sub');
    if (elReceivables) elReceivables.textContent = this.formatCurrency(rp.total_receivables);
    if (elPayables) elPayables.textContent = `Payables: ${this.formatCurrency(rp.total_payables)}`;

    // 2. Actionable Insights Banner
    const banner = document.getElementById('insights-banner');
    if (banner) {
      if (insights && insights.length > 0) {
        const topInsight = insights[0];
        document.getElementById('insight-title').textContent = topInsight.title || 'Attention Needed';
        document.getElementById('insight-message').textContent = topInsight.message || '';
        const link = document.getElementById('insight-action-link');
        if (link) {
          link.textContent = topInsight.action_label || 'View';
          if (topInsight.action_type === 'expiry') link.href = 'inventory.html?filter=expiring';
          else if (topInsight.action_type === 'lowstock') link.href = 'inventory.html?filter=low_stock';
          else if (topInsight.action_type === 'khata') link.href = 'khata.html';
          else link.href = 'inventory.html';
        }
        banner.style.display = 'flex';
      } else {
        banner.style.display = 'none';
      }
    }

    // 3. Trend Chart
    this.renderTrends(sales.trend || [], purchases.trend || []);

    // 4. Payment Split
    this.renderPaymentSplit(sales.payment_split || {});

    // 5. Product Performance
    this.renderProductPerformance(data.product_performance || {});

    // 6. GST Snapshot
    this.renderGstSnapshot(sales.total_sales || 0, purchases.total_purchases || 0);
  },

  renderTrends(salesTrend, purchasesTrend) {
    const container = document.getElementById('trend-bars-container');
    if (!container) return;

    if (!salesTrend || salesTrend.length === 0) {
      container.innerHTML = `<div style="margin: auto; color: var(--color-text-muted); font-size: 13px;">No sales or purchase data recorded for this period.</div>`;
      return;
    }

    const purchasesMap = {};
    if (Array.isArray(purchasesTrend)) {
      purchasesTrend.forEach(p => { purchasesMap[p.date] = p.purchases || 0; });
    }

    let maxVal = 100;
    salesTrend.forEach(s => {
      const pVal = purchasesMap[s.date] || 0;
      if (s.sales > maxVal) maxVal = s.sales;
      if (pVal > maxVal) maxVal = pVal;
    });

    container.innerHTML = salesTrend.map(s => {
      const pAmt = purchasesMap[s.date] || 0;
      const sHeight = Math.max(4, Math.round((s.sales / maxVal) * 130));
      const pHeight = Math.max(4, Math.round((pAmt / maxVal) * 130));
      const dateParts = s.date.split('-');
      const dateShort = `${dateParts[2]}/${dateParts[1]}`;

      return `
        <div class="trend-bar-col" title="${s.date}\nSales: ${this.formatCurrency(s.sales)} (${s.bills} bills)\nPurchases: ${this.formatCurrency(pAmt)}">
          <div style="display: flex; gap: 2px; width: 100%; align-items: flex-end; justify-content: center;">
            <div class="trend-bar-fill" style="height: ${sHeight}px;"></div>
            <div class="trend-bar-fill trend-bar-purchases" style="height: ${pHeight}px;"></div>
          </div>
          <span class="trend-bar-label">${dateShort}</span>
        </div>
      `;
    }).join('');
  },

  renderPaymentSplit(split) {
    const cash = Number(split.CASH || 0);
    const upi = Number(split.UPI || 0);
    const card = Number(split.CARD || 0);
    const credit = Number(split.CREDIT || 0);
    const total = cash + upi + card + credit;

    const elCash = document.getElementById('pay-cash-val');
    const elUpi = document.getElementById('pay-upi-val');
    const elCard = document.getElementById('pay-card-val');
    const elCredit = document.getElementById('pay-credit-val');

    if (elCash) elCash.textContent = this.formatCurrency(cash);
    if (elUpi) elUpi.textContent = this.formatCurrency(upi);
    if (elCard) elCard.textContent = this.formatCurrency(card);
    if (elCredit) elCredit.textContent = this.formatCurrency(credit);

    const segCash = document.getElementById('seg-cash');
    const segUpi = document.getElementById('seg-upi');
    const segCard = document.getElementById('seg-card');
    const segCredit = document.getElementById('seg-credit');

    if (total > 0) {
      if (segCash) segCash.style.width = `${(cash / total * 100).toFixed(1)}%`;
      if (segUpi) segUpi.style.width = `${(upi / total * 100).toFixed(1)}%`;
      if (segCard) segCard.style.width = `${(card / total * 100).toFixed(1)}%`;
      if (segCredit) segCredit.style.width = `${(credit / total * 100).toFixed(1)}%`;
    } else {
      if (segCash) segCash.style.width = '25%';
      if (segUpi) segUpi.style.width = '25%';
      if (segCard) segCard.style.width = '25%';
      if (segCredit) segCredit.style.width = '25%';
    }
  },

  renderProductPerformance(perf) {
    const topRevenue = perf.by_revenue || [];
    const slowMoving = perf.slow_moving || [];

    const topTbody = document.getElementById('top-selling-body');
    if (topTbody) {
      if (topRevenue.length === 0) {
        topTbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--color-text-muted); padding: 24px;">No items sold in this period.</td></tr>`;
      } else {
        topTbody.innerHTML = topRevenue.map(p => `
          <tr>
            <td style="font-weight: 600; color: var(--color-text-primary);">${escapeHtml(p.product_name)}</td>
            <td class="num-tabular">${p.units_sold} units</td>
            <td style="text-align: right;"><strong class="num-currency">${this.formatCurrency(p.revenue)}</strong></td>
          </tr>
        `).join('');
      }
    }

    const slowTbody = document.getElementById('slow-moving-body');
    if (slowTbody) {
      if (slowMoving.length === 0) {
        slowTbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--status-safe); padding: 24px;">🎉 All current stock has active sales turnover!</td></tr>`;
      } else {
        slowTbody.innerHTML = slowMoving.map(p => `
          <tr>
            <td style="font-weight: 600; color: var(--color-text-primary);">${escapeHtml(p.product_name)}</td>
            <td class="num-tabular">${p.quantity}</td>
            <td class="num-currency">${this.formatCurrency(p.mrp)}</td>
            <td><span class="badge badge-warning">0 sold in period</span></td>
          </tr>
        `).join('');
      }
    }
  },

  renderGstSnapshot(salesTotal, purchasesTotal) {
    // Standard pharmaceutical average blended GST rate ~12% (5.35% CGST + 5.35% SGST or 12% IGST)
    const outputGst = Math.round(salesTotal * (12 / 112) * 100) / 100;
    const inputGst = Math.round(purchasesTotal * (12 / 112) * 100) / 100;
    const netGst = Math.max(0, Math.round((outputGst - inputGst) * 100) / 100);

    const elOutput = document.getElementById('rep-gst-output');
    const elItc = document.getElementById('rep-gst-itc');
    const elNet = document.getElementById('rep-gst-net');

    if (elOutput) elOutput.textContent = this.formatCurrency(outputGst);
    if (elItc) elItc.textContent = this.formatCurrency(inputGst);
    if (elNet) elNet.textContent = this.formatCurrency(netGst);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('reports-page')) {
    ReportsApp.init();
  }
});
