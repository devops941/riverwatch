/**
 * RiverWatch 2026 Core Frontend Script
 * CLEAN, NEAT & MODERN LIGHT THEME: Bio-Emerald, Amethyst Purple, Warm Amber, Coral Rose.
 * Handles database status checking (MongoDB via .env / SQLite),
 * universal quick data upload modal, toast notifications, and crisp Plotly styling.
 */

const RiverWatch = {
  apiBase: '/api',

  // Initialize all global components
  init() {
    this.initTheme();
    this.highlightNav();
    this.initDbStatus();
    this.initQuickUploadModal();
  },

  // Pure Light Theme System
  initTheme() {
    document.documentElement.setAttribute('data-theme', 'light');
    localStorage.setItem('riverwatch_theme', 'light');
  },

  isDark() {
    return false; // Strict light theme
  },

  // Active Navbar Item
  highlightNav() {
    const currentPath = window.location.pathname.split('/').pop() || 'index.html';
    document.querySelectorAll('.nav-links .nav-item').forEach(item => {
      const link = item.querySelector('a');
      if (link) {
        if (link.getAttribute('href') === 'upload.html') {
          link.setAttribute('href', 'riverupload.html');
        }
        if (link.getAttribute('href') === currentPath) {
          item.classList.add('active');
        } else {
          item.classList.remove('active');
        }
      }
    });
  },

  // Central API Client
  async api(endpoint, options = {}) {
    try {
      const res = await fetch(`${this.apiBase}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
        ...options,
      });

      if (!res.ok) {
        let errDetail = 'Request failed';
        try {
          const errData = await res.json();
          errDetail = errData.detail || errData.message || JSON.stringify(errData);
        } catch (_) {
          errDetail = `HTTP ${res.status}: ${res.statusText}`;
        }
        throw new Error(errDetail);
      }

      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await res.json();
      }
      return res;
    } catch (err) {
      this.toast(err.message, 'error');
      throw err;
    }
  },

  // Database Connection Status Checker (MongoDB via .env vs SQLite)
  async initDbStatus() {
    try {
      const res = await fetch('/api/database/status');
      if (!res.ok) return;
      const data = await res.json();

      const footer = document.querySelector('.sidebar-footer');
      if (!footer) return;

      let pill = document.getElementById('dbStatusPill');
      if (!pill) {
        pill = document.createElement('div');
        pill.id = 'dbStatusPill';
        pill.className = 'db-status-pill';
        footer.insertBefore(pill, footer.firstChild);
      }

      const isMongo = data.mongodb_connected;
      const configured = data.configured_type === 'mongodb';

      if (isMongo) {
        pill.innerHTML = `
          <span style="font-size: 14px;">🍃</span>
          <div>
            <div style="font-size: 11.5px; font-weight: 800; color: #047857;">MongoDB Active</div>
            <div style="font-size: 10px; color: var(--text-muted);">${data.mongodb_database} (.env)</div>
          </div>
        `;
        pill.title = `MongoDB connected via .env at ${data.mongodb_uri} (Database: ${data.mongodb_database})`;
      } else {
        pill.innerHTML = `
          <span style="font-size: 14px;">📦</span>
          <div>
            <div style="font-size: 11.5px; font-weight: 800; color: #b45309;">SQLite Storage</div>
            <div style="font-size: 10px; color: var(--text-muted);">${configured ? 'Local engine active' : 'Local file'}</div>
          </div>
        `;
        pill.title = `Using high-speed SQLite local storage. Configured in .env: ${data.configured_type.toUpperCase()}`;
      }
    } catch (e) {
      // Ignore background status errors
    }
  },

  // Universal Quick Upload Modal
  initQuickUploadModal() {
    if (document.getElementById('quickUploadModal')) return;

    const modal = document.createElement('div');
    modal.id = 'quickUploadModal';
    modal.className = 'modal-backdrop';
    modal.style.display = 'none';

    modal.innerHTML = `
      <div class="modal-card">
        <div class="modal-header">
          <div style="display: flex; align-items: center; gap: 10px;">
            <div class="modal-icon-badge" style="background: #ecfdf5; color: #059669;">📤</div>
            <div>
              <h2 style="font-size: 17px; font-weight: 800; color: #0f172a;">Data Ingestion Options</h2>
              <p style="font-size: 12px; color: #64748b; margin-top: 2px;">Enter single measurements or upload CSV/Excel files</p>
            </div>
          </div>
          <button type="button" class="modal-close-btn" onclick="RiverWatch.closeUploadModal()">✕</button>
        </div>

        <div class="modal-body">
          <!-- Choice 1: Direct Entry Form -->
          <a href="entry.html" style="display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; text-decoration: none; margin-bottom: 14px; transition: all 0.2s ease;">
            <div style="display: flex; align-items: center; gap: 12px;">
              <span style="font-size: 22px;">📝</span>
              <div>
                <strong style="color: #047857; font-size: 13.5px; display: block;">Manual Data Entry Form</strong>
                <span style="color: #64748b; font-size: 11.5px;">Type in field samples with instant live WQI calculation</span>
              </div>
            </div>
            <span style="color: #059669; font-weight: 700; font-size: 16px;">→</span>
          </a>

          <!-- Choice 2: Bulk File Dropzone -->
          <div id="modalDropzone" class="upload-dropzone" style="padding: 24px 20px;">
            <div style="font-size: 32px; margin-bottom: 6px; color: #059669;">📁</div>
            <div style="font-weight: 700; font-size: 13.5px; margin-bottom: 4px; color: #0f172a;">Bulk CSV or Excel Upload</div>
            <div style="font-size: 12px; color: #64748b; margin-bottom: 12px;">Supports CPCB, State PCB, and lab monitoring sheets</div>
            <input type="file" id="modalFileInput" accept=".csv, .xlsx, .xls" style="display: none;">
            <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('modalFileInput').click()">Browse Computer Files</button>
            <div id="modalFileName" style="margin-top: 10px; font-size: 12px; font-weight: 700; color: #059669;"></div>
          </div>

          <div style="margin-top: 16px; display: flex; justify-content: space-between; align-items: center;">
            <a href="riverupload.html" style="font-size: 12px; color: #7c3aed; text-decoration: none; font-weight: 600;">Full Validation Studio →</a>
            <button type="button" id="modalUploadSubmitBtn" class="btn btn-primary btn-sm" disabled>⚡ Ingest & Validate File</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const fileInput = document.getElementById('modalFileInput');
    const submitBtn = document.getElementById('modalUploadSubmitBtn');
    const fileNameDiv = document.getElementById('modalFileName');

    let selectedFile = null;

    fileInput?.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        selectedFile = e.target.files[0];
        fileNameDiv.innerText = `Selected: ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`;
        submitBtn.disabled = false;
      }
    });

    submitBtn?.addEventListener('click', async () => {
      if (!selectedFile) return;
      submitBtn.disabled = true;
      submitBtn.innerText = '⏳ Ingesting...';
      const formData = new FormData();
      formData.append('file', selectedFile);

      try {
        const res = await fetch('/api/upload', {
          method: 'POST',
          body: formData,
        });
        const result = await res.json();
        if (!res.ok) throw new Error(result.detail || 'Upload failed');

        RiverWatch.toast(`Dataset uploaded successfully! Ingested ${result.row_count} records.`, 'success');
        RiverWatch.closeUploadModal();
        setTimeout(() => {
          window.location.href = 'riverupload.html';
        }, 1000);
      } catch (err) {
        RiverWatch.toast(`Upload Error: ${err.message}`, 'error');
        submitBtn.disabled = false;
        submitBtn.innerText = '⚡ Ingest & Validate File';
      }
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal) RiverWatch.closeUploadModal();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.style.display !== 'none') {
        RiverWatch.closeUploadModal();
      }
    });
  },

  openUploadModal() {
    const modal = document.getElementById('quickUploadModal');
    if (modal) modal.style.display = 'flex';
  },

  closeUploadModal() {
    const modal = document.getElementById('quickUploadModal');
    if (modal) modal.style.display = 'none';
  },

  // Toast Notifications
  toast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : '💡';
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.25s ease';
      setTimeout(() => toast.remove(), 250);
    }, 4000);
  },

  // Color helper for WQI Classes - Clean Non-Blue Palette
  getWQIColor(wqiClass) {
    const c = (wqiClass || '').toLowerCase();
    if (c.includes('excellent')) return '#059669'; // Deep Bio-Emerald
    if (c.includes('good')) return '#0d9488';      // Mint Teal
    if (c.includes('poor') && !c.includes('very')) return '#d97706'; // Warm Amber
    if (c.includes('very poor')) return '#ea580c'; // Sunset Orange
    if (c.includes('unsuitable')) return '#e11d48'; // Coral Crimson
    return '#64748b';
  },

  // HTML Badge helper
  getWQIBadge(wqiClass) {
    const c = (wqiClass || 'Unknown').toLowerCase();
    let pillClass = 'pill-good';
    if (c.includes('excellent')) pillClass = 'pill-excellent';
    else if (c.includes('very poor')) pillClass = 'pill-very-poor';
    else if (c.includes('poor')) pillClass = 'pill-poor';
    else if (c.includes('unsuitable')) pillClass = 'pill-unsuitable';

    return `<span class="status-pill ${pillClass}">${wqiClass || 'Unknown'}</span>`;
  },

  // Modern 2026 Light Theme Plotly Layout Presets
  getPlotlyLayout(title, extra = {}) {
    return {
      title: {
        text: title,
        font: { family: 'Plus Jakarta Sans, sans-serif', size: 14, color: '#0f172a' },
      },
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { family: 'Plus Jakarta Sans, sans-serif', color: '#475569', size: 11 },
      xaxis: {
        gridcolor: '#f1f5f9',
        linecolor: '#e2e8f0',
        tickfont: { size: 10, color: '#64748b' },
      },
      yaxis: {
        gridcolor: '#f1f5f9',
        linecolor: '#e2e8f0',
        tickfont: { size: 10, color: '#64748b' },
      },
      margin: { l: 45, r: 25, t: 35, b: 35 },
      hoverlabel: {
        bgcolor: '#ffffff',
        bordercolor: '#059669',
        font: { family: 'Plus Jakarta Sans, sans-serif', color: '#0f172a' },
      },
      ...extra,
    };
  },
};

document.addEventListener('DOMContentLoaded', () => RiverWatch.init());

// Global safety interceptor: guarantees clicking any upload link always routes to riverupload.html
document.addEventListener('click', (e) => {
  const link = e.target.closest('a');
  if (link) {
    const href = link.getAttribute('href') || '';
    if (href === 'upload.html' || href.endsWith('/upload.html')) {
      e.preventDefault();
      e.stopPropagation();
      window.location.href = 'riverupload.html';
    }
  }
}, true);
