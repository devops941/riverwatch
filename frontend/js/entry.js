/**
 * RiverWatch 2026 Direct Data Entry Controller
 * Powers manual field sample recording, instant WQI calculation preview,
 * and automated basin analytics recalculation.
 */

const PARAM_FIELDS = [
  'do_mgl',
  'ph',
  'temp_c',
  'turbidity_ntu',
  'conductivity_uscm',
  'tds_mgl',
  'bod_mgl',
  'cod_mgl',
  'nitrate_mgl',
  'ammonia_mgl',
  'total_coliform_mpn',
  'faecal_coliform_mpn',
];

let previewDebounceTimer = null;

document.addEventListener('DOMContentLoaded', async () => {
  await loadStationsList();
  setDefaultDate();
  setupEventListeners();
});

async function loadStationsList() {
  try {
    const stations = await RiverWatch.api('/stations');
    const select = document.getElementById('entryStation');
    if (!select) return;

    select.innerHTML = stations.map(s => `
      <option value="${s.station_id}">
        ${s.station_id} - ${s.station_name} (#${s.river_order || '?'})
      </option>
    `).join('');
  } catch (err) {
    console.error('Failed to load stations:', err);
  }
}

function setDefaultDate() {
  const dateInput = document.getElementById('entryDate');
  if (dateInput) {
    const today = new Date().toISOString().split('T')[0];
    dateInput.value = today;
  }
}

function setupEventListeners() {
  // Set today quick button
  document.getElementById('todayQuickBtn')?.addEventListener('click', setDefaultDate);

  // Form submit
  document.getElementById('dataEntryForm')?.addEventListener('submit', handleFormSubmit);

  // Preview button
  document.getElementById('previewBtn')?.addEventListener('click', triggerPreviewCalculation);

  // Reset form
  document.getElementById('resetFormBtn')?.addEventListener('click', resetEntryForm);

  // Preset buttons
  document.getElementById('loadCleanSampleBtn')?.addEventListener('click', loadCleanPreset);
  document.getElementById('loadPollutedSampleBtn')?.addEventListener('click', loadPollutedPreset);

  // Live calculation on input change (debounced 400ms)
  PARAM_FIELDS.forEach(p => {
    const input = document.getElementById(`param_${p}`);
    input?.addEventListener('input', () => {
      clearTimeout(previewDebounceTimer);
      previewDebounceTimer = setTimeout(triggerPreviewCalculation, 400);
    });
  });
}

function collectMeasurementValues() {
  const measurements = {};
  PARAM_FIELDS.forEach(p => {
    const input = document.getElementById(`param_${p}`);
    if (input && input.value !== '' && !isNaN(parseFloat(input.value))) {
      measurements[p] = parseFloat(input.value);
    }
  });
  return measurements;
}

async function triggerPreviewCalculation() {
  const measurements = collectMeasurementValues();
  const keys = Object.keys(measurements);

  document.getElementById('previewParamsCount').innerText = `${keys.length} / 12`;

  if (keys.length === 0) {
    document.getElementById('previewWqiVal').innerText = '--';
    document.getElementById('previewWqiClass').innerHTML = '<span class="status-pill pill-good">Awaiting Data</span>';
    document.getElementById('previewCpcbClass').innerText = '--';
    document.getElementById('previewViolations').innerText = 'None';
    return;
  }

  try {
    const res = await fetch('/api/records/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ measurements }),
    });

    if (!res.ok) return;
    const data = await res.json();

    // Update live preview card
    const wqiVal = data.wqi !== null ? data.wqi.toFixed(1) : '--';
    const wqiValElem = document.getElementById('previewWqiVal');
    wqiValElem.innerText = wqiVal;
    wqiValElem.style.color = RiverWatch.getWQIColor(data.wqi_class);

    document.getElementById('previewWqiClass').innerHTML = RiverWatch.getWQIBadge(data.wqi_class);
    document.getElementById('previewCpcbClass').innerText = data.cpcb_class || 'Evaluating';

    const violDiv = document.getElementById('previewViolations');
    if (data.violating_params && data.violating_params.length > 0) {
      violDiv.innerHTML = data.violating_params.map(v => `• ${v}`).join('<br>');
      violDiv.style.color = 'var(--accent-rose)';
    } else {
      violDiv.innerText = '✓ None (Meets all standard limits)';
      violDiv.style.color = 'var(--accent-primary)';
    }
  } catch (err) {
    console.error('Preview calculation error:', err);
  }
}

