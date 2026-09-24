const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const filenameEl = document.getElementById('filename');
const jobDesc = document.getElementById('job-desc');
const adaptBtn = document.getElementById('adapt-btn');
const templateSelect = document.getElementById('template-select');
const providerSelect = document.getElementById('provider-select');
const profileSelect = document.getElementById('profile-select');
const opportunitySelect = document.getElementById('opportunity-select');
const opportunityMeta = document.getElementById('opportunity-meta');
const opportunityFit = document.getElementById('opportunity-fit');
const opportunityLink = document.getElementById('opportunity-link');
const progressSection = document.getElementById('progress-section');
const progressText = document.getElementById('progress-text');
const progressElapsed = document.getElementById('progress-elapsed');
const resultsSection = document.getElementById('results-section');
const errorMsg = document.getElementById('error-msg');
const errorMsgText = document.getElementById('error-msg-text');
const errorTrace = document.getElementById('error-trace');
const errorTracePre = document.getElementById('error-trace-pre');
const errorClose = document.getElementById('error-close');
const scoreValue = document.getElementById('score-value');
const scoreValueBefore = document.getElementById('score-value-before');
const scoreDelta = document.getElementById('score-delta');
const matchedKeywords = document.getElementById('matched-keywords');
const missingKeywords = document.getElementById('missing-keywords');
const suggestionsBox = document.getElementById('suggestions-box');
const suggestionsList = document.getElementById('suggestions-list');
const downloadBtn = document.getElementById('download-btn');
const useCustomCv = document.getElementById('use-custom-cv');
const uploadSection = document.getElementById('upload-section');

const baseCvBtn = document.getElementById('base-cv-btn');

// Download base CV (uses the currently selected template)
baseCvBtn.addEventListener('click', () => {
  const tpl = templateSelect.value === 'original' ? 'modern' : templateSelect.value;
  const params = new URLSearchParams({ profile: profileSelect.value, template: tpl });
  window.open('/api/base-cv?' + params.toString(), '_blank');
});

profileSelect.addEventListener('change', async () => {
  const isBpo = profileSelect.value === 'bilingual_customer_service';
  templateSelect.value = isBpo ? 'bilingual' : 'technical';
  templateSelect.disabled = isBpo;
  baseCvBtn.textContent = isBpo ? 'Download Bilingual CV' : 'Download PDF';
  jobDesc.placeholder = isBpo
    ? 'Paste a bilingual customer-service, technical-support, or BPO job description...'
    : 'Paste the full job description here (from LinkedIn, Indeed, etc.)...';
  editorLoaded = false;
  cvStore = null;
  if (cvEditor.style.display !== 'none') await loadCvStore();
  await loadOpportunities();
});

let opportunityCatalog = [];

async function loadOpportunities() {
  opportunitySelect.disabled = true;
  opportunitySelect.innerHTML = '<option value="">Loading verified opportunities…</option>';
  opportunityMeta.style.display = 'none';
  try {
    const response = await fetch('/api/opportunities?profile=' + encodeURIComponent(profileSelect.value));
    if (!response.ok) throw new Error('Could not load the real-job catalog');
    opportunityCatalog = await response.json();
    opportunitySelect.innerHTML = '<option value="">Choose a verified opportunity…</option>';
    opportunityCatalog.forEach(item => {
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = `${item.title} — ${item.company} (${item.location})`;
      opportunitySelect.appendChild(option);
    });
  } catch (error) {
    opportunityCatalog = [];
    opportunitySelect.innerHTML = '<option value="">Catalog unavailable</option>';
  } finally {
    opportunitySelect.disabled = false;
  }
}

opportunitySelect.addEventListener('change', () => {
  const selected = opportunityCatalog.find(item => item.id === opportunitySelect.value);
  if (!selected) {
    opportunityMeta.style.display = 'none';
    return;
  }
  jobDesc.value = selected.job_description;
  const status = selected.status === 'active' ? 'Active when checked' : selected.status;
  opportunityFit.textContent = `${status} · Checked ${selected.checked_at} · ${selected.fit_note}`;
  opportunityLink.href = selected.source_url;
  opportunityMeta.style.display = 'block';
  updateButton();
});

let selectedFile = null;
let downloadFilename = null;

