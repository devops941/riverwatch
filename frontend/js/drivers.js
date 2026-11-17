/**
 * RiverWatch 2026 Drivers & PCA Controller
 * ZERO-BLUE PALETTE: Emerald, Amethyst Purple, Amber, Coral Rose.
 */

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const [drivers, corrData, pcaData] = await Promise.all([
      RiverWatch.api('/drivers'),
      RiverWatch.api('/correlation'),
      RiverWatch.api('/pca'),
    ]);

    renderDriverCards(drivers);
    renderCorrelationHeatmap(corrData);
    renderPCAScree(pcaData);
    renderPCABiplot(pcaData);
  } catch (err) {
    console.error('Failed to load drivers & PCA data:', err);
  }
});

function renderDriverCards(drivers) {
  const container = document.getElementById('driversListGrid');
  if (!container) return;

  if (drivers.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); font-size: 13px;">No driver rankings computed yet.</div>`;
    return;
  }

  container.innerHTML = drivers.slice(0, 6).map(d => {
    const isTop = d.rank === 1;
    const borderGlow = isTop ? 'border: 1px solid var(--accent-rose);' : 'border: 1px solid var(--accent-purple);';
    const scorePct = Math.round(d.combined_score * 100);

    return `
      <div class="glass-card" style="${borderGlow}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 17px; font-weight: 800; font-family: var(--font-mono); color: var(--accent-primary);">${d.param_code}</span>
          <span class="kpi-badge ${isTop ? 'badge-danger' : 'badge-purple'}">Rank #${d.rank}</span>
        </div>
        <p style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 12px; min-height: 52px;">
          ${d.explanation}
        </p>
        <div style="margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; font-size: 11.5px; font-weight: 700; margin-bottom: 4px;">
            <span style="color: var(--text-muted);">Composite Impact Score</span>
            <span>${d.combined_score} (${scorePct}%)</span>
          </div>
          <div style="width: 100%; height: 6px; background: var(--bg-secondary); border-radius: 3px; overflow: hidden;">
            <div style="width: ${scorePct}%; height: 100%; background: linear-gradient(90deg, var(--accent-primary), var(--accent-rose));"></div>
          </div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 10.5px; color: var(--text-muted); border-top: 1px solid var(--border-subtle); padding-top: 6px;">
          <span>PCA: <strong>${d.pca_score}</strong></span>
          <span>WQI Corr: <strong>${d.corr_score}</strong></span>
          <span>Change: <strong>${d.change_contribution}</strong></span>
        </div>
      </div>
    `;
  }).join('');
}

function renderCorrelationHeatmap(corrData) {
  const chartElem = document.getElementById('corrHeatmapChart');
  if (!chartElem || corrData.length === 0) return;

  // Build matrix of params
  const paramSet = new Set();
  corrData.forEach(c => {
    paramSet.add(c.param_a);
    paramSet.add(c.param_b);
  });

  const params = Array.from(paramSet).sort();
  const zMatrix = params.map(p1 => {
    return params.map(p2 => {
      if (p1 === p2) return 1.0;
      const match = corrData.find(c => (c.param_a === p1 && c.param_b === p2) || (c.param_a === p2 && c.param_b === p1));
      return match ? match.spearman_rho : 0.0;
    });
  });

  const trace = {
    z: zMatrix,
    x: params.map(p => p.split('_')[0]),
    y: params.map(p => p.split('_')[0]),
    type: 'heatmap',
    colorscale: [
      [0.0, '#8b5cf6'], // Royal Amethyst
      [0.5, '#12181e'], // Obsidian Carbon
      [1.0, '#f43f5e'], // Coral Crimson
    ],
    zmin: -1.0,
    zmax: 1.0,
    showscale: true,
  };

  const layout = RiverWatch.getPlotlyLayout('Pairwise Spearman Correlation', {
    xaxis: { tickangle: 45 },
    margin: { l: 70, r: 20, t: 30, b: 60 },
  });

  Plotly.newPlot(chartElem, [trace], layout, { responsive: true, displayModeBar: false });
}

function renderPCAScree(pcaData) {
  const chartElem = document.getElementById('pcaScreeChart');
  if (!chartElem || !pcaData.explained_variance) return;

  const comps = Object.keys(pcaData.explained_variance);
  const variances = comps.map(c => Math.round(pcaData.explained_variance[c] * 1000) / 10);
  const total = variances.reduce((a, b) => a + b, 0).toFixed(1);

  const badge = document.getElementById('pcaCumVarBadge');
  if (badge) badge.innerText = `Total Explained: ${total}%`;

  const barTrace = {
    x: comps,
    y: variances,
    type: 'bar',
    name: 'Variance Explained (%)',
    marker: { color: '#8b5cf6', opacity: 0.85 }, // Royal Amethyst
    text: variances.map(v => `${v}%`),
    textposition: 'auto',
  };

  let cum = 0;
  const cumVariances = variances.map(v => { cum += v; return cum; });
  const lineTrace = {
    x: comps,
    y: cumVariances,
    type: 'scatter',
    mode: 'lines+markers',
    name: 'Cumulative %',
    line: { color: '#10b981', width: 2.5 }, // Emerald
  };

  const layout = RiverWatch.getPlotlyLayout('Scree Plot (Variance by Principal Component)', {
    yaxis: { title: 'Percentage (%)', range: [0, 105] },
    showlegend: true,
  });

  Plotly.newPlot(chartElem, [barTrace, lineTrace], layout, { responsive: true, displayModeBar: false });
}

function renderPCABiplot(pcaData) {
  const chartElem = document.getElementById('pcaBiplotChart');
  if (!chartElem || !pcaData.scores) return;

  // Scatter points for sample observations
  const scoresTrace = {
    x: pcaData.scores.map(s => s.PC1),
    y: pcaData.scores.map(s => s.PC2),
    mode: 'markers',
    type: 'scatter',
    name: 'River Samples',
    marker: { size: 6, color: '#10b981', opacity: 0.65 }, // Emerald
  };

  // Loadings vectors for parameters
  const shapes = [];
  const annotations = [];

  if (pcaData.loadings) {
    const scale = 3.5;
    Object.keys(pcaData.loadings).forEach(param => {
      const p1 = (pcaData.loadings[param].PC1 || 0) * scale;
      const p2 = (pcaData.loadings[param].PC2 || 0) * scale;

      shapes.push({
        type: 'line',
        x0: 0,
        y0: 0,
        x1: p1,
        y1: p2,
        line: { color: '#f59e0b', width: 2 }, // Amber Gold vector
      });

      annotations.push({
        x: p1 * 1.15,
        y: p2 * 1.15,
        text: param.split('_')[0],
        showarrow: false,
        font: { size: 10, color: '#f59e0b', family: 'JetBrains Mono, monospace' },
      });
    });
  }

  const layout = RiverWatch.getPlotlyLayout('PCA Biplot (PC1 vs PC2 Loadings & Scores)', {
    xaxis: { title: 'PC1 (Organic & Microbial Load)', zeroline: true },
    yaxis: { title: 'PC2 (Physical & Chemical Dynamics)', zeroline: true },
    shapes: shapes,
    annotations: annotations,
    showlegend: false,
  });

  Plotly.newPlot(chartElem, [scoresTrace], layout, { responsive: true, displayModeBar: false });
}
