/**
 * ExpiryGuard — Public SaaS Landing Website Scripts
 * Features: Sticky Navbar, Mobile Menu, Interactive Product Demo, FAQ Accordion, Pilot Lead AJAX Form
 */

document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  initMobileMenu();
  initProductDemo();
  initFaqAccordion();
  initPilotLeadForm();
  initSmoothScroll();
  initMobileStickyCta();
});

/* ==========================================================================
   1. STICKY NAVBAR SCROLL EFFECT
   ========================================================================== */
function initNavbar() {
  const navbar = document.getElementById('main-navbar');
  if (!navbar) return;

  const handleScroll = () => {
    if (window.scrollY > 20) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll();
}

/* ==========================================================================
   2. MOBILE HAMBURGER MENU
   ========================================================================== */
function initMobileMenu() {
  const toggleBtn = document.getElementById('mobile-menu-toggle');
  const navMenu = document.getElementById('nav-menu');
  if (!toggleBtn || !navMenu) return;

  toggleBtn.addEventListener('click', () => {
    const isOpen = navMenu.classList.toggle('mobile-open');
    toggleBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    toggleBtn.innerHTML = isOpen
      ? `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>`
      : `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>`;
  });

  // Close menu on nav item click
  navMenu.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
      navMenu.classList.remove('mobile-open');
      toggleBtn.setAttribute('aria-expanded', 'false');
      toggleBtn.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>`;
    });
  });
}

/* ==========================================================================
   3. INTERACTIVE HERO PRODUCT DEMO
   ========================================================================== */
function initProductDemo() {
  const steps = [
    { name: 'Scan Medicines', icon: '📸' },
    { name: 'AI Recognition', icon: '🤖' },
    { name: 'Bill Generated', icon: '💳' },
    { name: 'Stock Updated', icon: '📦' }
  ];

  let currentStepIndex = 0;
  const pills = document.querySelectorAll('.workflow-step-pill');
  const laser = document.getElementById('demo-laser');
  const billRows = document.querySelectorAll('.demo-bill-row');
  const stockIndicator = document.getElementById('demo-stock-sync');
  const demoTimer = document.getElementById('demo-timer-badge');

  function setStep(index) {
    currentStepIndex = index;
    pills.forEach((p, i) => {
      if (i <= index) {
        p.classList.add('active');
      } else {
        p.classList.remove('active');
      }
    });

    if (laser) {
      laser.style.display = index === 0 || index === 1 ? 'block' : 'none';
    }

    if (billRows) {
      billRows.forEach(row => {
        row.style.opacity = index >= 2 ? '1' : '0.4';
      });
    }

    if (stockIndicator) {
      stockIndicator.style.opacity = index >= 3 ? '1' : '0.5';
      stockIndicator.style.borderColor = index >= 3 ? '#16A34A' : '#E5E7EB';
    }

    if (demoTimer && index >= 2) {
      demoTimer.textContent = 'Demo Time: ~2.8s ✓';
    }
  }

  // Auto-cycle demo gently
  let demoInterval = setInterval(() => {
    currentStepIndex = (currentStepIndex + 1) % steps.length;
    setStep(currentStepIndex);
  }, 3200);

  // Allow clicking pills to test specific steps
  pills.forEach((pill, idx) => {
    pill.addEventListener('click', () => {
      clearInterval(demoInterval);
      setStep(idx);
    });
  });
}

/* ==========================================================================
   4. FAQ ACCORDION
   ========================================================================== */
function initFaqAccordion() {
  const faqItems = document.querySelectorAll('.faq-item');
  if (!faqItems.length) return;

  faqItems.forEach(item => {
    const trigger = item.querySelector('.faq-trigger');
    if (!trigger) return;

    trigger.addEventListener('click', () => {
      const isActive = item.classList.contains('active');

      // Close all others
      faqItems.forEach(other => {
        other.classList.remove('active');
        const otherTrigger = other.querySelector('.faq-trigger');
        if (otherTrigger) otherTrigger.setAttribute('aria-expanded', 'false');
      });

      // Toggle current
      if (!isActive) {
        item.classList.add('active');
        trigger.setAttribute('aria-expanded', 'true');
      }
    });
  });
}

/* ==========================================================================
   5. PILOT LEAD FORM AJAX SUBMISSION
   ========================================================================== */
function initPilotLeadForm() {
  const form = document.getElementById('pilot-lead-form');
  const statusBox = document.getElementById('form-status-box');
  const submitBtn = document.getElementById('btn-submit-pilot');
  if (!form || !statusBox || !submitBtn) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Reset status
    statusBox.className = 'form-status-box';
    statusBox.style.display = 'none';
    statusBox.textContent = '';

    const fullName = form.querySelector('#full_name')?.value?.trim();
    const pharmacyName = form.querySelector('#pharmacy_name')?.value?.trim();
    const city = form.querySelector('#city')?.value?.trim();
    const phone = form.querySelector('#phone')?.value?.trim();
    const currentBillingMethod = form.querySelector('#current_billing_method')?.value;
    const billsPerDay = form.querySelector('#bills_per_day')?.value;
    const numPharmacies = form.querySelector('#num_pharmacies')?.value;
    const biggestProblem = form.querySelector('#biggest_problem')?.value?.trim();

    // Client-side validation
    if (!fullName || !pharmacyName || !city || !phone || !currentBillingMethod || !billsPerDay || !numPharmacies) {
      statusBox.className = 'form-status-box error';
      statusBox.textContent = 'Please fill out all required fields before submitting.';
      statusBox.style.display = 'block';
      return;
    }

    const cleanPhone = phone.replace(/[^\d+]/g, '');
    if (cleanPhone.length < 10) {
      statusBox.className = 'form-status-box error';
      statusBox.textContent = 'Please provide a valid 10-digit phone number so we can reach out.';
      statusBox.style.display = 'block';
      return;
    }

    // Set Loading State
    submitBtn.disabled = true;
    const originalBtnText = submitBtn.innerHTML;
    submitBtn.innerHTML = `
      <svg class="spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;">
        <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
        <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"></path>
      </svg>
      Submitting Request...
    `;

    // Format combined problem containing number of outlets
    let combinedProblem = `[Number of Pharmacies: ${numPharmacies}]`;
    if (biggestProblem) {
      combinedProblem += `\nBiggest Problem: ${biggestProblem}`;
    }

    try {
      const payload = {
        full_name: fullName,
        pharmacy_name: pharmacyName,
        city: city,
        phone: cleanPhone,
        current_billing_method: currentBillingMethod,
        bills_per_day: billsPerDay,
        biggest_problem: combinedProblem
      };

      const response = await fetch('/api/pilot-leads', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${response.status}`);
      }

      const result = await response.json();

      // Show Success State
      form.innerHTML = `
        <div style="text-align: center; padding: 36px 16px;">
          <div style="width: 56px; height: 56px; background-color: #DCFCE7; color: #16A34A; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 20px auto;">
            ✓
          </div>
          <h3 style="font-size: 24px; font-weight: 800; color: #111827; margin-bottom: 12px;">Thanks, ${escapeHtml(fullName)}!</h3>
          <p style="font-size: 16px; color: #4B5563; max-width: 500px; margin: 0 auto 16px auto; line-height: 1.6;">
            We’ve received your pilot request for <strong>${escapeHtml(pharmacyName)}</strong> in ${escapeHtml(city)}.
          </p>
          <p style="font-size: 14.5px; color: #16A34A; font-weight: 600; background-color: #F0FDF4; border: 1px solid #86EFAC; padding: 12px 18px; border-radius: 8px; display: inline-block;">
            Someone from the ExpiryGuard team will get in touch on ${escapeHtml(cleanPhone)} soon.
          </p>
        </div>
      `;
    } catch (err) {
      console.error('Pilot submission error:', err);
      statusBox.className = 'form-status-box error';
      statusBox.textContent = `Could not submit your request: ${err.message}. Please check your connection and try again.`;
      statusBox.style.display = 'block';
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalBtnText;
    }
  });
}