// Toggle custom CV upload and "Original Layout" template option
useCustomCv.addEventListener('change', () => {
  uploadSection.style.display = useCustomCv.checked ? 'block' : 'none';

  // Add/remove "Original Layout" option based on whether a custom CV is being used
  const hasOriginal = Array.from(templateSelect.options).some(o => o.value === 'original');
  if (useCustomCv.checked && !hasOriginal) {
    const opt = document.createElement('option');
    opt.value = 'original';
    opt.textContent = 'Original Layout';
    templateSelect.appendChild(opt);
  } else if (!useCustomCv.checked) {
    if (hasOriginal) {
      const idx = Array.from(templateSelect.options).findIndex(o => o.value === 'original');
      templateSelect.remove(idx);
    }
    selectedFile = null;
    filenameEl.textContent = '';
    if (templateSelect.value === 'original') templateSelect.value = 'modern';
  }

  updateButton();
});

// Drop zone
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('drag-over');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const files = e.dataTransfer.files;
  if (files.length && files[0].type === 'application/pdf') {
    selectFile(files[0]);
  }
});

fileInput.addEventListener('change', () => {
  if (fileInput.files.length) {
    selectFile(fileInput.files[0]);
  }
});

function selectFile(file) {
  selectedFile = file;
  filenameEl.textContent = file.name;
  updateButton();
}

function updateButton() {
  const hasJob = jobDesc.value.trim().length > 0;
  if (useCustomCv.checked) {
    adaptBtn.disabled = !(selectedFile && hasJob);
  } else {
    adaptBtn.disabled = !hasJob;
  }
}

jobDesc.addEventListener('input', updateButton);

let errorHideTimer = null;

// msg: string. detail: optional traceback string shown in an expandable block.
// Errors with a traceback stay on screen until dismissed.
function showError(msg, detail) {
  clearTimeout(errorHideTimer);
  errorMsgText.textContent = msg;
  if (detail) {
    errorTracePre.textContent = detail;
    errorTrace.style.display = 'block';
    errorTrace.open = false;
  } else {
    errorTrace.style.display = 'none';
    errorHideTimer = setTimeout(hideError, 10000);
  }
  errorMsg.style.display = 'block';
  errorMsg.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideError() {
  errorMsg.style.display = 'none';
}

errorClose.addEventListener('click', hideError);

// Normalize a failed fetch Response into {message, traceback}
async function parseApiError(response) {
  let message = `HTTP ${response.status} ${response.statusText}`;
  let traceback = '';
  try {
    const err = await response.json();
    const d = err.detail;
    if (typeof d === 'string') message = d;
    else if (d && typeof d === 'object') {
      message = d.message || message;
      traceback = d.traceback || '';
    }
  } catch (_) { /* non-JSON body */ }
  return { message, traceback };
}

let progressTimer = null;

function showProgress(msg) {
  progressSection.style.display = 'block';
  resultsSection.style.display = 'none';
  progressText.textContent = msg;
  progressElapsed.textContent = '';
  const started = performance.now();
  clearInterval(progressTimer);
  progressTimer = setInterval(() => {
    progressElapsed.textContent = ((performance.now() - started) / 1000).toFixed(1) + 's elapsed';
  }, 250);
}

function hideProgress() {
  progressSection.style.display = 'none';
  clearInterval(progressTimer);
  progressTimer = null;
}

// ── Activity console ─────────────────────────────────────────────────────────
// Live mirror of everything the backend does: API calls, retries, model
// fallbacks, JSON repairs, and errors with full tracebacks.

const consoleBody = document.getElementById('console-body');
const consoleOutput = document.getElementById('console-output');
const consoleToggleBtn = document.getElementById('console-toggle-btn');
const consoleClearBtn = document.getElementById('console-clear-btn');
const consoleBadge = document.getElementById('console-badge');
const consoleHeader = document.getElementById('console-header');

let lastSeq = 0;
let consoleErrorCount = 0;
let adapting = false;
let pollTimer = null;
let pollInFlight = false;

function setConsoleOpen(open) {
  consoleBody.style.display = open ? 'block' : 'none';
  consoleToggleBtn.textContent = open ? 'Hide' : 'Show';
}

function consoleIsOpen() {
  return consoleBody.style.display !== 'none';
}

consoleToggleBtn.addEventListener('click', () => setConsoleOpen(!consoleIsOpen()));
consoleHeader.addEventListener('click', (e) => {
  if (e.target.closest('button')) return;
  setConsoleOpen(!consoleIsOpen());
});

consoleClearBtn.addEventListener('click', async () => {
  try { await fetch('/api/events', { method: 'DELETE' }); } catch (_) {}
  consoleOutput.innerHTML = '';
  consoleErrorCount = 0;
  consoleBadge.style.display = 'none';
});

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toTimeString().slice(0, 8) + '.' + String(d.getMilliseconds()).padStart(3, '0');
}

