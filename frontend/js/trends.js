/**
 * RiverWatch 2026 Trends Controller
 */

let allTrendsData = [];

document.addEventListener('DOMContentLoaded', async () => {
  await loadTrends();
  document.getElementById('trendParamSelect')?.addEventListener('change', filterAndRenderTrends);
  document.getElementById('significanceFilter')?.addEventListener('change', filterAndRenderTrends);
});

async function loadTrends() {
  try {
    allTrendsData = await RiverWatch.api('/trends');
    filterAndRenderTrends();
  } catch (err) {
    console.error('Failed to load trends:', err);
  }
}

function filterAndRenderTrends() {
  const param = document.getElementById('trendParamSelect')?.value || 'wqi';
  const sigMode = document.getElementById('significanceFilter')?.value || 'sig';

  // Compute overall KPI counts
  let worsening = 0, improving = 0, noTrend = 0;
  allTrendsData.forEach(t => {
    if (t.interpretation === 'worsening') worsening++;
    else if (t.interpretation === 'improving') improving++;
    else noTrend++;
  });

  document.getElementById('kpiTotalTrends').innerText = allTrendsData.length;
  document.getElementById('kpiWorseningCount').innerText = worsening;
  document.getElementById('kpiImprovingCount').innerText = improving;
  document.getElementById('kpiNoTrendCount').innerText = noTrend;

  // Filter trends for selected parameter
  let paramTrends = allTrendsData.filter(t => t.param_code === param);
  if (sigMode === 'sig') {
    paramTrends = paramTrends.filter(t => (t.p_value || 1.0) < 0.05);
  }

  renderSensSlopeChart(paramTrends, param);
  renderTrendsTable(paramTrends);
}

function renderSensSlopeChart(trends, param) {
  const chartElem = document.getElementById('sensSlopeChart');
  if (!chartElem) return;

  if (trends.length === 0) {
    Plotly.purge(chartElem);
    chartElem.innerHTML = `<div style="display:flex; align-items:center; justify-content:center; height:100%; color:var(--text-muted); font-size:13px;">No statistically significant trends found for ${param.toUpperCase()}.</div>`;
    return;
  }

  const sorted = [...trends].sort((a, b) => (b.sen_slope_per_year || 0) - (a.sen_slope_per_year || 0));

  const stnLabels = sorted.map(t => t.station_id);
  const slopes = sorted.map(t => t.sen_slope_per_year || 0);
  const colors = sorted.map(t => {
    if (t.interpretation === 'worsening') return '#f43f5e';
    if (t.interpretation === 'improving') return '#10b981';
    return '#94a3b8';
  });

  const trace = {
    x: stnLabels,
    y: slopes,
    type: 'bar',
    marker: { color: colors, opacity: 0.85, line: { color: '#ffffff', width: 1 } },
    text: slopes.map(s => `${s > 0 ? '+' : ''}${s.toFixed(3)}/yr`),
    textposition: 'auto',
  };

  const layout = RiverWatch.getPlotlyLayout(`Sen's Slope: Annual Rate of Change for ${param.toUpperCase()}`, {
    yaxis: { title: 'Units / Year' },
    xaxis: { title: 'Station ID' },
  });

  Plotly.newPlot(chartElem, [trace], layout, { responsive: true, displayModeBar: false });
}

function renderTrendsTable(trends) {
  const tbody = document.getElementById('trendsTableBody');
  if (!tbody) return;

  if (trends.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 20px;">No trend records match the current filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = trends.map(t => {
    const isWorse = t.interpretation === 'worsening';
    const isImp = t.interpretation === 'improving';
    const badgeClass = isWorse ? 'badge-danger' : isImp ? 'badge-positive' : 'badge-warning';

    return `
      <tr>
        <td><strong>${t.station_id}</strong></td>
        <td><code>${t.param_code}</code></td>
        <td><span style="font-size: 11.5px; color: var(--text-muted);">${t.test_used}</span></td>
        <td><strong>${(t.trend || '').toUpperCase()}</strong></td>
        <td><span class="kpi-badge ${badgeClass}">${(t.interpretation || '').toUpperCase()}</span></td>
        <td><strong style="color: ${isWorse ? 'var(--accent-rose)' : isImp ? 'var(--accent-primary)' : 'inherit'};">${t.sen_slope_per_year > 0 ? '+' : ''}${t.sen_slope_per_year}/yr</strong></td>
        <td>${t.tau}</td>
        <td><code style="color: ${t.p_value < 0.05 ? 'var(--accent-primary)' : 'var(--text-muted)'}; font-weight: 700;">p = ${t.p_value}</code></td>
        <td>${t.pct_change_per_year > 0 ? '+' : ''}${t.pct_change_per_year}%</td>
      </tr>
    `;
  }).join('');
}

window.addEventListener('themeChanged', () => {
  const c = document.getElementById('sensSlopeChart');
  if (c && c.data) Plotly.relayout(c, RiverWatch.getPlotlyLayout("Sen's Slope"));
});
