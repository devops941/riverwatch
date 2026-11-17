/**
 * RiverWatch 2026 Export & Reports Controller
 * Manages PDF compilation, report list rendering, and document downloads.
 */

document.addEventListener('DOMContentLoaded', async () => {
  await loadReportsList();
  document.getElementById('generatePdfBtn')?.addEventListener('click', generateNewReport);
});

async function loadReportsList() {
  try {
    const reports = await RiverWatch.api('/reports');
    const tbody = document.getElementById('reportsTableBody');
    if (!tbody) return;

    if (!reports || reports.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 24px;">No executive reports generated yet. Click "Generate New PDF Report" above to compile one.</td></tr>`;
      return;
    }

    tbody.innerHTML = reports.map(r => `
      <tr>
        <td><strong style="color: var(--text-primary); font-family: var(--font-mono);">#REP-${r.report_id}</strong></td>
        <td>${r.created_at ? new Date(r.created_at).toLocaleString() : 'Recent'}</td>
        <td><span class="status-pill pill-excellent">PDF Document</span></td>
        <td>
          <a href="${r.pdf_url}" target="_blank" download class="btn btn-primary btn-sm">📥 Download PDF</a>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Failed to load reports:', err);
  }
}

async function generateNewReport() {
  const btn = document.getElementById('generatePdfBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Rendering PDF Report...';
  }

  RiverWatch.toast('Compiling water quality analytics and rendering high-res PDF charts...', 'info');

  try {
    const res = await RiverWatch.api('/report', { method: 'POST' });
    RiverWatch.toast(`Report #REP-${res.report_id} successfully compiled!`, 'success');
    await loadReportsList();

    // Auto trigger download
    window.open(res.pdf_url, '_blank');
  } catch (err) {
    // Handled in api
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '⚡ Generate New PDF Report';
    }
  }
}