function renderEvent(evt) {
  const line = document.createElement('div');
  line.className = 'console-line lvl-' + evt.level;

  const time = document.createElement('span');
  time.className = 'console-time';
  time.textContent = fmtTime(evt.ts);

  const stage = document.createElement('span');
  stage.className = 'console-stage';
  stage.textContent = evt.stage;

  const msg = document.createElement('span');
  msg.className = 'console-msg';
  msg.textContent = evt.message;

  line.append(time, stage, msg);

  if (evt.detail) {
    const det = document.createElement('details');
    det.className = 'console-detail';
    const sum = document.createElement('summary');
    sum.textContent = 'traceback / detail';
    const pre = document.createElement('pre');
    pre.textContent = evt.detail;
    det.append(sum, pre);
    line.appendChild(det);
  }

  consoleOutput.appendChild(line);

  if (evt.level === 'error') {
    consoleErrorCount++;
    consoleBadge.textContent = consoleErrorCount + (consoleErrorCount === 1 ? ' error' : ' errors');
    consoleBadge.style.display = 'inline-block';
  }
}

let pollFailStreak = 0;

// Surface polling problems IN the console instead of failing silently —
// one line per failure streak, not one per poll.
function notePollProblem(msg) {
  pollFailStreak++;
  if (pollFailStreak !== 1) return;
  renderEvent({
    seq: 0,
    ts: Date.now() / 1000,
    level: 'error',
    stage: 'frontend',
    message: msg,
    detail: '',
  });
  consoleOutput.scrollTop = consoleOutput.scrollHeight;
}

async function pollEvents() {
  if (pollInFlight) return;
  pollInFlight = true;
  try {
    const res = await fetch('/api/events?since=' + lastSeq);
    if (!res.ok) {
      notePollProblem(
        `/api/events responded HTTP ${res.status} — the running server predates this feature. ` +
        'Restart it: python -m uvicorn app.main:app --reload'
      );
      return;
    }
    pollFailStreak = 0;
    const events = await res.json();
    if (!events.length) return;

    const atBottom = consoleOutput.scrollHeight - consoleOutput.scrollTop - consoleOutput.clientHeight < 40;
    events.forEach(renderEvent);
    lastSeq = events[events.length - 1].seq;

    // Trim very old lines so the DOM stays light
    while (consoleOutput.childElementCount > 1500) consoleOutput.firstElementChild.remove();
    if (atBottom) consoleOutput.scrollTop = consoleOutput.scrollHeight;

    // Live progress: mirror the latest backend event while adapting
    if (adapting) {
      const last = events[events.length - 1];
      progressText.textContent = last.message;
    }
  } catch (e) {
    notePollProblem('Cannot reach the server for live events: ' + e.message);
  } finally {
    pollInFlight = false;
    schedulePoll();
  }
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(pollEvents, adapting ? 500 : 2500);
}

// Adapt CV
adaptBtn.addEventListener('click', async () => {
  if (!jobDesc.value.trim()) return;
  if (useCustomCv.checked && !selectedFile) return;

  hideError();
  showProgress('Contacting server…');
  adaptBtn.disabled = true;
  adaptBtn.textContent = 'Generating…';
  adapting = true;
  setConsoleOpen(true);
  clearTimeout(pollTimer);
  pollEvents();

  const formData = new FormData();
  formData.append('job_description', jobDesc.value.trim());
  formData.append('template', templateSelect.value);
  formData.append('provider_name', providerSelect.value);
  formData.append('profile_id', profileSelect.value);

  if (useCustomCv.checked && selectedFile) {
    formData.append('file', selectedFile);
  }

  try {
    const response = await fetch('/api/adapt', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const { message, traceback } = await parseApiError(response);
      const e = new Error(message);
      e.traceback = traceback;
      throw e;
    }

    const result = await response.json();
    hideProgress();
    showResults(result);
    loadHistory();
  } catch (err) {
    hideProgress();
    showError(err.message || 'An error occurred. Please try again.', err.traceback || '');
  } finally {
    adapting = false;
    adaptBtn.disabled = false;
    adaptBtn.textContent = 'Generate Adapted CV';
    updateButton();
    // One last poll so the final events (or the error) land in the console
    clearTimeout(pollTimer);
    setTimeout(pollEvents, 300);
  }
});

