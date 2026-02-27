/**
 * Remittance Reconciliation Tool — Client-side JS
 *
 * Minimal vanilla JS + Alpine.js component helpers.
 * No build step required.
 */

// ---------------------------------------------------------------------------
// Auto-dismiss alerts after 8 seconds
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.alert.alert-success, .alert.alert-info').forEach(function (el) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getInstance(el) || new bootstrap.Alert(el);
      bsAlert.close();
    }, 8000);
  });
});

// ---------------------------------------------------------------------------
// Confirm delete / destructive actions
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (!confirm(el.dataset.confirm)) {
        e.preventDefault();
      }
    });
  });
});

// ---------------------------------------------------------------------------
// Flash message helper (for AJAX responses)
// ---------------------------------------------------------------------------
function showFlash(message, type = 'success') {
  const container = document.querySelector('.container.mt-3');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `alert alert-${type} alert-dismissible fade show`;
  div.role = 'alert';
  div.innerHTML = message + '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
  container.prepend(div);
  setTimeout(() => {
    const bsAlert = bootstrap.Alert.getInstance(div) || new bootstrap.Alert(div);
    try { bsAlert.close(); } catch(e) {}
  }, 6000);
}

// ---------------------------------------------------------------------------
// AJAX confirm/reject helpers for review queue (used in queue.html via onclick)
// ---------------------------------------------------------------------------
async function confirmMatch(matchId) {
  const btn = event.currentTarget;
  btn.disabled = true;
  try {
    const resp = await fetch(`/queue/review/${matchId}/confirm`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
    });
    const data = await resp.json();
    if (data.ok) {
      btn.closest('.card').remove();
      showFlash('Match confirmed and saved.', 'success');
    } else {
      showFlash('Error: ' + (data.error || 'Unknown'), 'danger');
      btn.disabled = false;
    }
  } catch(e) {
    showFlash('Request failed: ' + e.message, 'danger');
    btn.disabled = false;
  }
}

async function rejectMatch(matchId) {
  const btn = event.currentTarget;
  btn.disabled = true;
  try {
    const resp = await fetch(`/queue/review/${matchId}/reject`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
    });
    const data = await resp.json();
    if (data.ok) {
      btn.closest('.card').remove();
      showFlash('Match rejected. Deposit returned to pending queue.', 'info');
    } else {
      showFlash('Error: ' + (data.error || 'Unknown'), 'danger');
      btn.disabled = false;
    }
  } catch(e) {
    showFlash('Request failed: ' + e.message, 'danger');
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Tier status indicator — refresh every 30s
// ---------------------------------------------------------------------------
(function() {
  // Nothing to poll for now; tier status set on batch run
})();
