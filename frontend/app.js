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

// --- UI Enhancements: Scroll Reveal ---
function initScrollAnimations() {
  const reveals = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('active');
        observer.unobserve(entry.target); // Only animate once
      }
    });
  }, { threshold: 0.1, rootMargin: "0px 0px -50px 0px" });

  reveals.forEach(reveal => observer.observe(reveal));
}
document.addEventListener('DOMContentLoaded', initScrollAnimations);


// --- Core Logic ---
function addMessage(text, role) {
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${role}`;
  
  // Format based on role for the new luxury UI
  const avatarText = role === 'assistant' ? 'C' : 'U';
  
  messageDiv.innerHTML = `
    <div class="avatar">${avatarText}</div>
    <div class="bubble">${text}</div>
  `;
  
  history.appendChild(messageDiv);
  
  // Smooth scroll to bottom
  history.scrollTo({
    top: history.scrollHeight,
    behavior: 'smooth'
  });
}

function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function updatePanel(job) {
  panel.hidden = false;
  panel.classList.toggle('failed', job.status === 'failed');
  
  const value = Math.max(0, Math.min(100, Number(job.progress) || 0));
  progressBar.style.width = `${value}%`;
  percent.textContent = `${value}%`;
  detail.textContent = job.message;
  
  if (job.status === 'complete') {
    label.textContent = 'Artifact Generated';
    label.classList.add('gradient-text');
  } else if (job.status === 'failed') {
    label.textContent = 'Process Failed';
    label.classList.remove('gradient-text');
  } else {
    label.textContent = 'Processing Directive...';
    label.classList.add('gradient-text');
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
      if (!response.ok) throw new Error(job.detail || 'Could not establish telemetry with local processor.');
      
      updatePanel(job);
      
      if (job.status === 'complete') { 
        addMessage('Conversion successful. The artifact is ready for immediate download below.', 'assistant'); 
        return; 
      }
      if (job.status === 'failed') { 
        addMessage(`Conversion halted: ${job.message}`, 'assistant'); 
        return; 
      }
    } catch (error) {
      updatePanel({ status: 'failed', progress: 0, message: error.message });
      return;
    }
    await new Promise(resolve => window.setTimeout(resolve, 800)); // Polling delay
  }
}

async function uploadFile(file) {
  if (!file) return;
  activeJob = null;
  panel.hidden = true;
  
  const fileSize = formatBytes(file.size);
  fileStatus.textContent = `Establishing secure link... (${fileSize})`;
  fileStatus.style.borderColor = 'var(--accent-secondary)';
  fileStatus.style.color = 'var(--accent-secondary)';
  
  const body = new FormData();
  body.append('file', file);
  
  try {
    const response = await fetch('/upload', { method: 'POST', body });
    const data = await response.json();
    
    if (!response.ok) throw new Error(data.detail || 'Upload protocol failed.');
    
    uploadedFilename = data.filename;
    fileStatus.textContent = `Payload Secured: ${data.original_name}`;
    fileStatus.style.borderColor = 'var(--accent-success)';
    fileStatus.style.color = 'var(--accent-success)';
    fileStatus.style.background = 'rgba(0, 230, 118, 0.1)';
    
    addMessage(`File payload "${data.original_name}" secured in local memory. Input your conversion directive.`, 'assistant');
    input.focus();
  } catch (error) {
    uploadedFilename = null;
    fileStatus.textContent = 'Transfer interrupted. Please retry.';
    fileStatus.style.borderColor = 'var(--accent-error)';
    fileStatus.style.color = 'var(--accent-error)';
    fileStatus.style.background = 'rgba(255, 59, 48, 0.1)';
    
    addMessage(error.message, 'assistant');
  }
}

// Event Listeners for File Drag/Drop
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

// Event Listener for Chat Submit
form.addEventListener('submit', async event => {
  event.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;
  
  if (!uploadedFilename) { 
    addMessage('Action denied: No file payload detected. Please upload a file first.', 'assistant'); 
    return; 
  }
  
  addMessage(prompt, 'user');
  input.value = '';
  sendButton.disabled = true;
  
  // Show thinking indicator (optional, simple text implementation)
  addMessage('Parsing neural intent...', 'assistant');
  const tempMsg = history.lastElementChild;
  tempMsg.style.opacity = '0.5';
  
  try {
    const response = await fetch('/chat', { 
      method: 'POST', 
      headers: { 'Content-Type': 'application/json' }, 
      body: JSON.stringify({ prompt, filename: uploadedFilename }) 
    });
    
    const data = await response.json();
    
    // Remove thinking message
    if(tempMsg && tempMsg.parentNode) { tempMsg.parentNode.removeChild(tempMsg); }
    
    if (!response.ok) throw new Error(data.detail || 'Critical error in logic parser.');
    
    addMessage(data.message, 'assistant');
    
    if (data.job_id) {
      panel.hidden = false;
      updatePanel({ status: 'queued', progress: 5, message: 'Initialization command received.' });
      watchJob(data.job_id);
    }
  } catch (error) { 
    if(tempMsg && tempMsg.parentNode) { tempMsg.parentNode.removeChild(tempMsg); }
    addMessage(error.message, 'assistant'); 
  } finally { 
    sendButton.disabled = false; 
    input.focus(); 
  }
});