function setBreakdownBar(fillId, beforeFillId, pctId, scoreAfter, scoreBefore) {
  const fill = document.getElementById(fillId);
  const fillBefore = document.getElementById(beforeFillId);
  const pct = document.getElementById(pctId);
  fill.style.width = scoreAfter + '%';
  if (fillBefore) fillBefore.style.width = scoreBefore + '%';
  pct.textContent = scoreAfter.toFixed(0) + '%';
  fill.style.background = scoreAfter >= 70 ? 'var(--success)' : scoreAfter >= 40 ? '#f57c00' : 'var(--danger)';
}

function setOverallScore(scoreAfter, scoreBefore) {
  scoreValue.textContent = scoreAfter.toFixed(0) + '%';
  scoreValue.className = 'score-value ' +
    (scoreAfter >= 70 ? 'high' : scoreAfter >= 40 ? 'medium' : 'low');

  scoreValueBefore.textContent = scoreBefore.toFixed(0) + '%';

  const delta = scoreAfter - scoreBefore;
  const rounded = Math.round(delta);
  if (rounded > 0) {
    scoreDelta.textContent = '+' + rounded;
    scoreDelta.className = 'score-delta';
  } else if (rounded < 0) {
    scoreDelta.textContent = String(rounded);
    scoreDelta.className = 'score-delta negative';
  } else {
    scoreDelta.textContent = '±0';
    scoreDelta.className = 'score-delta neutral';
  }
}

