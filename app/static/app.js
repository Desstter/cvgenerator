const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const filenameEl = document.getElementById('filename');
const jobDesc = document.getElementById('job-desc');
const adaptBtn = document.getElementById('adapt-btn');
const templateSelect = document.getElementById('template-select');
const providerSelect = document.getElementById('provider-select');
const progressSection = document.getElementById('progress-section');
const progressText = document.getElementById('progress-text');
const resultsSection = document.getElementById('results-section');
const errorMsg = document.getElementById('error-msg');
const scoreValue = document.getElementById('score-value');
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
  window.open('/api/base-cv?template=' + encodeURIComponent(tpl), '_blank');
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

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.style.display = 'block';
  setTimeout(() => { errorMsg.style.display = 'none'; }, 8000);
}

function showProgress(msg) {
  progressSection.style.display = 'block';
  resultsSection.style.display = 'none';
  progressText.textContent = msg;
}

function hideProgress() {
  progressSection.style.display = 'none';
}

// Adapt CV
adaptBtn.addEventListener('click', async () => {
  if (!jobDesc.value.trim()) return;
  if (useCustomCv.checked && !selectedFile) return;

  errorMsg.style.display = 'none';
  showProgress('Analyzing job description...');
  adaptBtn.disabled = true;

  const formData = new FormData();
  formData.append('job_description', jobDesc.value.trim());
  formData.append('template', templateSelect.value);
  formData.append('provider_name', providerSelect.value);

  if (useCustomCv.checked && selectedFile) {
    formData.append('file', selectedFile);
  }

  try {
    const steps = [
      'Analyzing job description...',
      'Adapting CV with AI...',
      'Swapping technologies to match role...',
      'Optimizing for ATS...',
      'Generating PDF...',
    ];
    let stepIdx = 0;
    const stepInterval = setInterval(() => {
      stepIdx++;
      if (stepIdx < steps.length) {
        progressText.textContent = steps[stepIdx];
      }
    }, 3000);

    const response = await fetch('/api/adapt', {
      method: 'POST',
      body: formData,
    });

    clearInterval(stepInterval);

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Server error');
    }

    const result = await response.json();
    hideProgress();
    showResults(result);
    loadHistory();
  } catch (err) {
    hideProgress();
    showError(err.message || 'An error occurred. Please try again.');
  } finally {
    adaptBtn.disabled = false;
    updateButton();
  }
});

function setBreakdownBar(fillId, pctId, score) {
  const fill = document.getElementById(fillId);
  const pct = document.getElementById(pctId);
  fill.style.width = score + '%';
  pct.textContent = score.toFixed(0) + '%';
  fill.style.background = score >= 70 ? 'var(--success)' : score >= 40 ? '#f57c00' : 'var(--danger)';
}

function showResults(result) {
  resultsSection.style.display = 'block';

  // Overall score
  const score = result.ats_score.overall_score;
  scoreValue.textContent = score.toFixed(0) + '%';
  scoreValue.className = 'score-value ' +
    (score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low');

  // ATS breakdown by category
  setBreakdownBar('req-fill', 'req-pct', result.ats_score.required_score || 0);
  setBreakdownBar('pref-fill', 'pref-pct', result.ats_score.preferred_score || 0);
  setBreakdownBar('gen-fill', 'gen-pct', result.ats_score.general_score || 0);

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
    row.innerHTML = `<span class="job-analysis-label">Role</span><span>${roleText}</span>`;
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
    const tags = (jobData.required_skills).map(s => `<span class="tag matched">${s}</span>`).join('');
    row.innerHTML = `<span class="job-analysis-label">Required</span><div class="keyword-tags" style="flex-wrap:wrap;gap:4px;">${tags}</div>`;
    jaContent.appendChild(row);
  }

  if ((jobData.preferred_skills || []).length) {
    const row = document.createElement('div');
    row.className = 'job-analysis-row';
    const tags = (jobData.preferred_skills).map(s => `<span class="tag" style="background:#fff3e0;color:#e65100;">${s}</span>`).join('');
    row.innerHTML = `<span class="job-analysis-label">Preferred</span><div class="keyword-tags" style="flex-wrap:wrap;gap:4px;">${tags}</div>`;
    jaContent.appendChild(row);
  }

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

    row.innerHTML = `
      <div class="history-meta">
        <span class="history-role">${escHtml(entry.job_title)}</span>
        <span class="history-company">${escHtml(entry.company)}</span>
      </div>
      <div class="history-right">
        <span class="history-date">${date}</span>
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
    const res = await fetch('/api/base-cv-data');
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
  const refs = { contact: {}, experience: [], education: [], summary: null, skills: null, languages: null, certifications: null };

  // Contact
  const contactSection = section('Contact');
  const cFields = [
    ['Name', 'name'], ['Email', 'email'], ['Phone', 'phone'],
    ['Location', 'location'], ['LinkedIn', 'linkedin'], ['Website', 'website'],
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

  // Summary
  const sumSection = section('Summary');
  const sumF = field('', cv.summary, { textarea: true, rows: 4 });
  refs.summary = sumF.input;
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
    hidden.innerHTML = '<span class="editor-hidden-note">Hidden — sent to AI for tech-swapping, never shown in the CV</span>';
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

  const payload = {
    cv: {
      contact: {
        name: refs.contact.name.value.trim(),
        email: refs.contact.email.value.trim(),
        phone: refs.contact.phone.value.trim(),
        location: refs.contact.location.value.trim(),
        linkedin: refs.contact.linkedin.value.trim(),
        website: refs.contact.website.value.trim(),
      },
      summary: refs.summary.value.trim(),
      experience,
      education: refs.education.map(r => ({
        institution: r.institution.value.trim(),
        degree: r.degree.value.trim(),
        dates: r.dates.value.trim(),
        details: r.details.value.trim(),
      })),
      projects: cvStore.cv.projects || [],
      skills: linesToList(refs.skills.value),
      certifications: linesToList(refs.certifications.value),
      languages: linesToList(refs.languages.value),
      detected_language: cvStore.cv.detected_language || 'es',
    },
    experience_context,
  };

  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving…';
  try {
    const res = await fetch('/api/base-cv-data', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to save CV');
    }
    cvStore = await res.json();
    showSuccess('CV saved.');
  } catch (err) {
    showError(err.message || 'Could not save your CV');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save CV';
  }
}

loadHistory();
