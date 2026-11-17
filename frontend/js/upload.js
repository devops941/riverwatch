/**
 * RiverWatch 2026 Upload & Validation Controller
 */

let currentUploadId = null;
let activeFixIssueId = null;

document.addEventListener('DOMContentLoaded', () => {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');

  // Drag and drop event listeners
  ['dragenter', 'dragover'].forEach(name => {
    dropzone?.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.add('drag-active');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropzone?.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag-active');
    });
  });

  dropzone?.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFileUpload(files[0]);
  });

  fileInput?.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFileUpload(e.target.files[0]);
  });

  // Filter change listeners
  document.getElementById('severityFilter')?.addEventListener('change', loadIssues);
  document.getElementById('statusFilter')?.addEventListener('change', loadIssues);

  // Commit Button
  document.getElementById('commitBtn')?.addEventListener('click', commitUpload);

  // Synthetic Dataset Button
  document.getElementById('loadSyntheticBtn')?.addEventListener('click', loadSyntheticSample);

  // Modal Cancel & Save & Close
  document.getElementById('cancelModalBtn')?.addEventListener('click', closeFixModal);
  document.getElementById('modalCloseXBtn')?.addEventListener('click', closeFixModal);
  document.getElementById('saveFixBtn')?.addEventListener('click', applyModalFix);

  const fixModal = document.getElementById('fixModal');
  fixModal?.addEventListener('click', (e) => {
    if (e.target === fixModal) closeFixModal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && fixModal && fixModal.style.display !== 'none') {
      closeFixModal();
    }
  });
});

async function handleFileUpload(file) {
  RiverWatch.toast(`Uploading & validating ${file.name}...`, 'info');
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/uploads', {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }

    const data = await res.json();
    currentUploadId = data.upload_id;

    // Display summary
    document.getElementById('validationSummarySection').style.display = 'grid';
    document.getElementById('issuesSection').style.display = 'block';

    document.getElementById('valTotalRows').innerText = data.n_rows;
    document.getElementById('valErrors').innerText = data.n_errors;
    document.getElementById('valWarnings').innerText = data.n_warnings;
    document.getElementById('valStatus').innerText = data.status.toUpperCase();
    document.getElementById('valUploadId').innerText = `Upload ID: #${data.upload_id}`;

    RiverWatch.toast(`Validated ${data.n_rows} rows: ${data.n_errors} errors, ${data.n_warnings} warnings.`, data.n_errors > 0 ? 'error' : 'success');
    loadIssues();
  } catch (err) {
    RiverWatch.toast(err.message, 'error');
  }
}

async function loadIssues() {
  if (!currentUploadId) return;

  const severity = document.getElementById('severityFilter')?.value || '';
  const status = document.getElementById('statusFilter')?.value || '';

  let url = `/uploads/${currentUploadId}/issues?`;
  if (severity) url += `severity=${severity}&`;
  if (status) url += `status=${status}&`;

  try {
    const issues = await RiverWatch.api(url);
    const tbody = document.getElementById('issuesTableBody');

    if (issues.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 20px;">No validation issues matching the selected filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = issues.map(iss => {
      const isErr = iss.severity === 'error';
      const sevBadge = isErr ? '<span class="status-pill pill-unsuitable">Error</span>' : '<span class="status-pill pill-poor">Warning</span>';
      const statusBadge = `<span class="kpi-badge ${iss.status === 'open' ? 'badge-warning' : 'badge-positive'}">${iss.status.toUpperCase()}</span>`;

      return `
        <tr>
          <td><strong>${iss.row_number || 'All'}</strong></td>
          <td><code>${iss.column_name || 'N/A'}</code></td>
          <td><span style="font-family: var(--font-mono); color: var(--accent-rose);">${iss.value || 'None'}</span></td>
          <td>${sevBadge}</td>
          <td><strong style="font-size: 12px;">${iss.rule}</strong></td>
          <td>
            <div style="font-size: 13px;">${iss.message}</div>
            <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 3px;">💡 ${iss.suggestion || 'Inspect value'}</div>
          </td>
          <td>${statusBadge}</td>
          <td>
            <div style="display: flex; gap: 6px;">
              <button class="btn btn-secondary btn-sm" onclick="openFixModal(${iss.issue_id}, '${iss.column_name}', '${iss.value}')">Fix</button>
              <button class="btn btn-secondary btn-sm" onclick="patchIssue(${iss.issue_id}, 'ignore')">Ignore</button>
              <button class="btn btn-danger btn-sm" onclick="patchIssue(${iss.issue_id}, 'exclude_row')">Exclude</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load issues:', err);
  }
}

async function patchIssue(issueId, action, newVal = null, reason = null) {
  try {
    await RiverWatch.api(`/uploads/${currentUploadId}/issues/${issueId}`, {
      method: 'PATCH',
      body: JSON.stringify({ action, new_value: newVal, reason }),
    });
    RiverWatch.toast(`Issue #${issueId} marked as ${action}.`, 'success');
    loadIssues();
  } catch (err) {
    // Handled in api
  }
}

function openFixModal(issueId, col, val) {
  activeFixIssueId = issueId;
  const modal = document.getElementById('fixModal');
  const details = document.getElementById('modalDetails');
  const input = document.getElementById('modalNewVal');

  details.innerHTML = `Resolving Issue for Column: <code>${col}</code> | Current Value: <code>${val}</code>`;
  input.value = val && val !== 'None' ? val : '';
  modal.style.display = 'flex';
}

function closeFixModal() {
  document.getElementById('fixModal').style.display = 'none';
  activeFixIssueId = null;
}

async function applyModalFix() {
  const newVal = document.getElementById('modalNewVal').value;
  const reason = document.getElementById('modalReason').value;

  if (activeFixIssueId) {
    await patchIssue(activeFixIssueId, 'fix', newVal, reason);
    closeFixModal();
  }
}

async function commitUpload() {
  if (!currentUploadId) {
    RiverWatch.toast('No upload active to commit.', 'error');
    return;
  }

  RiverWatch.toast('Preprocessing, committing to SQLite, and computing analytics...', 'info');
  try {
    const res = await RiverWatch.api(`/uploads/${currentUploadId}/commit?duplicate_strategy=keep_first`, {
      method: 'POST',
    });
    RiverWatch.toast(`Committed ${res.samples_committed} samples and ${res.measurements_committed} measurements!`, 'success');
    setTimeout(() => {
      window.location.href = 'index.html';
    }, 1200);
  } catch (err) {
    // Handled
  }
}

async function loadSyntheticSample() {
  RiverWatch.toast('Generating & loading 8-year synthetic river monitoring data...', 'info');
  try {
    const res = await RiverWatch.api('/datasets/sample', { method: 'POST' });
    RiverWatch.toast(`Loaded ${res.n_samples} samples across 8 stations with full analytical pipeline!`, 'success');
    setTimeout(() => {
      window.location.href = 'index.html';
    }, 1000);
  } catch (err) {
    // Handled
  }
}