function showResults(result) {
  resultsSection.style.display = 'block';

  // Overall score — before vs after
  const after = result.ats_score || {};
  const before = result.original_ats_score || {};
  setOverallScore(after.overall_score || 0, before.overall_score || 0);

  // ATS breakdown by category (before bar behind, after bar in front)
  setBreakdownBar('req-fill', 'req-fill-before', 'req-pct',
    after.required_score || 0, before.required_score || 0);
  setBreakdownBar('pref-fill', 'pref-fill-before', 'pref-pct',
    after.preferred_score || 0, before.preferred_score || 0);
  setBreakdownBar('gen-fill', 'gen-fill-before', 'gen-pct',
    after.general_score || 0, before.general_score || 0);

  // Matched keywords
  matchedKeywords.innerHTML = '';
  (result.ats_score.matched_keywords || []).forEach(kw => {
    const tag = document.createElement('span');
    tag.className = 'tag matched';
    tag.textContent = kw;
    matchedKeywords.appendChild(tag);
  });

  // Missing keywords
  missingKeywords.innerHTML = '';
  (result.ats_score.missing_keywords || []).forEach(kw => {
    const tag = document.createElement('span');
    tag.className = 'tag missing';
    tag.textContent = kw;
    missingKeywords.appendChild(tag);
  });

  // Tech swaps
  const swapSection = document.getElementById('tech-swaps-section');
  const swapTags = document.getElementById('swap-tags');
  const swaps = result.tech_swaps || [];
  swapTags.innerHTML = '';
  if (swaps.length) {
    swapSection.style.display = 'block';
    swaps.forEach(swap => {
      const tag = document.createElement('span');
      tag.className = 'tag swap';
      tag.textContent = swap;
      swapTags.appendChild(tag);
    });
  } else {
    swapSection.style.display = 'none';
  }

  // What changed
  const changesSection = document.getElementById('changes-section');
  const changesList = document.getElementById('changes-list');
  changesList.innerHTML = '';
  const changes = [];

  const orig = result.original_cv;
  const adapted = result.adapted_cv;

  if (orig.summary !== adapted.summary && adapted.summary) {
    changes.push('Summary updated');
  }

  (orig.experience || []).forEach((origExp, i) => {
    const newExp = (adapted.experience || [])[i];
    if (!newExp) return;
    const diffs = [];
    if (origExp.title !== newExp.title) diffs.push('title');
    if (origExp.description !== newExp.description) diffs.push('description');
    if (JSON.stringify(origExp.technologies) !== JSON.stringify(newExp.technologies)) diffs.push('technologies');
    if (diffs.length) {
      changes.push(`${origExp.company}: ${diffs.join(', ')} adapted`);
    }
  });

  if (changes.length) {
    changesSection.style.display = 'block';
    changes.forEach(c => {
      const li = document.createElement('li');
      li.textContent = c;
      changesList.appendChild(li);
    });
  } else {
    changesSection.style.display = 'none';
  }

  // Job analysis panel
  const jaContent = document.getElementById('job-analysis-content');
  jaContent.innerHTML = '';
  const jobData = result.job_analysis || {};

  if (jobData.title || jobData.company) {
    const row = document.createElement('div');
    row.className = 'job-analysis-row';
    const roleText = [jobData.title, jobData.company].filter(Boolean).join(' at ');
    row.innerHTML = `<span class="job-analysis-label">Role</span><span>${escHtml(roleText)}</span>`;
    jaContent.appendChild(row);
  }

  if (jobData.detected_language) {
    const row = document.createElement('div');
    row.className = 'job-analysis-row';
    row.innerHTML = `<span class="job-analysis-label">Language</span><span>${jobData.detected_language === 'es' ? 'Spanish' : 'English'}</span>`;
    jaContent.appendChild(row);
  }

  if ((jobData.required_skills || []).length) {
    const row = document.createElement('div');
    row.className = 'job-analysis-row';
    const tags = (jobData.required_skills).map(s => `<span class="tag matched">${escHtml(s)}</span>`).join('');
    row.innerHTML = `<span class="job-analysis-label">Required</span><div class="keyword-tags" style="flex-wrap:wrap;gap:4px;">${tags}</div>`;
    jaContent.appendChild(row);
  }

  if ((jobData.preferred_skills || []).length) {
    const row = document.createElement('div');
    row.className = 'job-analysis-row';
    const tags = (jobData.preferred_skills).map(s => `<span class="tag" style="background:#fff3e0;color:#e65100;">${escHtml(s)}</span>`).join('');
    row.innerHTML = `<span class="job-analysis-label">Preferred</span><div class="keyword-tags" style="flex-wrap:wrap;gap:4px;">${tags}</div>`;
    jaContent.appendChild(row);
  }

  // Deterministic truth/claim audit for the BPO profile
  const claimSection = document.getElementById('claim-review-section');
  const claimContent = document.getElementById('claim-review-content');
  claimContent.innerHTML = '';
  const review = result.claim_review || {};
  if (result.profile_id === 'bilingual_customer_service') {
    claimSection.style.display = 'block';
    const status = document.createElement('p');
    status.className = review.status === 'passed' ? 'claim-pass' : 'claim-blocked';
    status.textContent = review.status === 'passed'
      ? 'Passed: no unsupported BPO claims were detected.'
      : 'Blocked: unsupported claims require correction.';
    claimContent.appendChild(status);
    [...(review.notes || []), ...(review.transferable_strengths || []).map(s => 'Verified strength: ' + s)]
      .forEach(note => {
        const item = document.createElement('div');
        item.className = 'claim-note';
        item.textContent = '✓ ' + note;
        claimContent.appendChild(item);
      });
  } else {
    claimSection.style.display = 'none';
  }

  // Human-readable content review before the PDF download action
  const contentReview = document.getElementById('content-review-content');
  document.getElementById('content-review-section').open = result.profile_id === 'bilingual_customer_service';
  contentReview.innerHTML = '';
  const summaryTitle = document.createElement('h4');
  summaryTitle.textContent = adapted.headline || 'Professional Summary';
  const summaryText = document.createElement('p');
  summaryText.textContent = adapted.summary || '';
  contentReview.append(summaryTitle, summaryText);
  (adapted.experience || []).forEach(exp => {
    const title = document.createElement('h4');
    title.textContent = `${exp.title} | ${exp.company}`;
    const list = document.createElement('ul');
    (exp.description || '').split('\n').filter(Boolean).forEach(line => {
      const item = document.createElement('li');
      item.textContent = line.replace(/^[•*\-]\s*/, '');
      list.appendChild(item);
    });
    contentReview.append(title, list);
  });

  // Suggestions
  const suggestions = result.ats_score.suggestions || [];
  if (suggestions.length) {
    suggestionsBox.style.display = 'block';
    suggestionsList.innerHTML = '';
    suggestions.forEach(s => {
      const li = document.createElement('li');
      li.textContent = s;
      suggestionsList.appendChild(li);
    });
  } else {
    suggestionsBox.style.display = 'none';
  }

  // Download
  downloadFilename = result.pdf_filename;
  downloadBtn.onclick = () => {
    window.open('/api/download/' + encodeURIComponent(downloadFilename), '_blank');
  };

  resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// ── History ──────────────────────────────────────────────────────────────────

const historyCard = document.getElementById('history-card');
const historyList = document.getElementById('history-list');
const clearHistoryBtn = document.getElementById('clear-history-btn');

async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    if (!res.ok) return;
    const entries = await res.json();
    renderHistory(entries);
  } catch (_) {}
}

