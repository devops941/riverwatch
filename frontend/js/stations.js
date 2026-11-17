/**
 * RiverWatch 2026 Station Explorer Controller
 */

let allStations = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadStationsList();
  document.getElementById('stationSelect')?.addEventListener('change', updateStationView);
  document.getElementById('paramSelect')?.addEventListener('change', updateStationView);
});

async function loadStationsList() {
  try {
    allStations = await RiverWatch.api('/stations');
    const select = document.getElementById('stationSelect');
    if (!select || allStations.length === 0) return;

    select.innerHTML = allStations.map(s => `
      <option value="${s.station_id}">#${s.river_order} - ${s.station_name} (${s.station_id})</option>
    `).join('');

    updateStationView();
  } catch (err) {
    console.error('Failed to load stations:', err);
  }
}

async function updateStationView() {
  const stationId = document.getElementById('stationSelect')?.value;
  const param = document.getElementById('paramSelect')?.value || 'wqi';
  if (!stationId) return;

  const stn = allStations.find(s => s.station_id === stationId);
  if (stn) {
    document.getElementById('stnOrderVal').innerText = `#${stn.river_order || '1'}`;
    document.getElementById('stnRiverName').innerText = `${stn.river_name || 'Ganga'} Basin`;
    document.getElementById('stnLatestWqi').innerText = stn.latest_wqi || 'N/A';
    document.getElementById('stnWqiPill').innerHTML = RiverWatch.getWQIBadge(stn.wqi_class);
    document.getElementById('stnCpcbClass').innerText = stn.cpcb_class || 'Evaluating';
    document.getElementById('stnPriorityScore').innerText = stn.priority_score || '--';
  }

  try {
    const [seriesData, complianceData] = await Promise.all([
      RiverWatch.api(`/stations/${stationId}/series?param=${param}`),
      RiverWatch.api(`/compliance?station_id=${stationId}`),
    ]);

    renderSeriesChart(seriesData);
    renderSeasonalBoxplot(seriesData);
    renderComplianceTable(complianceData[0]);
  } catch (err) {
    console.error('Failed to update station view:', err);
  }
}

function renderSeriesChart(data) {
  const chartElem = document.getElementById('stationSeriesChart');
  if (!chartElem) return;

  const titleElem = document.getElementById('timeSeriesTitle');
  const badgeElem = document.getElementById('standardLimitBadge');

  if (titleElem) titleElem.innerText = `${data.display_name} Historical Trajectory`;
  if (badgeElem) {
    badgeElem.innerText = data.standard_value ? `Permissible Limit: ${data.standard_value} ${data.unit}` : `Unit: ${data.unit}`;
  }

  const xDates = data.points.map(p => p.sample_date);
  const yVals = data.points.map(p => p.value);

  const trace = {
    x: xDates,
    y: yVals,
    type: 'scatter',
    mode: 'lines+markers',
    marker: { size: 6, color: '#10b981' },
    line: { color: '#10b981', width: 2.2 },
    name: data.display_name,
  };

  const shapes = [];
  if (data.standard_value) {
    shapes.push({
      type: 'line',
      x0: 0,
      x1: 1,
      xref: 'paper',
      y0: data.standard_value,
      y1: data.standard_value,
      line: { color: '#f43f5e', width: 2, dash: 'dash' },
    });
  }

  const layout = RiverWatch.getPlotlyLayout(`${data.display_name} (${data.unit})`, {
    shapes,
    yaxis: { title: data.unit },
    xaxis: { title: 'Date' },
  });

  Plotly.newPlot(chartElem, [trace], layout, { responsive: true, displayModeBar: false });
}

function renderSeasonalBoxplot(data) {
  const chartElem = document.getElementById('seasonalBoxplot');
  if (!chartElem) return;

  const seasons = { 'Winter': [], 'Summer': [], 'Monsoon': [], 'Post-Monsoon': [] };

  data.points.forEach(p => {
    if (p.value !== null && p.sample_date) {
      const month = parseInt(p.sample_date.split('-')[1]);
      if ([11, 12, 1, 2].includes(month)) seasons['Winter'].push(p.value);
      else if ([3, 4, 5, 6].includes(month)) seasons['Summer'].push(p.value);
      else if ([7, 8, 9].includes(month)) seasons['Monsoon'].push(p.value);
      else seasons['Post-Monsoon'].push(p.value);
    }
  });

  const traces = Object.keys(seasons).map(sName => ({
    y: seasons[sName],
    type: 'box',
    name: sName,
    boxpoints: 'outliers',
    jitter: 0.3,
  }));

  const layout = RiverWatch.getPlotlyLayout('Seasonal Distribution', {
    yaxis: { title: data.unit },
    showlegend: false,
  });

  Plotly.newPlot(chartElem, traces, layout, { responsive: true, displayModeBar: false });
}

function renderComplianceTable(comp) {
  const tbody = document.getElementById('complianceBreakdownBody');
  if (!tbody || !comp) return;

  const classes = [
    { name: 'Class A', desc: 'Drinking water source without conventional treatment', pct: comp.pct_class_a },
    { name: 'Class B', desc: 'Outdoor bathing (organized) standard', pct: comp.pct_class_b },
    { name: 'Class C', desc: 'Drinking water source with conventional treatment', pct: comp.pct_class_c },
    { name: 'Class D', desc: 'Propagation of wildlife & fisheries', pct: comp.pct_class_d },
    { name: 'Class E', desc: 'Irrigation, industrial cooling & waste disposal', pct: comp.pct_class_e },
    { name: 'Below Class E', desc: 'Severely polluted / non-conforming', pct: comp.pct_below_e },
  ];

  tbody.innerHTML = classes.map(c => `
    <tr>
      <td><strong>${c.name}</strong></td>
      <td style="color: var(--text-secondary);">${c.desc}</td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="width: 80px; height: 6px; background: var(--bg-secondary); border-radius: 3px; overflow: hidden;">
            <div style="width: ${c.pct}%; height: 100%; background: ${c.pct > 50 ? 'var(--accent-emerald)' : 'var(--accent-rose)'};"></div>
          </div>
          <span><strong>${c.pct}%</strong></span>
        </div>
      </td>
      <td><span style="color: var(--accent-rose); font-size: 12px;">${comp.dominant_violations.join(', ') || 'Compliant'}</span></td>
    </tr>
  `).join('');
}

window.addEventListener('themeChanged', () => {
  const c1 = document.getElementById('stationSeriesChart');
  const c2 = document.getElementById('seasonalBoxplot');
  if (c1 && c1.data) Plotly.relayout(c1, RiverWatch.getPlotlyLayout('Time Series'));
  if (c2 && c2.data) Plotly.relayout(c2, RiverWatch.getPlotlyLayout('Seasonal Distribution'));
});
