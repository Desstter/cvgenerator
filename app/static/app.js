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

let selectedFile = null;
let downloadFilename = null;

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
  adaptBtn.disabled = !(selectedFile && jobDesc.value.trim());
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
  if (!selectedFile || !jobDesc.value.trim()) return;

  errorMsg.style.display = 'none';
  showProgress('Uploading and parsing your CV...');
  adaptBtn.disabled = true;

  const formData = new FormData();
  formData.append('file', selectedFile);
  formData.append('job_description', jobDesc.value.trim());
  formData.append('template', templateSelect.value);
  formData.append('provider_name', providerSelect.value);

  try {
    const steps = [
      'Analyzing CV structure...',
      'Parsing job description...',
      'Adapting CV with AI...',
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
  } catch (err) {
    hideProgress();
    showError(err.message || 'An error occurred. Please try again.');
  } finally {
    adaptBtn.disabled = false;
    updateButton();
  }
});

function showResults(result) {
  resultsSection.style.display = 'block';

  const score = result.ats_score.overall_score;
  scoreValue.textContent = score.toFixed(0) + '%';
  scoreValue.className = 'score-value ' +
    (score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low');

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