function renderHistory(entries) {
  if (!entries || entries.length === 0) {
    historyCard.style.display = 'none';
    return;
  }
  historyCard.style.display = 'block';
  historyList.innerHTML = '';
  entries.forEach(entry => {
    const row = document.createElement('div');
    row.className = 'history-row';
    row.dataset.id = entry.id;

    const score = entry.ats_score;
    const scoreClass = score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low';
    const date = new Date(entry.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const lang = entry.detected_language === 'es' ? 'ES' : 'EN';
    const profileLabel = entry.profile_id === 'bilingual_customer_service' ? 'BPO' : 'DEV';

    row.innerHTML = `
      <div class="history-meta">
        <span class="history-role">${escHtml(entry.job_title)}</span>
        <span class="history-company">${escHtml(entry.company)}</span>
      </div>
      <div class="history-right">
        <span class="history-date">${date}</span>
        <span class="history-lang">${profileLabel}</span>
        <span class="history-lang">${lang}</span>
        <span class="score-badge ${scoreClass}">${score.toFixed(0)}%</span>
        <button class="btn-ghost history-dl" data-filename="${escHtml(entry.pdf_filename)}">PDF</button>
        <button class="btn-ghost history-del" data-id="${entry.id}" title="Delete">✕</button>
      </div>`;
    historyList.appendChild(row);
  });

  historyList.querySelectorAll('.history-dl').forEach(btn => {
    btn.addEventListener('click', () => {
      window.open('/api/download/' + encodeURIComponent(btn.dataset.filename), '_blank');
    });
  });

  historyList.querySelectorAll('.history-del').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch('/api/history/' + btn.dataset.id, { method: 'DELETE' });
      btn.closest('.history-row').remove();
      if (!historyList.querySelector('.history-row')) {
        historyCard.style.display = 'none';
      }
    });
  });
}

clearHistoryBtn.addEventListener('click', async () => {
  const entries = historyList.querySelectorAll('.history-row');
  await Promise.all(Array.from(entries).map(row =>
    fetch('/api/history/' + row.dataset.id, { method: 'DELETE' })
  ));
  historyCard.style.display = 'none';
  historyList.innerHTML = '';
});

function escHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── My CV editor ───────────────────────────────────────────────────────────

const editCvBtn = document.getElementById('edit-cv-btn');
const cvEditor = document.getElementById('cv-editor');
const successMsg = document.getElementById('success-msg');

let cvStore = null;
let editorLoaded = false;

function showSuccess(msg) {
  successMsg.textContent = msg;
  successMsg.style.display = 'block';
  setTimeout(() => { successMsg.style.display = 'none'; }, 4000);
}

editCvBtn.addEventListener('click', async () => {
  const open = cvEditor.style.display === 'none';
  cvEditor.style.display = open ? 'block' : 'none';
  editCvBtn.textContent = open ? 'Close' : 'Edit';
  if (open && !editorLoaded) {
    await loadCvStore();
  }
});

async function loadCvStore() {
  cvEditor.innerHTML = '<p class="editor-loading">Loading…</p>';
  try {
    const res = await fetch('/api/base-cv-data?profile=' + encodeURIComponent(profileSelect.value));
    if (!res.ok) throw new Error('Failed to load CV');
    cvStore = await res.json();
    editorLoaded = true;
    renderEditor();
  } catch (err) {
    cvEditor.innerHTML = '';
    showError(err.message || 'Could not load your CV');
  }
}

function field(label, value, opts = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'editor-field';
  const lbl = document.createElement('label');
  lbl.textContent = label;
  wrap.appendChild(lbl);
  const input = opts.textarea ? document.createElement('textarea') : document.createElement('input');
  input.value = value || '';
  if (opts.textarea) input.rows = opts.rows || 3;
  if (opts.placeholder) input.placeholder = opts.placeholder;
  input.dataset.key = opts.key || '';
  wrap.appendChild(input);
  return { wrap, input };
}

