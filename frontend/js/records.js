/**
 * RiverWatch 2026 Records & Audit Controller
 */

let currentPage = 1;
let totalPages = 1;
let activeEditSampleId = null;

document.addEventListener('DOMContentLoaded', async () => {
  await loadStationFilterOptions();
  await loadRecords();

  document.getElementById('stationFilter')?.addEventListener('change', () => {
    currentPage = 1;
    loadRecords();
  });

  document.getElementById('prevPageBtn')?.addEventListener('click', () => {
    if (currentPage > 1) { currentPage--; loadRecords(); }
  });

  document.getElementById('nextPageBtn')?.addEventListener('click', () => {
    if (currentPage < totalPages) { currentPage++; loadRecords(); }
  });

  // Tab switching
  document.getElementById('tabRecordsBtn')?.addEventListener('click', () => switchTab('records'));
  document.getElementById('tabAuditBtn')?.addEventListener('click', () => switchTab('audit'));

  // Edit Modal Event Listeners
  document.getElementById('cancelEditBtn')?.addEventListener('click', closeEditModal);
  document.getElementById('closeEditModalBtn')?.addEventListener('click', closeEditModal);
  document.getElementById('saveEditBtn')?.addEventListener('click', saveRecordCorrection);

  // Click outside to close modal
  const editModal = document.getElementById('editModal');
  editModal?.addEventListener('click', (e) => {
    if (e.target === editModal) closeEditModal();
  });

  // ESC key to close modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && editModal && editModal.style.display !== 'none') {
      closeEditModal();
    }
  });
});

async function loadStationFilterOptions() {
  try {
    const stations = await RiverWatch.api('/stations');
    const select = document.getElementById('stationFilter');
    if (!select) return;

    stations.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.station_id;
      opt.innerText = `${s.station_id} - ${s.station_name}`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Failed to load stations:', err);
  }
}

async function loadRecords() {
  const stn = document.getElementById('stationFilter')?.value || '';
  let url = `/records?page=${currentPage}&page_size=25`;
  if (stn) url += `&station_id=${stn}`;

  try {
    const res = await RiverWatch.api(url);
    totalPages = res.total_pages || 1;

    document.getElementById('paginationInfo').innerText = `Page ${res.page} of ${totalPages} (${res.total_records} total samples)`;
    document.getElementById('pageIndicator').innerText = `Page ${res.page} of ${totalPages}`;

    const tbody = document.getElementById('recordsTableBody');
    if (!tbody) return;

    if (res.records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 20px;">No samples found.</td></tr>`;
      return;
    }

    tbody.innerHTML = res.records.map(r => {
      const m = r.measurements || {};
      return `
        <tr>
          <td><code>#${r.sample_id}</code></td>
          <td><strong>${r.station_id}</strong></td>
          <td>${r.sample_date}</td>
          <td><strong>${r.wqi !== null ? r.wqi : 'N/A'}</strong></td>
          <td>${RiverWatch.getWQIBadge(r.wqi_class)}</td>
          <td><span style="font-size: 11px; font-weight: 700;">${r.cpcb_class || 'N/A'}</span></td>
          <td>${m.do_mgl !== undefined && m.do_mgl !== null ? m.do_mgl : '--'}</td>
          <td>${m.bod_mgl !== undefined && m.bod_mgl !== null ? m.bod_mgl : '--'}</td>
          <td>${m.cod_mgl !== undefined && m.cod_mgl !== null ? m.cod_mgl : '--'}</td>
          <td>${m.nitrate_mgl !== undefined && m.nitrate_mgl !== null ? m.nitrate_mgl : '--'}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="openEditModal(${r.sample_id}, '${r.station_id}', '${r.sample_date}')">✏️ Edit</button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load records:', err);
  }
}

async function loadAuditTrail() {
  try {
    const audits = await RiverWatch.api('/records/audit');
    const tbody = document.getElementById('auditTableBody');
    if (!tbody) return;

    if (audits.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 20px;">No correction audit logs yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = audits.map(a => `
      <tr>
        <td><code>#AUD-${a.audit_id}</code></td>
        <td><code>#${a.sample_id}</code></td>
        <td><strong>${a.param_code}</strong></td>
        <td><span style="color: var(--accent-rose);">${a.old_value !== null ? a.old_value : 'null'}</span></td>
        <td><span style="color: var(--accent-primary); font-weight: 700;">${a.new_value !== null ? a.new_value : 'null'}</span></td>
        <td>${a.reason}</td>
        <td><span style="font-size: 11.5px; color: var(--text-muted);">${new Date(a.changed_at).toLocaleString()}</span></td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Failed to load audit trail:', err);
  }
}

function switchTab(tab) {
  const recSec = document.getElementById('recordsViewSection');
  const audSec = document.getElementById('auditViewSection');
  const recBtn = document.getElementById('tabRecordsBtn');
  const audBtn = document.getElementById('tabAuditBtn');

  if (tab === 'records') {
    recSec.style.display = 'block';
    audSec.style.display = 'none';
    recBtn.className = 'btn btn-primary';
    audBtn.className = 'btn btn-secondary';
    loadRecords();
  } else {
    recSec.style.display = 'none';
    audSec.style.display = 'block';
    recBtn.className = 'btn btn-secondary';
    audBtn.className = 'btn btn-primary';
    loadAuditTrail();
  }
}

function openEditModal(sampleId, stationId, date) {
  activeEditSampleId = sampleId;
  const modal = document.getElementById('editModal');
  const details = document.getElementById('editModalMeta');

  if (details) {
    details.innerHTML = `Sample ID: <code>#${sampleId}</code> | Station: <strong>${stationId}</strong> | Date: <strong>${date}</strong>`;
  }
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeEditModal() {
  const modal = document.getElementById('editModal');
  if (modal) {
    modal.style.display = 'none';
  }
  activeEditSampleId = null;
}

async function saveRecordCorrection() {
  if (!activeEditSampleId) return;

  const param = document.getElementById('editParamSelect').value;
  const val = parseFloat(document.getElementById('editNewVal').value);
  const reason = document.getElementById('editReason').value;

  if (isNaN(val)) {
    RiverWatch.toast('Please enter a valid numeric value.', 'error');
    return;
  }

  try {
    const res = await RiverWatch.api(`/records/${activeEditSampleId}/${param}`, {
      method: 'PATCH',
      body: JSON.stringify({ new_value: val, reason }),
    });

    RiverWatch.toast(`Measurement updated: Audit #AUD-${res.audit_id} created.`, 'success');
    closeEditModal();
    loadRecords();
  } catch (err) {
    // Handled in api
  }
}