/* ==========================================================================
   6. SMOOTH SCROLLING & CTA FOCUS
   ========================================================================== */
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href');
      if (targetId === '#') return;
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (targetId === '#pilot-form') {
          setTimeout(() => {
            const firstInput = targetEl.querySelector('#full_name');
            if (firstInput) firstInput.focus();
          }, 600);
        }
      }
    });
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>"']/g, function(m) {
    switch (m) {
      case '&': return '&amp;';
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '"': return '&quot;';
      case "'": return '&#039;';
      default: return m;
    }
  });
}

/* ==========================================================================
   7. MOBILE STICKY "JOIN THE PILOT" CTA
   ========================================================================== */
function initMobileStickyCta() {
  const stickyBar = document.getElementById('mobile-sticky-cta');
  const pilotSection = document.getElementById('pilot-form');
  if (!stickyBar) return;

  const updateSticky = () => {
    if (window.innerWidth > 768) {
      stickyBar.classList.remove('visible');
      return;
    }

    const scrollY = window.scrollY;
    let inForm = false;
    if (pilotSection) {
      const rect = pilotSection.getBoundingClientRect();
      if (rect.top <= window.innerHeight && rect.bottom >= 0) {
        inForm = true;
      }
    }

    if (scrollY > 380 && !inForm) {
      stickyBar.classList.add('visible');
    } else {
      stickyBar.classList.remove('visible');
    }
  };

  window.addEventListener('scroll', updateSticky, { passive: true });
  window.addEventListener('resize', updateSticky, { passive: true });
  updateSticky();
}