function linesToList(str) {
  return str.split('\n').map(s => s.trim()).filter(Boolean);
}

function renderEditor() {
  cvEditor.innerHTML = '';
  const cv = cvStore.cv;
  const refs = { contact: {}, experience: [], education: [], headline: null, summary: null, skills: null, languages: null, certifications: null };

  // Contact
  const contactSection = section('Contact');
  const cFields = [
    ['Name', 'name'], ['Email', 'email'], ['Phone', 'phone'],
    ['Location', 'location'], ['LinkedIn', 'linkedin'], ['Website', 'website'], ['GitHub', 'github'],
  ];
  const cGrid = document.createElement('div');
  cGrid.className = 'editor-grid';
  cFields.forEach(([label, key]) => {
    const f = field(label, cv.contact[key]);
    refs.contact[key] = f.input;
    cGrid.appendChild(f.wrap);
  });
  contactSection.appendChild(cGrid);
  cvEditor.appendChild(contactSection);

  // Headline and summary
  const sumSection = section('Summary');
  const headlineF = field('Headline', cv.headline || '');
  const sumF = field('', cv.summary, { textarea: true, rows: 4 });
  refs.headline = headlineF.input;
  refs.summary = sumF.input;
  sumSection.appendChild(headlineF.wrap);
  sumSection.appendChild(sumF.wrap);
  cvEditor.appendChild(sumSection);

  // Experience
  const expSection = section('Experience');
  (cv.experience || []).forEach((exp) => {
    const ctx = (cvStore.experience_context || {})[exp.company] || { real_technologies: [], real_achievements: [] };
    const block = document.createElement('div');
    block.className = 'editor-entry';

    const grid = document.createElement('div');
    grid.className = 'editor-grid';
    const fCompany = field('Company', exp.company);
    const fTitle = field('Title', exp.title);
    const fDates = field('Dates', exp.dates);
    const fLoc = field('Location', exp.location);
    [fCompany, fTitle, fDates, fLoc].forEach(f => grid.appendChild(f.wrap));
    block.appendChild(grid);

    const fDesc = field('Description (one bullet per line)', (exp.description || '').split('\n').map(l => l.replace(/^•\s*/, '')).join('\n'), { textarea: true, rows: 4 });
    block.appendChild(fDesc.wrap);

    const fTech = field('Technologies (shown in CV, one per line)', (exp.technologies || []).join('\n'), { textarea: true, rows: 3 });
    block.appendChild(fTech.wrap);

    const hidden = document.createElement('div');
    hidden.className = 'editor-hidden-context';
    hidden.innerHTML = cvStore.profile_type === 'bpo'
      ? '<span class="editor-hidden-note">Hidden — verified evidence sent to AI, never printed in the CV</span>'
      : '<span class="editor-hidden-note">Hidden — verified evidence used for truthful rewriting, never printed verbatim</span>';
    const fRealTech = field('Real technologies (one per line)', (ctx.real_technologies || []).join('\n'), { textarea: true, rows: 3 });
    const fRealAch = field('Real achievements (one per line)', (ctx.real_achievements || []).join('\n'), { textarea: true, rows: 4 });
    hidden.appendChild(fRealTech.wrap);
    hidden.appendChild(fRealAch.wrap);
    block.appendChild(hidden);

    refs.experience.push({
      company: fCompany.input, title: fTitle.input, dates: fDates.input,
      location: fLoc.input, description: fDesc.input, technologies: fTech.input,
      real_technologies: fRealTech.input, real_achievements: fRealAch.input,
    });
    expSection.appendChild(block);
  });
  cvEditor.appendChild(expSection);

  // Education
  const eduSection = section('Education');
  (cv.education || []).forEach((edu) => {
    const block = document.createElement('div');
    block.className = 'editor-entry';
    const grid = document.createElement('div');
    grid.className = 'editor-grid';
    const fInst = field('Institution', edu.institution);
    const fDeg = field('Degree', edu.degree);
    const fDates = field('Dates', edu.dates);
    [fInst, fDeg, fDates].forEach(f => grid.appendChild(f.wrap));
    block.appendChild(grid);
    const fDet = field('Details', edu.details);
    block.appendChild(fDet.wrap);
    refs.education.push({ institution: fInst.input, degree: fDeg.input, dates: fDates.input, details: fDet.input });
    eduSection.appendChild(block);
  });
  cvEditor.appendChild(eduSection);

  // Skills / languages / certifications
  const listsSection = section('Skills & Languages');
  const fSkills = field('Skills (one per line)', (cv.skills || []).join('\n'), { textarea: true, rows: 5 });
  const fLangs = field('Languages (one per line)', (cv.languages || []).join('\n'), { textarea: true, rows: 2 });
  const fCerts = field('Certifications (one per line)', (cv.certifications || []).join('\n'), { textarea: true, rows: 2 });
  refs.skills = fSkills.input;
  refs.languages = fLangs.input;
  refs.certifications = fCerts.input;
  listsSection.appendChild(fSkills.wrap);
  listsSection.appendChild(fLangs.wrap);
  listsSection.appendChild(fCerts.wrap);
  cvEditor.appendChild(listsSection);

  // Save bar
  const saveBar = document.createElement('div');
  saveBar.className = 'editor-savebar';
  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn';
  saveBtn.textContent = 'Save CV';
  saveBtn.addEventListener('click', () => saveCvStore(refs, saveBtn));
  saveBar.appendChild(saveBtn);
  cvEditor.appendChild(saveBar);
}

