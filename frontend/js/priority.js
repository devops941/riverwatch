/**
 * RiverWatch 2026 Sampling Priority Controller
 */

let debounceTimer = null;

document.addEventListener('DOMContentLoaded', async () => {
  await loadPriorityData();

  // Attach slider input listeners
  ['wqi_12m', 'wqi_slope', 'violation_rate', 'recency', 'variability_gap'].forEach(key => {
    const slider = document.getElementById(`weight_${key}`);
    const label = document.getElementById(`label_${key}`);
    slider?.addEventListener('input', () => {
      if (label) label.innerText = `${slider.value}%`;
      debouncedRecompute();
    });
  });

  document.getElementById('resetWeightsBtn')?.addEventListener('click', resetDefaults);
});

async function loadPriorityData() {
  try {
    const data = await RiverWatch.api('/priority');
    renderPriorityViews(data);
  } catch (err) {
    console.error('Failed to load priority data:', err);
  }
}

function debouncedRecompute() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(recomputeWithCustomWeights, 250);
}

async function recomputeWithCustomWeights() {
  const getW = (key) => parseFloat(document.getElementById(`weight_${key}`)?.value || 0);

  const rawWeights = {
    wqi_12m: getW('wqi_12m'),
    wqi_slope: getW('wqi_slope'),
    violation_rate: getW('violation_rate'),
    recency: getW('recency'),
    variability_gap: getW('variability_gap'),
  };

  const sum = Object.values(rawWeights).reduce((a, b) => a + b, 0) || 1.0;
  const normalized = {};
  for (const k in rawWeights) normalized[k] = rawWeights[k] / sum;

  try {
    const data = await RiverWatch.api('/priority/recompute', {
      method: 'POST',
      body: JSON.stringify({ weights: normalized }),
    });
    renderPriorityViews(data);
  } catch (err) {
    console.error('Failed to recompute priority:', err);
  }
}

function resetDefaults() {
  const defaults = { wqi_12m: 30, wqi_slope: 25, violation_rate: 20, recency: 15, variability_gap: 10 };
  for (const k in defaults) {
    const slider = document.getElementById(`weight_${k}`);
    const label = document.getElementById(`label_${k}`);
    if (slider) slider.value = defaults[k];
    if (label) label.innerText = `${defaults[k]}%`;
  }
  recomputeWithCustomWeights();
}

function renderPriorityViews(data) {
  renderPriorityChart(data);
  renderPriorityTable(data);
}

function renderPriorityChart(data) {
  const chartElem = document.getElementById('priorityRankChart');
  if (!chartElem || data.length === 0) return;

  const sorted = [...data].reverse(); // reverse for horizontal bar chart order
  const names = sorted.map(d => d.station_name || d.station_id);
  const scores = sorted.map(d => d.priority_score || 0);

  const colors = sorted.map(d => {
    if ((d.priority_rank || 10) <= 2) return '#f43f5e'; // Coral Red (urgent)
    if ((d.priority_rank || 10) <= 4) return '#f59e0b'; // Amber Gold (moderate)
    return '#10b981'; // Bio-Emerald Green (stable)
  });

  const trace = {
    x: scores,
    y: names,
    type: 'bar',
    orientation: 'h',
    marker: { color: colors, opacity: 0.85, line: { color: '#ffffff', width: 1 } },
    text: scores.map(s => s.toFixed(3)),
    textposition: 'auto',
  };

  const layout = RiverWatch.getPlotlyLayout('Station Priority Score (Higher = Urgent Sampling Needed)', {
    xaxis: { title: 'Normalized Priority Score (0.0 to 1.0)', range: [0, 1.05] },
    margin: { l: 150, r: 25, t: 30, b: 40 },
  });

  Plotly.newPlot(chartElem, [trace], layout, { responsive: true, displayModeBar: false });
}

function renderPriorityTable(data) {
  const tbody = document.getElementById('priorityTableBody');
  if (!tbody) return;

  tbody.innerHTML = data.map(d => {
    const isHigh = d.priority_rank <= 2;
    const rankPill = isHigh ? 'pill-unsuitable' : d.priority_rank <= 5 ? 'pill-poor' : 'pill-good';

    return `
      <tr>
        <td><span class="status-pill ${rankPill}">Rank #${d.priority_rank}</span></td>
        <td><strong>${d.station_id}</strong></td>
        <td><strong>${d.station_name}</strong></td>
        <td><strong style="color: ${isHigh ? 'var(--accent-rose)' : 'inherit'}; font-size: 14.5px;">${d.priority_score}</strong></td>
        <td>${d.mean_wqi_12m}</td>
        <td>${d.wqi_slope > 0 ? '+' : ''}${d.wqi_slope}/yr</td>
        <td>${Math.round((d.violation_rate || 0) * 100)}%</td>
        <td>${d.days_since_last_sample} days</td>
        <td>
          <div style="font-size: 13px; font-weight: 600; color: ${isHigh ? 'var(--accent-rose)' : 'var(--text-secondary)'};">
            ${d.reason}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

window.addEventListener('themeChanged', () => {
  const c = document.getElementById('priorityRankChart');
  if (c && c.data) Plotly.relayout(c, RiverWatch.getPlotlyLayout('Priority'));
});
