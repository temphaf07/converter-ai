const fileInput = document.querySelector('#file-input');
const dropZone = document.querySelector('#drop-zone');
const fileStatus = document.querySelector('#file-status');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#chat-input');
const history = document.querySelector('#chat-history');
const sendButton = document.querySelector('#send-button');
const panel = document.querySelector('#conversion-panel');
const label = document.querySelector('#conversion-label');
const percent = document.querySelector('#conversion-percent');
const progressBar = document.querySelector('#progress-bar');
const detail = document.querySelector('#conversion-detail');
const downloadButton = document.querySelector('#download-button');
let uploadedFilename = null;
let activeJob = null;

function addMessage(text, role) {
  const message = document.createElement('div');
  message.className = `message ${role}`;
  message.textContent = text;
  history.appendChild(message);
  history.scrollTop = history.scrollHeight;
}

function updatePanel(job) {
  panel.hidden = false;
  panel.classList.toggle('failed', job.status === 'failed');
  const value = Math.max(0, Math.min(100, Number(job.progress) || 0));
  progressBar.style.width = `${value}%`;
  percent.textContent = `${value}%`;
  detail.textContent = job.message;
  label.textContent = job.status === 'complete' ? 'Your file is ready' : job.status === 'failed' ? 'Conversion failed' : 'Converting file';
  if (job.status === 'complete' && job.download_url) {
    downloadButton.href = job.download_url;
    downloadButton.hidden = false;
  }
}

async function watchJob(jobId) {
  activeJob = jobId;
  downloadButton.hidden = true;
  while (activeJob === jobId) {
    try {
      const response = await fetch(`/jobs/${jobId}`);
      const job = await response.json();
      if (!response.ok) throw new Error(job.detail || 'Could not read conversion status.');
      updatePanel(job);
      if (job.status === 'complete') { addMessage('Your conversion is complete. Use the download button below the chat.', 'assistant'); return; }
      if (job.status === 'failed') { addMessage(job.message, 'assistant'); return; }
    } catch (error) {
      updatePanel({ status: 'failed', progress: 0, message: error.message });
      return;
    }
    await new Promise(resolve => window.setTimeout(resolve, 700));
  }
}

async function uploadFile(file) {
  if (!file) return;
  activeJob = null;
  panel.hidden = true;
  fileStatus.textContent = `Uploading ${file.name}...`;
  const body = new FormData();
  body.append('file', file);
  try {
    const response = await fetch('/upload', { method: 'POST', body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Upload failed.');
    uploadedFilename = data.filename;
    fileStatus.textContent = `Ready: ${data.original_name}`;
    addMessage(`I have ${data.original_name}. What should I turn it into?`, 'assistant');
    input.focus();
  } catch (error) {
    uploadedFilename = null;
    fileStatus.textContent = 'Upload failed - try again';
    addMessage(error.message, 'assistant');
  }
}

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') fileInput.click(); });
fileInput.addEventListener('change', event => uploadFile(event.target.files[0]));
['dragenter', 'dragover'].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach(type => dropZone.addEventListener(type, event => { event.preventDefault(); dropZone.classList.remove('dragging'); }));
dropZone.addEventListener('drop', event => uploadFile(event.dataTransfer.files[0]));

form.addEventListener('submit', async event => {
  event.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;
  if (!uploadedFilename) { addMessage('Please upload a file first.', 'assistant'); return; }
  addMessage(prompt, 'user');
  input.value = '';
  sendButton.disabled = true;
  try {
    const response = await fetch('/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt, filename: uploadedFilename }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Something went wrong.');
    addMessage(data.message, 'assistant');
    if (data.job_id) {
      panel.hidden = false;
      updatePanel({ status: 'queued', progress: 0, message: 'Conversion queued' });
      watchJob(data.job_id);
    }
  } catch (error) { addMessage(error.message, 'assistant'); }
  finally { sendButton.disabled = false; input.focus(); }
});
