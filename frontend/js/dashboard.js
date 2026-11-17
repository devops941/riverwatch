/**
 * RiverWatch 2026 Dashboard Controller
 * Powers the interactive map, longitudinal river degradation chart, and live alerts.
 * Completely free of blue: uses Bio-Emerald, Mint Teal, Royal Amethyst, Amber, and Coral Rose.
 */

let mapInstance = null;
let tileLayer = null;

async function initDashboard() {
  try {
    const [stations, wqiData, priorities] = await Promise.all([
      RiverWatch.api('/stations'),
      RiverWatch.api('/wqi?limit=1000'),
      RiverWatch.api('/priority'),
    ]);

    renderKPIs(stations, wqiData);
    renderMap(stations);
    renderProfileChart(stations, wqiData);
    renderTemporalChart(wqiData);
    renderUrgentAlerts(priorities);
  } catch (err) {
    console.error('Failed to load dashboard data:', err);
  }
}

function renderKPIs(stations, wqiData) {
  document.getElementById('kpiStations').innerText = stations.length;
  document.getElementById('kpiSamples').innerText = wqiData.length;

  if (wqiData.length > 0) {
    const wqis = wqiData.map(d => d.wqi).filter(w => w !== null && !isNaN(w));
    const meanWqi = wqis.length > 0 ? (wqis.reduce((a, b) => a + b, 0) / wqis.length).toFixed(1) : 0;
    document.getElementById('kpiMeanWqi').innerText = meanWqi;

    const badge = document.getElementById('kpiWqiBadge');
    if (meanWqi <= 25) {
      badge.className = 'kpi-badge badge-positive';
      badge.innerText = 'Excellent Quality (Class A)';
    } else if (meanWqi <= 50) {
      badge.className = 'kpi-badge badge-positive';
      badge.innerText = 'Good Quality (Class B)';
    } else if (meanWqi <= 75) {
      badge.className = 'kpi-badge badge-warning';
      badge.innerText = 'Poor Quality (Stress)';
    } else {
      badge.className = 'kpi-badge badge-danger';
      badge.innerText = 'High Pollution (Class D/E)';
    }

    const classBCount = wqiData.filter(d => d.cpcb_class === 'Class A' || d.cpcb_class === 'Class B').length;
    const pctClassB = ((classBCount / wqiData.length) * 100).toFixed(1);
    document.getElementById('kpiClassB').innerText = `${pctClassB}%`;
  }
}

function renderMap(stations) {
  const mapElem = document.getElementById('riverMap');
  if (!mapElem) return;

  if (!mapInstance) {
    mapInstance = L.map('riverMap', { zoomControl: true }).setView([27.5, 80.5], 6);
  }

  updateMapTileLayer();

  // Clear existing markers
  mapInstance.eachLayer(layer => {
    if (layer instanceof L.CircleMarker || layer instanceof L.Polyline) {
      mapInstance.removeLayer(layer);
    }
  });

  const latlngs = [];

  stations.forEach(stn => {
    if (stn.lat && stn.lon) {
      latlngs.push([stn.lat, stn.lon]);
      const color = RiverWatch.getWQIColor(stn.wqi_class);
      const isUrgent = (stn.latest_wqi || 0) > 75;

      const marker = L.circleMarker([stn.lat, stn.lon], {
        radius: isUrgent ? 9 : 7,
        fillColor: color,
        color: '#ffffff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.9,
        className: isUrgent ? 'pulsing-marker' : '',
      }).addTo(mapInstance);

      marker.bindPopup(`
        <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 13px; line-height: 1.4;">
          <div style="font-weight: 800; font-size: 14px; margin-bottom: 4px; color: #111827;">${stn.station_name}</div>
          <div style="color: #64748b; font-size: 11px;">Station ID: <strong>${stn.station_id}</strong> | River Flow Order: #${stn.river_order}</div>
          <div style="margin-top: 6px;">
            WQI Value: <strong>${stn.latest_wqi || 'N/A'}</strong> ${RiverWatch.getWQIBadge(stn.wqi_class)}
          </div>
          <div style="margin-top: 4px; font-size: 11px; color: #475569;">
            CPCB Category: <strong>${stn.cpcb_class || 'Evaluating'}</strong>
          </div>
        </div>
      `);
    }
  });

  // Draw connecting river course line (Emerald Green instead of Cyan)
  if (latlngs.length > 1) {
    L.polyline(latlngs, {
      color: '#10b981', // Bio-Emerald Green
      weight: 3,
      opacity: 0.75,
      dashArray: '5, 8',
    }).addTo(mapInstance);

    mapInstance.fitBounds(L.latLngBounds(latlngs).pad(0.15));
  }
}

