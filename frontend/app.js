/**
 * Convertly UI Logic Handler
 * Handles state, polling, file drops, and DOM updates securely.
 */

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

// --- Intersection Observer for Scroll Reveals ---
function initScrollAnimations() {
  const reveals = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('active');
        observer.unobserve(entry.target); 
      }
    });
  }, { threshold: 0.05, rootMargin: "0px 0px 0px 0px" });

  reveals.forEach(reveal => observer.observe(reveal));
  
  // Safety fallback: Force reveal everything after 1 second just in case
  setTimeout(() => {
    reveals.forEach(reveal => reveal.classList.add('active'));
  }, 1000);
}

// Bulletproof initialization check
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScrollAnimations);
} else {
  initScrollAnimations();
}

// --- Core Helper Functions ---
function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function addMessage(text, role) {
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${role}`;
  
  // Icon for System/Assistant, Text for User
  const avatarContent = role === 'system' 
    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>`
    : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`;
  
  messageDiv.innerHTML = `
    <div class="msg-avatar">${avatarContent}</div>
    <div class="msg-content">${text}</div>
  `;
  
  history.appendChild(messageDiv);
  history.scrollTo({ top: history.scrollHeight, behavior: 'smooth' });
}

// --- Status Panel Logic ---
function updatePanel(job) {
  panel.hidden = false;
  panel.classList.toggle('failed', job.status === 'failed');
  
  const value = Math.max(0, Math.min(100, Number(job.progress) || 0));
  progressBar.style.width = `${value}%`;
  percent.textContent = `${value}%`;
  detail.textContent = job.message;
  
  if (job.status === 'complete') {
    label.textContent = 'Artifact Generated';
    label.style.color = 'var(--accent-success)';
  } else if (job.status === 'failed') {
    label.textContent = 'Process Halted';
    label.style.color = 'var(--accent-danger)';
  } else {
    label.textContent = 'Processing Directive...';
    label.style.color = 'var(--accent-blue)';
  }

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
      if (!response.ok) throw new Error(job.detail || 'Telemetry linkage failed.');
      
      updatePanel(job);
      
      if (job.status === 'complete') { 
        addMessage('Conversion successful. The artifact is secured and ready for download in the panel.', 'system'); 
        return; 
      }
      if (job.status === 'failed') { 
        addMessage(`Conversion halted: ${job.message}`, 'system'); 
        return; 
      }
    } catch (error) {
      updatePanel({ status: 'failed', progress: 0, message: error.message });
      return;
    }
    await new Promise(resolve => window.setTimeout(resolve, 800));
  }
}

// --- Upload Pipeline ---
async function uploadFile(file) {
  if (!file) return;
  
  // Basic frontend validation to prevent accidental massive uploads
  if (file.size > 100 * 1024 * 1024) {
    addMessage(`File size (${formatBytes(file.size)}) exceeds local memory bounds (100MB limit).`, 'system');
    return;
  }

  activeJob = null;
  panel.hidden = true;
  
  const fileSize = formatBytes(file.size);
  fileStatus.textContent = `Establishing secure link... (${fileSize})`;
  fileStatus.style.color = 'var(--accent-blue)';
  fileStatus.style.borderColor = 'rgba(59, 130, 246, 0.3)';
  fileStatus.style.background = 'rgba(59, 130, 246, 0.1)';
  
  const body = new FormData();
  body.append('file', file);
  
  try {
    const response = await fetch('/upload', { method: 'POST', body });
    const data = await response.json();
    
    if (!response.ok) throw new Error(data.detail || 'Upload protocol rejected.');
    
    uploadedFilename = data.filename;
    fileStatus.textContent = `Payload Secured: ${data.original_name}`;
    fileStatus.style.color = 'var(--accent-success)';
    fileStatus.style.borderColor = 'rgba(16, 185, 129, 0.3)';
    fileStatus.style.background = 'rgba(16, 185, 129, 0.1)';
    
    addMessage(`File payload "${data.original_name}" cached securely in memory. Awaiting conversion directive.`, 'system');
    input.focus();
  } catch (error) {
    uploadedFilename = null;
    fileStatus.textContent = 'Transfer interrupted. Please retry.';
    fileStatus.style.color = 'var(--accent-danger)';
    fileStatus.style.borderColor = 'rgba(239, 68, 68, 0.3)';
    fileStatus.style.background = 'rgba(239, 68, 68, 0.1)';
    
    addMessage(error.message, 'system');
  }
}

// --- Event Listeners: Drag & Drop ---
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', event => { 
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    fileInput.click(); 
  }
});

fileInput.addEventListener('change', event => uploadFile(event.target.files[0]));

['dragenter', 'dragover'].forEach(type => {
  dropZone.addEventListener(type, event => { 
    event.preventDefault(); 
    dropZone.classList.add('dragging'); 
  });
});

['dragleave', 'drop'].forEach(type => {
  dropZone.addEventListener(type, event => { 
    event.preventDefault(); 
    dropZone.classList.remove('dragging'); 
  });
});

dropZone.addEventListener('drop', event => {
  if (event.dataTransfer.files.length) {
    uploadFile(event.dataTransfer.files[0]);
  }
});

// --- Event Listeners: Terminal Chat ---
form.addEventListener('submit', async event => {
  event.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;
  
  if (!uploadedFilename) { 
    addMessage('Action denied: No file payload detected in memory. Initialize transfer first.', 'system'); 
    return; 
  }
  
  addMessage(prompt, 'user');
  input.value = '';
  sendButton.disabled = true;
  
  // Synthetic thinking indicator
  addMessage('Parsing neural intent...', 'system');
  const tempMsg = history.lastElementChild;
  tempMsg.style.opacity = '0.5';
  
  try {
    const response = await fetch('/chat', { 
      method: 'POST', 
      headers: { 'Content-Type': 'application/json' }, 
      body: JSON.stringify({ prompt, filename: uploadedFilename }) 
    });
    
    const data = await response.json();
    
    if(tempMsg && tempMsg.parentNode) { tempMsg.parentNode.removeChild(tempMsg); }
    if (!response.ok) throw new Error(data.detail || 'Critical error in syntax parser.');
    
    addMessage(data.message, 'system');
    
    if (data.job_id) {
      panel.hidden = false;
      updatePanel({ status: 'queued', progress: 5, message: 'Initialization command authorized.' });
      watchJob(data.job_id);
    }
  } catch (error) { 
    if(tempMsg && tempMsg.parentNode) { tempMsg.parentNode.removeChild(tempMsg); }
    addMessage(error.message, 'system'); 
  } finally { 
    sendButton.disabled = false; 
    input.focus(); 
  }
});