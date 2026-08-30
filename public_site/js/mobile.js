/* ==========================================================================
   DAWAIFLOW — MOBILE COMPONENT INTERACTIVITY HANDLERS
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
  // 1. ADAPTIVE DESKTOP RESIZE BOOTSTRAP
  // If the mobile view is loaded but window size increases to desktop,
  // we fetch and rewrite the DOM with the desktop index.html.
  function checkViewportResize() {
    if (window.innerWidth > 768) {
      try {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/index.html', false);
        xhr.send(null);
        if (xhr.status === 200) {
          document.open();
          document.write(xhr.responseText);
          document.close();
        }
      } catch (e) {
        window.location.replace("/");
      }
    }
  }
  
  window.addEventListener('resize', () => {
    if (window.innerWidth > 768) {
      checkViewportResize();
    }
  });

  // 2. HAMBURGER MENU DRAWER
  const hamburgerBtn = document.getElementById('mobile-hamburger-toggle');
  const drawerMenu = document.getElementById('mobile-drawer-menu');
  
  if (hamburgerBtn && drawerMenu) {
    hamburgerBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      drawerMenu.classList.toggle('open');
    });

    document.addEventListener('click', (e) => {
      if (!drawerMenu.contains(e.target) && !hamburgerBtn.contains(e.target)) {
        drawerMenu.classList.remove('open');
      }
    });

    drawerMenu.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        drawerMenu.classList.remove('open');
      });
    });
  }

  // 3. JOIN PILOT MODAL OVERLAY
  const modalOverlay = document.getElementById('mobile-pilot-modal');
  const modalCloseBtn = document.getElementById('mobile-modal-close-btn');
  const openModalBtns = document.querySelectorAll('.mobile-open-modal-btn');
  
  openModalBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      if (modalOverlay) {
        modalOverlay.classList.add('active');
        if (drawerMenu) drawerMenu.classList.remove('open');
      }
    });
  });

  if (modalCloseBtn && modalOverlay) {
    modalCloseBtn.addEventListener('click', () => {
      modalOverlay.classList.remove('active');
    });

    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) {
        modalOverlay.classList.remove('active');
      }
    });
  }

  // 4. LEAD REQUEST ASYNC FORM SUBMISSION
  const mobileForm = document.getElementById('mobile-pilot-lead-form');
  if (mobileForm) {
    mobileForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const statusBox = document.getElementById('m_form_status_box');
      const submitBtn = document.getElementById('m_btn_submit_pilot');
      if (!statusBox || !submitBtn) return;

      statusBox.className = 'mobile-form-status';
      statusBox.style.display = 'none';

      const payload = {
        full_name: document.getElementById('m_full_name')?.value?.trim(),
        pharmacy_name: document.getElementById('m_pharmacy_name')?.value?.trim(),
        city: document.getElementById('m_city')?.value?.trim(),
        phone: document.getElementById('m_phone')?.value?.trim(),
        current_billing_method: document.getElementById('m_current_billing_method')?.value,
        bills_per_day: document.getElementById('m_bills_per_day')?.value,
        num_pharmacies: document.getElementById('m_num_pharmacies')?.value,
        biggest_problem: ''
      };

      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting...';

      try {
        const response = await fetch('/api/v1/leads/pilot-request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Submission failed');

        statusBox.className = 'mobile-form-status success';
        statusBox.style.display = 'block';
        statusBox.textContent = 'Request Received! We will get in touch on WhatsApp soon.';
        mobileForm.reset();
        
        // Autoclose modal after successful request
        setTimeout(() => {
          modalOverlay?.classList.remove('active');
        }, 2200);
      } catch (err) {
        statusBox.className = 'mobile-form-status error';
        statusBox.style.display = 'block';
        statusBox.textContent = err.message || 'Error submitting request. Please try again.';
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Join the Pilot →';
      }
    });
  }
});