function updateMapTileLayer() {
  if (!mapInstance) return;
  if (tileLayer) mapInstance.removeLayer(tileLayer);

  const dark = RiverWatch.isDark();
  const tileUrl = dark
    ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

  tileLayer = L.tileLayer(tileUrl, {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(mapInstance);
}

function renderProfileChart(stations, wqiData) {
  const chartElem = document.getElementById('profileChart');
  if (!chartElem) return;

  const stnOrder = [...stations].sort((a, b) => (a.river_order || 0) - (b.river_order || 0));

  // Compute mean WQI per station
  const names = [];
  const means = [];
  const colors = [];

  stnOrder.forEach(stn => {
    const samples = wqiData.filter(d => d.station_id === stn.station_id && d.wqi !== null);
    if (samples.length > 0) {
      const avg = samples.reduce((acc, cur) => acc + cur.wqi, 0) / samples.length;
      names.push(stn.station_name.split(' ')[0]);
      means.push(parseFloat(avg.toFixed(1)));
      colors.push(RiverWatch.getWQIColor(stn.wqi_class));
    }
  });

  const trace = {
    x: names,
    y: means,
    type: 'scatter',
    mode: 'lines+markers',
    marker: { size: 9, color: colors, line: { color: '#ffffff', width: 1.5 } },
    line: { color: '#10b981', width: 3, shape: 'spline' }, // Bio-Emerald
    name: 'Mean WQI',
  };

  // Threshold lines for CPCB categories (No blue!)
  const layout = RiverWatch.getPlotlyLayout('Longitudinal Profile (Clean Headwaters → Downstream Delta)', {
    yaxis: { title: 'WQI Value (Lower is Cleaner)', rangemode: 'tozero' },
    xaxis: { title: 'Stations from Upstream to Downstream' },
    shapes: [
      { type: 'line', y0: 25, y1: 25, x0: 0, x1: 1, xref: 'paper', line: { color: '#10b981', dash: 'dot', width: 1.5 } },
      { type: 'line', y0: 50, y1: 50, x0: 0, x1: 1, xref: 'paper', line: { color: '#34d399', dash: 'dot', width: 1.5 } },
      { type: 'line', y0: 75, y1: 75, x0: 0, x1: 1, xref: 'paper', line: { color: '#f59e0b', dash: 'dot', width: 1.5 } },
      { type: 'line', y0: 100, y1: 100, x0: 0, x1: 1, xref: 'paper', line: { color: '#f43f5e', dash: 'dot', width: 1.5 } },
    ],
  });

  Plotly.newPlot(chartElem, [trace], layout, { responsive: true, displayModeBar: false });
}

function renderTemporalChart(wqiData) {
  const chartElem = document.getElementById('temporalChart');
  if (!chartElem || wqiData.length === 0) return;

  // Group by sample_date monthly average
  const dateMap = {};
  wqiData.forEach(d => {
    if (d.sample_date && d.wqi !== null) {
      const monthKey = d.sample_date.substring(0, 7);
      if (!dateMap[monthKey]) dateMap[monthKey] = [];
      dateMap[monthKey].push(d.wqi);
    }
  });

  const months = Object.keys(dateMap).sort();
  const avgWqis = months.map(m => {
    const arr = dateMap[m];
    return parseFloat((arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(1));
  });

  const trace = {
    x: months,
    y: avgWqis,
    type: 'scatter',
    mode: 'lines',
    fill: 'tozeroy',
    fillcolor: 'rgba(16, 185, 129, 0.12)', // Emerald glow
    line: { color: '#10b981', width: 2.5 },   // Bio-Emerald line
    name: 'Basin Mean WQI',
  };

  const layout = RiverWatch.getPlotlyLayout('Monthly Mean Basin WQI Trajectory', {
    yaxis: { title: 'WQI (Lower is Cleaner)' },
    xaxis: { title: 'Sampling Month' },
  });

  Plotly.newPlot(chartElem, [trace], layout, { responsive: true, displayModeBar: false });
}

function renderUrgentAlerts(priorities) {
  const container = document.getElementById('urgentAlertsList');
  if (!container) return;

  const top3 = priorities.slice(0, 3);
  if (top3.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); font-size: 13px;">No critical alerts currently flagged.</div>`;
    return;
  }

  container.innerHTML = top3.map((p, idx) => `
    <div style="background: var(--bg-surface-hover); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px; border-left: 3px solid ${idx === 0 ? 'var(--accent-rose)' : 'var(--accent-amber)'};">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
        <span style="font-weight: 700; font-size: 13.5px;">${p.station_name || p.station_id}</span>
        <span class="status-pill pill-unsuitable" style="font-size: 10.5px;">Priority #${p.priority_rank}</span>
      </div>
      <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.35;">${p.reason}</div>
      <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">Score: <strong>${p.priority_score}</strong> | Sen Slope: <strong>+${p.wqi_slope}/yr</strong></div>
    </div>
  `).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  initDashboard();
  document.getElementById('refreshBtn')?.addEventListener('click', () => {
    RiverWatch.toast('Refreshing basin telemetry...', 'info');
    initDashboard();
  });
});

window.addEventListener('themeChanged', () => {
  updateMapTileLayer();
  const profileElem = document.getElementById('profileChart');
  const temporalElem = document.getElementById('temporalChart');
  if (profileElem && profileElem.data) {
    Plotly.relayout(profileElem, RiverWatch.getPlotlyLayout('Longitudinal Profile (Clean Headwaters → Downstream Delta)'));
  }
  if (temporalElem && temporalElem.data) {
    Plotly.relayout(temporalElem, RiverWatch.getPlotlyLayout('Monthly Mean Basin WQI Trajectory'));
  }
});
