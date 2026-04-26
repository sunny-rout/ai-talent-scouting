/ TalentScout AI — static/js/app.js
// Handles: SSE streaming, score explanation, candidate compare,
//          email drafting, interview questions, shortlist, architecture
// ============================================================

// ─── Utilities ───────────────────────────────────────────────

function showToast(msg, type = 'success') {
  const colours = { success: 'bg-green-600', error: 'bg-red-600', info: 'bg-blue-600' };
  const toast = document.createElement('div');
  toast.className = `fixed bottom-4 right-4 z-50 px-4 py-3 rounded-lg text-white text-sm shadow-lg ${colours[type] || colours.info} transition-opacity duration-500`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 500); }, 3000);
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) { el.classList.remove('hidden'); el.classList.add('flex'); }
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) { el.classList.add('hidden'); el.classList.remove('flex'); }
}

// Close modal on backdrop click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.closest('[id$="-modal"]')?.id && closeModal(e.target.closest('[id$="-modal"]').id);
  }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('[id$="-modal"]:not(.hidden)').forEach(m => closeModal(m.id));
  }
});


// ─── 1. SSE Streaming Conversation ───────────────────────────

function startStreaming(candidateId) {
  const box      = document.getElementById('conversation-box');
  const scoreBox = document.getElementById('interest-score-box');
  const btn      = document.getElementById('stream-btn');

  if (!box) return;

  box.innerHTML = '';
  if (btn) { btn.disabled = true; btn.textContent = 'Engaging…'; }

  const evtSource = new EventSource(`/stream-conversation/${candidateId}`);
  let buffer = '';

  evtSource.addEventListener('token', (e) => {
    buffer += e.data;
    box.innerHTML = buffer.replace(/\n/g, '<br>');
    box.scrollTop = box.scrollHeight;
  });

  evtSource.addEventListener('done', (e) => {
    evtSource.close();
    if (btn) { btn.disabled = false; btn.textContent = 'Re-run Conversation'; }
    try {
      const data = JSON.parse(e.data);
      renderInterestScore(data, scoreBox);
      renderShortlistButton(candidateId, data.interest_score);
    } catch (_) {}
  });

  evtSource.addEventListener('error', () => {
    evtSource.close();
    if (btn) { btn.disabled = false; btn.textContent = 'Retry'; }
    showToast('Streaming error — check server logs.', 'error');
  });
}


function renderInterestScore(data, container) {
  if (!container) return;
  const signals = [
    { label: 'Enthusiasm',        key: 'enthusiasm' },
    { label: 'Availability',      key: 'availability' },
    { label: 'Compensation Fit',  key: 'compensation_fit' },
    { label: 'Engagement Quality',key: 'engagement_quality' },
  ];
  const rows = signals.map(s => {
    const val = data[s.key] ?? 0;
    const pct = (val / 25) * 100;
    return `
      <div class="flex items-center gap-3 text-sm">
        <span class="w-40 text-gray-400">${s.label}</span>
        <div class="flex-1 bg-gray-700 rounded-full h-2">
          <div class="bg-indigo-500 h-2 rounded-full" style="width:${pct}%"></div>
        </div>
        <span class="w-8 text-right text-white font-semibold">${val}</span>
      </div>`;
  }).join('');

  const total = data.interest_score ?? 0;
  const colour = total >= 70 ? 'text-green-400' : total >= 45 ? 'text-yellow-400' : 'text-red-400';

  container.innerHTML = `
    <div class="space-y-3">
      ${rows}
      <div class="border-t border-gray-600 pt-3 flex justify-between items-center">
        <span class="font-semibold text-white">Interest Score</span>
        <span class="text-2xl font-bold ${colour}">${total}<span class="text-sm text-gray-400">/100</span></span>
      </div>
    </div>`;
  container.classList.remove('hidden');
}


function renderShortlistButton(candidateId, interestScore) {
  const wrap = document.getElementById('shortlist-action');
  if (!wrap) return;
  wrap.innerHTML = `
    <button onclick="addToShortlist('${candidateId}')"
      class="mt-4 w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 rounded-lg transition">
      ＋ Add to Shortlist (Interest ${interestScore})
    </button>`;
}


// ─── 2. Shortlist Add / Remove ────────────────────────────────

async function addToShortlist(candidateId) {
  const res = await fetch(`/shortlist/${candidateId}`, { method: 'POST' });
  if (res.ok) { showToast('Added to shortlist ✓'); }
  else        { showToast('Could not add — run conversation first.', 'error'); }
}

