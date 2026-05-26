/* app.js — all interactive behavior for the inspectable UI */

// ── Panel toggle ───────────────────────────────────────────────────────────
function togglePanel(bodyId) {
  const body = document.getElementById(bodyId);
  const hint = document.getElementById(bodyId + '-hint');
  if (!body) return;
  const isHidden = body.classList.contains('hidden');
  body.classList.toggle('hidden', !isHidden);
  if (hint) hint.textContent = isHidden ? '▲ hide' : '▼ show';
}

// Auto-expand first panel that has failures so it's immediately visible
document.addEventListener('DOMContentLoaded', function () {
  // On stock detail pages: if gates-body contains failures, expand it
  const gatesBody = document.getElementById('gates-body');
  if (gatesBody) {
    const hasFail = gatesBody.querySelector('.gate-fail-icon');
    if (hasFail) {
      togglePanel('gates-body');
    }
  }

  // Open score-body by default on stock detail
  const scoreBody = document.getElementById('score-body');
  if (scoreBody) togglePanel('score-body');

  // Open global uncertainty flags by default on dashboard if they exist
  const flagsBody = document.getElementById('flags-body');
  if (flagsBody) togglePanel('flags-body');

  // Open limitations panel on benchmark page
  const limitBody = document.getElementById('limitations-body');
  if (limitBody) togglePanel('limitations-body');

  // Highlight active timeline node on replay page
  const slider = document.getElementById('snapshot-slider');
  if (slider) {
    showSnapshot(parseInt(slider.value));
  }
});


// ── Dashboard sort ─────────────────────────────────────────────────────────
function sortTable(sortKey) {
  const tbody = document.getElementById('rankings-body');
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll('tr.stock-row'));

  const decisionOrder = { BUY: 0, WATCH: 1, AVOID: 2 };

  rows.sort(function (a, b) {
    if (sortKey === 'score') {
      return parseFloat(b.dataset.score) - parseFloat(a.dataset.score);
    }
    if (sortKey === 'confidence') {
      return parseFloat(b.dataset.confidence) - parseFloat(a.dataset.confidence);
    }
    if (sortKey === 'decision') {
      const dA = decisionOrder[a.dataset.decision] ?? 9;
      const dB = decisionOrder[b.dataset.decision] ?? 9;
      if (dA !== dB) return dA - dB;
      return parseFloat(b.dataset.score) - parseFloat(a.dataset.score);
    }
    if (sortKey === 'ticker') {
      return a.dataset.ticker.localeCompare(b.dataset.ticker);
    }
    return 0;
  });

  // Re-insert and renumber
  rows.forEach(function (row, idx) {
    row.querySelector('.rank-num').textContent = idx + 1;
    tbody.appendChild(row);
  });
}


// ── Historical replay slider ────────────────────────────────────────────────
function showSnapshot(idx) {
  if (typeof SNAPSHOT_COUNT === 'undefined') return;

  idx = Math.max(0, Math.min(idx, SNAPSHOT_COUNT - 1));

  // Hide all, show active
  for (let i = 0; i < SNAPSHOT_COUNT; i++) {
    const card = document.getElementById('snapshot-' + i);
    if (card) card.classList.toggle('hidden', i !== idx);
  }

  // Sync slider
  const slider = document.getElementById('snapshot-slider');
  if (slider) slider.value = idx;

  // Sync date label
  const dateLabel = document.getElementById('slider-date-label');
  const activeCard = document.getElementById('snapshot-' + idx);
  if (dateLabel && activeCard) {
    const dateEl = activeCard.querySelector('.snapshot-date');
    if (dateEl) dateLabel.textContent = dateEl.textContent.trim();
  }

  // Highlight timeline node
  document.querySelectorAll('.timeline-node').forEach(function (node, i) {
    node.style.outline = i === idx ? '2px solid #0077BB' : '';
    node.style.background = i === idx ? '#E3F0FF' : '';
  });
}


// ── Clipboard copy for reasoning trace ────────────────────────────────────
function copyTrace(ticker) {
  const traces = window._traces || {};
  const trace = traces[ticker];
  if (!trace) return;

  const text = trace.map(function (step, i) {
    return (i + 1) + '. ' + step;
  }).join('\n');

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () {
      showCopyFeedback('Trace copied to clipboard');
    }).catch(function () {
      fallbackCopy(text);
    });
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const el = document.createElement('textarea');
  el.value = text;
  el.style.position = 'fixed';
  el.style.opacity = '0';
  document.body.appendChild(el);
  el.select();
  try { document.execCommand('copy'); showCopyFeedback('Trace copied'); }
  catch (e) { showCopyFeedback('Copy failed — select text manually'); }
  document.body.removeChild(el);
}

function showCopyFeedback(msg) {
  const btn = document.querySelector('.copy-btn');
  if (!btn) return;
  const original = btn.textContent;
  btn.textContent = msg;
  btn.style.background = '#E8F5E9';
  setTimeout(function () {
    btn.textContent = original;
    btn.style.background = '';
  }, 2000);
}


// ── Keyboard shortcuts ─────────────────────────────────────────────────────
document.addEventListener('keydown', function (e) {
  // Replay page: left/right arrow to step through snapshots
  if (typeof SNAPSHOT_COUNT === 'undefined') return;
  const slider = document.getElementById('snapshot-slider');
  if (!slider) return;
  if (e.key === 'ArrowLeft')  showSnapshot(parseInt(slider.value) - 1);
  if (e.key === 'ArrowRight') showSnapshot(parseInt(slider.value) + 1);
});