async function handleFormSubmit(e) {
  e.preventDefault();

  const stationId = document.getElementById('entryStation').value;
  const sampleDate = document.getElementById('entryDate').value;
  const notes = document.getElementById('entryNotes').value;
  const measurements = collectMeasurementValues();

  if (Object.keys(measurements).length === 0) {
    RiverWatch.toast('Please enter at least one measurement parameter value.', 'error');
    return;
  }

  const submitBtn = document.getElementById('submitEntryBtn');
  submitBtn.disabled = true;
  submitBtn.innerText = '⏳ Recording & Recomputing Analytics...';

  try {
    const res = await RiverWatch.api('/records/entry', {
      method: 'POST',
      body: JSON.stringify({
        station_id: stationId,
        sample_date: sampleDate,
        measurements: measurements,
        notes: notes,
      }),
    });

    RiverWatch.toast(`Sample recorded! Computed WQI: ${res.wqi || 'N/A'} (${res.wqi_class || 'Evaluated'})`, 'success');

    // Update live preview card
    document.getElementById('previewWqiVal').innerText = res.wqi !== null ? res.wqi.toFixed(1) : '--';
    document.getElementById('previewWqiClass').innerHTML = RiverWatch.getWQIBadge(res.wqi_class);
    document.getElementById('previewCpcbClass').innerText = res.cpcb_class || 'Evaluated';

    // Show post submit links
    const postLinks = document.getElementById('postSubmitLinks');
    if (postLinks) postLinks.style.display = 'block';

  } catch (err) {
    // Handled in api client
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerText = '⚡ Save Sample & Recompute Analytics';
  }
}

function resetEntryForm() {
  document.getElementById('dataEntryForm').reset();
  setDefaultDate();
  document.getElementById('previewWqiVal').innerText = '--';
  document.getElementById('previewWqiClass').innerHTML = '<span class="status-pill pill-good">Awaiting Data</span>';
  document.getElementById('previewCpcbClass').innerText = '--';
  document.getElementById('previewParamsCount').innerText = '0 / 12';
  document.getElementById('previewViolations').innerText = 'None';
  document.getElementById('postSubmitLinks').style.display = 'none';
  RiverWatch.toast('Form cleared.', 'info');
}

function loadCleanPreset() {
  document.getElementById('param_do_mgl').value = '7.8';
  document.getElementById('param_ph').value = '7.4';
  document.getElementById('param_temp_c').value = '19.5';
  document.getElementById('param_turbidity_ntu').value = '4.2';
  document.getElementById('param_conductivity_uscm').value = '190';
  document.getElementById('param_tds_mgl').value = '120';
  document.getElementById('param_bod_mgl').value = '1.6';
  document.getElementById('param_cod_mgl').value = '8.5';
  document.getElementById('param_nitrate_mgl').value = '0.9';
  document.getElementById('param_ammonia_mgl').value = '0.12';
  document.getElementById('param_total_coliform_mpn').value = '65';
  document.getElementById('param_faecal_coliform_mpn').value = '25';
  document.getElementById('entryNotes').value = 'Pristine upstream verification sample';

  triggerPreviewCalculation();
  RiverWatch.toast('Loaded clean upstream water sample preset!', 'info');
}

function loadPollutedPreset() {
  document.getElementById('param_do_mgl').value = '2.4';
  document.getElementById('param_ph').value = '8.8';
  document.getElementById('param_temp_c').value = '28.0';
  document.getElementById('param_turbidity_ntu').value = '75.0';
  document.getElementById('param_conductivity_uscm').value = '980';
  document.getElementById('param_tds_mgl').value = '680';
  document.getElementById('param_bod_mgl').value = '14.8';
  document.getElementById('param_cod_mgl').value = '68.0';
  document.getElementById('param_nitrate_mgl').value = '8.5';
  document.getElementById('param_ammonia_mgl').value = '3.8';
  document.getElementById('param_total_coliform_mpn').value = '14500';
  document.getElementById('param_faecal_coliform_mpn').value = '6200';
  document.getElementById('entryNotes').value = 'High industrial & municipal discharge sample';

  triggerPreviewCalculation();
  RiverWatch.toast('Loaded severely polluted downstream sample preset!', 'info');
}