function section(title) {
  const sec = document.createElement('div');
  sec.className = 'editor-section';
  const h = document.createElement('h3');
  h.textContent = title;
  sec.appendChild(h);
  return sec;
}

async function saveCvStore(refs, saveBtn) {
  const experience_context = {};
  const experience = refs.experience.map(r => {
    const company = r.company.value.trim();
    if (company) {
      experience_context[company] = {
        real_technologies: linesToList(r.real_technologies.value),
        real_achievements: linesToList(r.real_achievements.value),
      };
    }
    return {
      company,
      title: r.title.value.trim(),
      dates: r.dates.value.trim(),
      location: r.location.value.trim(),
      description: linesToList(r.description.value).map(l => '• ' + l).join('\n'),
      technologies: linesToList(r.technologies.value),
    };
  });

  const selectedSkills = linesToList(refs.skills.value);
  const selectedSkillSet = new Set(selectedSkills);
  const skill_categories = (cvStore.cv.skill_categories || [])
    .map(category => ({
      name: category.name,
      skills: (category.skills || []).filter(skill => selectedSkillSet.has(skill)),
    }))
    .filter(category => category.skills.length > 0);
  const categorized = new Set(skill_categories.flatMap(category => category.skills));
  const uncategorized = selectedSkills.filter(skill => !categorized.has(skill));
  if (uncategorized.length) {
    skill_categories.push({ name: 'Other', skills: uncategorized });
  }

  const payload = {
    profile_id: cvStore.profile_id || profileSelect.value,
    display_name: cvStore.display_name || '',
    profile_type: cvStore.profile_type || 'developer',
    cv: {
      contact: {
        name: refs.contact.name.value.trim(),
        email: refs.contact.email.value.trim(),
        phone: refs.contact.phone.value.trim(),
        location: refs.contact.location.value.trim(),
        linkedin: refs.contact.linkedin.value.trim(),
        website: refs.contact.website.value.trim(),
        github: refs.contact.github.value.trim(),
      },
      headline: refs.headline.value.trim(),
      summary: refs.summary.value.trim(),
      experience,
      education: refs.education.map(r => ({
        institution: r.institution.value.trim(),
        degree: r.degree.value.trim(),
        dates: r.dates.value.trim(),
        details: r.details.value.trim(),
      })),
      projects: cvStore.cv.projects || [],
      skills: selectedSkills,
      skill_categories,
      certifications: linesToList(refs.certifications.value),
      languages: linesToList(refs.languages.value),
      detected_language: cvStore.cv.detected_language || 'es',
    },
    experience_context,
  };

  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving…';
  try {
    const res = await fetch('/api/base-cv-data?profile=' + encodeURIComponent(profileSelect.value), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const { message, traceback } = await parseApiError(res);
      const e = new Error(message || 'Failed to save CV');
      e.traceback = traceback;
      throw e;
    }
    cvStore = await res.json();
    showSuccess('CV saved.');
  } catch (err) {
    showError(err.message || 'Could not save your CV', err.traceback || '');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save CV';
  }
}

loadHistory();
loadOpportunities();
pollEvents();