async function removeFromShortlist(candidateId) {
  const res = await fetch(`/shortlist/${candidateId}`, { method: 'DELETE' });
  if (res.ok) {
    showToast('Removed from shortlist');
    document.getElementById(`row-${candidateId}`)?.remove();
  } else {
    showToast('Remove failed.', 'error');
  }
}


// ─── 3. Score Explanation (D2) ────────────────────────────────

async function explainScore(candidateId, candidateName) {
  openModal('explain-modal');
  const body    = document.getElementById('explain-body');
  const title   = document.getElementById('explain-title');
  if (title) title.textContent = `Score Breakdown — ${candidateName}`;
  if (body)  body.innerHTML = '<p class="text-gray-400 animate-pulse">Generating explanation…</p>';

  try {
    const res  = await fetch('/explain-score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId }),
    });
    const data = await res.json();
    if (body) {
      const bullets = (data.explanation || 'No explanation returned.')
        .split('\n')
        .filter(l => l.trim())
        .map(l => `<li class="mb-2">${l.replace(/^[-•*]\s*/, '')}</li>`)
        .join('');
      body.innerHTML = `<ul class="list-disc list-inside space-y-1 text-gray-200 text-sm">${bullets}</ul>`;
    }
  } catch (err) {
    if (body) body.innerHTML = `<p class="text-red-400">Error: ${err.message}</p>`;
  }
}


// ─── 4. Candidate Compare (D1) ────────────────────────────────

const selectedForCompare = new Set();

function toggleCompare(candidateId, btn) {
  if (selectedForCompare.has(candidateId)) {
    selectedForCompare.delete(candidateId);
    btn.classList.remove('bg-indigo-600', 'text-white');
    btn.classList.add('bg-gray-700', 'text-gray-300');
    btn.textContent = 'Compare';
  } else {
    if (selectedForCompare.size >= 3) { showToast('Select up to 3 candidates.', 'info'); return; }
    selectedForCompare.add(candidateId);
    btn.classList.add('bg-indigo-600', 'text-white');
    btn.classList.remove('bg-gray-700', 'text-gray-300');
    btn.textContent = 'Selected ✓';
  }

  const compareBar = document.getElementById('compare-bar');
  if (compareBar) {
    compareBar.classList.toggle('hidden', selectedForCompare.size < 2);
    const countEl = document.getElementById('compare-count');
    if (countEl) countEl.textContent = selectedForCompare.size;
  }
}


async function runCompare() {
  if (selectedForCompare.size < 2) { showToast('Select at least 2 candidates.', 'info'); return; }
  openModal('compare-modal');
  const body = document.getElementById('compare-body');
  if (body) body.innerHTML = '<p class="text-gray-400 animate-pulse col-span-3">Loading comparison…</p>';

  const ids = Array.from(selectedForCompare);
  try {
    const res  = await fetch('/compare-candidates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_ids: ids }),
    });
    const data = await res.json();   // expects { candidates: [...] }
    if (body) body.innerHTML = buildCompareTable(data.candidates);
  } catch (err) {
    if (body) body.innerHTML = `<p class="text-red-400 col-span-3">Error: ${err.message}</p>`;
  }
}


