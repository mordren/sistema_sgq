/* SGQ CSV Cascavel – Main JS */

'use strict';

// ── Mobile sidebar toggle ───────────────────────────────────────────────────
(function () {
  const btn     = document.getElementById('sidebar-toggle');
  const sidebar = document.getElementById('sidebar');

  if (!btn || !sidebar) return;

  // Create overlay element dynamically
  let overlay = document.getElementById('sidebar-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'sidebar-overlay';
    document.body.appendChild(overlay);
  }

  function openSidebar () {
    sidebar.classList.add('show');
    overlay.classList.add('show');
  }

  function closeSidebar () {
    sidebar.classList.remove('show');
    overlay.classList.remove('show');
  }

  btn.addEventListener('click', function () {
    sidebar.classList.contains('show') ? closeSidebar() : openSidebar();
  });

  overlay.addEventListener('click', closeSidebar);
})();

// ── Auto-dismiss flash alerts after 5 s ────────────────────────────────────
(function () {
  const container = document.getElementById('flash-container');
  if (!container) return;

  const alerts = container.querySelectorAll('.alert');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });
})();

// ── Confirm dialogs for destructive actions ─────────────────────────────────
document.addEventListener('click', function (e) {
  const el = e.target.closest('[data-confirm]');
  if (!el) return;
  // Only intercept elements that actually have data-confirm; let Bootstrap
  // dismiss buttons (data-bs-dismiss) pass through unblocked.
  if (el.hasAttribute('data-bs-dismiss')) return;
  const msg = el.getAttribute('data-confirm');
  if (!confirm(msg)) {
    e.preventDefault();
    e.stopPropagation();
  }
});
// ── CSRF token helper (for fetch() calls) ──────────────────────────────────
function getCsrfToken () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

// ── Generic fetch-POST helper ──────────────────────────────────────────────
async function postJSON (url, data) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
    },
    body: JSON.stringify(data),
  });
  return response.json();
}