function buildCompareTable(candidates) {
  const dims = [
    { label: 'Match Score',      key: 'match_score' },
    { label: 'Required Skills',  key: 'required_score' },
    { label: 'Experience',       key: 'experience_score' },
    { label: 'Preferred Skills', key: 'preferred_score' },
    { label: 'Role Fit',         key: 'role_fit_score' },
    { label: 'Education',        key: 'education_score' },
    { label: 'Interest Score',   key: 'interest_score' },
  ];

  const headers = candidates.map(c =>
    `<th class="px-4 py-2 text-indigo-300 font-semibold text-center">${c.name}</th>`
  ).join('');

  const rows = dims.map(dim => {
    const vals  = candidates.map(c => c[dim.key] ?? 0);
    const maxVal = Math.max(...vals);
    const cells = candidates.map((c, i) => {
      const v   = vals[i];
      const hi  = v === maxVal ? 'bg-indigo-900/40 font-bold text-white' : 'text-gray-300';
      return `<td class="px-4 py-2 text-center ${hi}">${v}</td>`;
    }).join('');
    return `<tr class="border-t border-gray-700">
              <td class="px-4 py-2 text-gray-400 text-sm">${dim.label}</td>
              ${cells}
            </tr>`;
  }).join('');

  return `
    <table class="w-full text-sm">
      <thead>
        <tr>
          <th class="px-4 py-2 text-left text-gray-500">Dimension</th>
          ${headers}
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}


// ─── 5. Email Drafting ────────────────────────────────────────

async function draftEmail(candidateId, candidateName) {
  openModal('email-modal');
  const body  = document.getElementById('email-body');
  const title = document.getElementById('email-title');
  if (title) title.textContent = `Outreach Email — ${candidateName}`;
  if (body)  body.innerHTML = '<p class="text-gray-400 animate-pulse">Drafting personalised email…</p>';

  try {
    const res  = await fetch(`/generate/email/${candidateId}`, { method: 'POST' });
    const data = await res.json();
    if (body) {
      const text = data.email || 'No email generated.';
      body.innerHTML = `<pre class="whitespace-pre-wrap text-gray-200 text-sm font-sans leading-relaxed">${text}</pre>
        <button onclick="copyEmail()" class="mt-4 text-xs text-indigo-400 hover:text-indigo-300 underline">
          Copy to clipboard
        </button>`;
      body.dataset.email = text;
    }
  } catch (err) {
    if (body) body.innerHTML = `<p class="text-red-400">Error: ${err.message}</p>`;
  }
}

function copyEmail() {
  const body = document.getElementById('email-body');
  if (!body) return;
  navigator.clipboard.writeText(body.dataset.email || '').then(() => showToast('Copied!'));
}


// ─── 6. Interview Questions ───────────────────────────────────

async function draftQuestions(candidateId, candidateName) {
  openModal('questions-modal');
  const body  = document.getElementById('questions-body');
  const title = document.getElementById('questions-title');
  if (title) title.textContent = `Interview Questions — ${candidateName}`;
  if (body)  body.innerHTML = '<p class="text-gray-400 animate-pulse">Generating questions…</p>';

  try {
    const res  = await fetch(`/generate/questions/${candidateId}`, { method: 'POST' });
    const data = await res.json();
    if (body) {
      const lines = (data.questions || 'No questions generated.')
        .split('\n')
        .filter(l => l.trim())
        .map((l, i) => `<li class="mb-2"><span class="text-indigo-400 font-semibold">${i + 1}.</span> ${l.replace(/^\d+\.\s*/, '')}</li>`)
        .join('');
      body.innerHTML = `<ol class="space-y-2 text-gray-200 text-sm list-none">${lines}</ol>`;
    }
  } catch (err) {
    if (body) body.innerHTML = `<p class="text-red-400">Error: ${err.message}</p>`;
  }
}


// ─── 7. Architecture Animation ───────────────────────────────

function animateArchitecture() {
  const nodes = document.querySelectorAll('[data-arch-node]');
  if (!nodes.length) return;

  nodes.forEach(n => n.classList.remove('ring-2', 'ring-indigo-400', 'opacity-100'));
  nodes.forEach(n => n.classList.add('opacity-30'));

  nodes.forEach((node, i) => {
    setTimeout(() => {
      nodes.forEach(n => n.classList.remove('ring-2', 'ring-indigo-400'));
      node.classList.remove('opacity-30');
      node.classList.add('opacity-100', 'ring-2', 'ring-indigo-400');
      if (i === nodes.length - 1) {
        setTimeout(() => node.classList.remove('ring-2', 'ring-indigo-400'), 800);
      }
    }, i * 700);
  });
}


// ─── 8. CSV Export ────────────────────────────────────────────

function exportCSV() {
  window.location.href = '/export-csv';
  showToast('Downloading shortlist CSV…', 'info');
}


// ─── 9. JD Parse — loading state ────────────────────────────

function handleParseSubmit(btn) {
  const jd = document.getElementById('jd-input')?.value.trim();
  if (!jd) { showToast('Paste a Job Description first.', 'error'); return false; }
  btn.disabled    = true;
  btn.textContent = 'Parsing…';
  btn.closest('form')?.submit();
  return true;
}


// ─── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Wire close buttons on all modals
  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal));
  });

  // Auto-start streaming if on engagement page
  const candidateIdEl = document.getElementById('candidate-id');
  const autoStart     = document.getElementById('auto-start-stream');
  if (candidateIdEl && autoStart) {
    startStreaming(candidateIdEl.value);
  }

  // Architecture animate button
  document.getElementById('animate-btn')
    ?.addEventListener('click', animateArchitecture);

  // Export CSV button
  document.getElementById('export-csv-btn')
    ?.addEventListener('click', exportCSV);
});