# 🌊 RiverWatch: River Health Intelligence & Multi-Indicator Pollution Analysis

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.162.0-009688.svg)](https://fastapi.tiangolo.com)
[![Pytest](https://img.shields.io/badge/pytest-36%20passed-brightgreen.svg)](https://pytest.org)
[![Design](https://img.shields.io/badge/UI-2026%20Glassmorphism%20Bento-cyan.svg)](#)

RiverWatch is a Python 3.12 environmental intelligence platform designed to ingest multi-source river water quality records (CPCB NWMP, India-WRIS, state pollution control boards), validate and sanitize raw laboratory data, compute weighted-arithmetic Water Quality Index (WQI), evaluate CPCB Designated Best Use compliance, detect multi-decadal trends with Mann-Kendall and Sen's slope, conduct Principal Component Analysis (PCA), rank pollution drivers, prioritize future station sampling, and generate automated executive PDF audit reports.

---

## 🌟 2026 Modern Design System & User Interface

The web interface is built using pure **HTML5, CSS3, and vanilla JavaScript** with **Plotly.js** and **Leaflet.js** (strictly no Streamlit):
- **Obsidian Dark & Ambient Light Modes**: Persistent theme switcher with radial mesh glow lighting.
- **Glassmorphic Bento Grid**: Frosted glass surfaces (`backdrop-filter: blur(20px)`), subtle borders (`rgba(255,255,255,0.08)`), and interactive micro-animations.
- **Geospatial River Map (Leaflet)**: Dark Matter / Positron vector tiles, pulsing radar indicators on high-priority stations, and dynamic river course polylines.
- **Plotly.js Interactive Visualizations**: Theme-synced longitudinal river degradation profiles, time-series thresholds, seasonal boxplots, Spearman correlation heatmaps, PCA scree variance charts, and 2D biplots.
- **Live Reactive Modeler**: Real-time slider weights recomputing station sampling priorities dynamically with debounced backend synchronization.
- **Immutable Audit Trail**: Inline data editing with logged timestamps, old values, new values, and operator justification strings.

---

## 🏗️ System Architecture & Workflow

```
Raw CSV / Excel Upload or Synthetic Generator (8 Stns x 8 Yrs)
        │
        ▼
[1] Ingest & Alias Mapping (config/aliases.yaml)
        │
        ▼
[2] Multi-Rule Validator (10 Rules: dates, dtypes, range, 5-MAD outliers, coords, units)
        │
        ▼
[3] Interactive Review (Inline Fix / Ignore / Exclude Row + Audit Trail)
        │
        ▼
[4] Preprocessing (Censored <DL -> DL/2, Unit Normalization, Duplicate Handling)
        │
        ▼
[5] SQLite Database (SQLAlchemy 2.0 ORM: 16 Relational Tables)
        │
        ▼
[6] Analytical Engine (Python Modules):
        ├── Weighted-Arithmetic WQI (Brown et al., 1970) + Equal Weights Sensitivity
        ├── CPCB Designated Best Use Criteria (Classes A through E) + Violations
        ├── Mann-Kendall Trend Test + Sen's Slope (pymannkendall, Hamed-Rao correction)
        ├── Spearman Correlation Matrix + Benjamini-Hochberg FDR Multiple Testing
        ├── Principal Component Analysis (scikit-learn PCA, Scree Plot, 2D Biplot)
        ├── Pollution Driver Ranking (PCA Loading + Correlation + Period Change)
        └── Sampling Priority Score (WQI 12m, Sen Slope, Violations, Recency, Gaps)
        │
        ▼
[7] FastAPI REST API + 2026 Modern Bento Grid Web Dashboard
        │
        ▼
[8] Export Layer: Cleaned CSV, Multi-Sheet Excel (.xlsx), and Executive PDF Report (PyMuPDF)
```

---

## 📂 Project Structure

```
river_watch/
├── PROJECT_SPEC_RIVERWATCH.md     # Original comprehensive project specifications
├── README.md                      # Complete system documentation
├── requirements.txt               # Pinned, tested Python 3.12 dependencies
├── pytest.ini                     # Pytest configuration
├── config/
│   ├── parameters.yaml            # Water quality standards, ideal values, valid limits
│   ├── aliases.yaml               # Header alias lookup table for real-world lab sheets
│   └── analysis.yaml              # CPCB classes, WQI thresholds, priority weights
├── data/
│   ├── sample/                    # Synthetic clean, synthetic raw, and template CSVs
│   ├── uploads/                   # Staged user uploads
│   └── riverwatch.db              # SQLite relational database
├── src/
│   ├── data/
│   │   ├── db.py                  # SQLAlchemy 2.0 models & connection manager
│   │   ├── synthetic.py           # Synthetic river generator with injected errors
│   │   ├── ingest.py              # File reader, header normalization, template generator
│   │   ├── validate.py            # Section 6.1 validation rules engine
│   │   └── preprocess.py          # Unit conversion, duplicate resolution, censored data
│   ├── analysis/
│   │   ├── wqi.py                 # Weighted-arithmetic WQI & sensitivity checks
│   │   ├── compliance.py          # CPCB Designated Best Use classification
│   │   ├── trend.py               # Mann-Kendall & Sen's slope trend test
│   │   ├── correlation.py         # Spearman correlation & Benjamini-Hochberg FDR
│   │   ├── pca.py                 # PCA loadings, explained variance, sample scores
│   │   ├── drivers.py             # Multi-signal composite pollution driver ranking
│   │   └── priority.py            # Station sampling prioritization modeler
│   ├── report/
│   │   ├── generate.py            # PDF (PyMuPDF) & HTML report generation engine
│   │   └── template.html.j2       # Jinja2 executive report template
│   └── pipeline.py                # End-to-end command-line runner
├── backend/
│   ├── main.py                    # FastAPI entrypoint, middleware, static mounting
│   ├── deps.py                    # Database session dependency injection
│   ├── schemas.py                 # Pydantic v2 request/response schemas
│   └── routers/
│       ├── uploads.py             # File upload, issue audit, commit, sample load
│       ├── analysis.py            # WQI, compliance, trends, correlation, PCA, drivers, priority
│       ├── stations.py            # Station geospatial metadata & time-series
│       ├── export.py              # CSV/Excel exports, record browser, value patch
│       └── reports.py             # PDF executive report generator & downloads
├── frontend/
│   ├── index.html                 # 2026 River Basin Dashboard
│   ├── upload.html                # Dataset Ingestion & Validation Anomaly Resolver
│   ├── stations.html              # Monitoring Station Explorer & Seasonal Dynamics
│   ├── trends.html                # Mann-Kendall Trends & Sen's Slope Rates
│   ├── drivers.html               # Pollution Drivers, Spearman Heatmap & PCA Biplot
│   ├── priority.html              # Sampling Prioritization Engine with Live Sliders
│   ├── records.html               # Processed Records & Corrections Audit Trail
│   ├── export.html                # CSV/Excel Exports & Executive PDF Reports
│   ├── css/
│   │   └── style.css              # 2026 Obsidian Glassmorphic Design System
│   └── js/
│       ├── app.js                 # Global API client, theme manager, toast alerts
│       ├── dashboard.js           # Leaflet map & longitudinal degradation chart
│       ├── upload.js              # Drag-drop uploader & inline issue resolver
│       ├── stations.js            # Time-series trajectory & seasonal boxplots
│       ├── trends.js              # Sen's slope bar chart & statistical tables
│       ├── drivers.js             # Driver cards, correlation matrix, scree plot
│       ├── priority.js            # Interactive priority re-ranking sliders
│       ├── records.js             # Paginated records table & modal editor
│       └── export.js              # Download triggers & report compiler
├── tests/
│   ├── test_validation.py         # Unit tests for 10 validation rules
│   ├── test_wqi_compliance.py     # Hand-calculated WQI tests & CPCB edges
│   ├── test_trends.py             # Mann-Kendall trend tests & Sen's slope
│   ├── test_pca_correlation.py    # Spearman correlation, FDR, & PCA decomposition
│   ├── test_priority.py           # Station priority formula & normalization
│   ├── test_api.py                # Backend REST endpoints integration suite
│   └── test_pipeline.py           # CLI pipeline & report compilation tests
└── outputs/
    ├── riverwatch_report.html     # Rendered executive HTML report
    ├── riverwatch_report.pdf      # Publication-quality executive PDF report
    └── riverwatch_report_chart.png# Embedded longitudinal degradation profile
```

---

## ⚡ Quick Start & Installation

### 1. Requirements & Setup
Ensure you are using **Python 3.11 or 3.12**:

```powershell
# Clone or navigate to repository
cd d:\python_projects\river_watch

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the End-to-End Pipeline (CLI)
Seed the SQLite database and calculate analytical indices on synthetic data:

```powershell
python -m src.pipeline --source synthetic
```

Or run on your own monitoring CSV / Excel file:

```powershell
python -m src.pipeline --source file --path path\to\water_data.csv
```

### 3. Launch the Web Application
Start the FastAPI server:

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open your browser at **`http://localhost:8000`** to access the 2026 River Basin Dashboard.
API documentation is available at **`http://localhost:8000/docs`**.

---

## 🧪 Running the Test Suite

Run all 36 unit and integration tests with `pytest`:

```powershell
python -m pytest -v
```

Run test coverage:

```powershell
python -m pytest --cov=src --cov=backend tests/
```

---

## 📐 Mathematical & Statistical Methodologies

### 1. Water Quality Index (Brown et al., 1970)
For each sample with available parameters $i \in \{1..n\}$:
- Standard permissible value: $S_i$ (from `config/parameters.yaml`).
- Ideal value: $V_{\text{ideal}} = 0$ for all parameters except $\text{pH} = 7.0$ and $\text{DO} = 14.6 \text{ mg/L}$.
- Proportionality constant:
  $$K = \frac{1}{\sum_{i=1}^n \frac{1}{S_i}}$$
- Unit weight:
  $$W_i = \frac{K}{S_i}, \quad \text{where } \sum_{i=1}^n W_i = 1.0$$
- Quality rating:
  $$q_i = 100 \times \left| \frac{V_i - V_{\text{ideal}}}{S_i - V_{\text{ideal}}} \right|$$
  *(For Dissolved Oxygen, the inverse formulation is applied: $q_{\text{DO}} = 100 \times \frac{14.6 - V_{\text{DO}}}{14.6 - 5.0}$)*.
- Weighted Arithmetic Index:
  $$\text{WQI} = \sum_{i=1}^n q_i W_i$$
- Categorization: **0–25 (Excellent)**, **26–50 (Good)**, **51–75 (Poor)**, **76–100 (Very Poor)**, **> 100 (Unsuitable)**.

### 2. CPCB Designated Best Use Compliance
Compares measured DO, BOD, pH, and Total Coliform against official criteria:
- **Class A**: $\text{DO} \ge 6.0$, $\text{BOD} \le 2.0$, $\text{pH} \in [6.5, 8.5]$, $\text{Total Coliform} \le 50 \text{ MPN/100mL}$.
- **Class B**: $\text{DO} \ge 5.0$, $\text{BOD} \le 3.0$, $\text{pH} \in [6.5, 8.5]$, $\text{Total Coliform} \le 500 \text{ MPN/100mL}$.
- **Class C**: $\text{DO} \ge 4.0$, $\text{BOD} \le 3.0$, $\text{pH} \in [6.0, 9.0]$, $\text{Total Coliform} \le 5000 \text{ MPN/100mL}$.
- **Class D**: $\text{DO} \ge 4.0$, $\text{pH} \in [6.5, 8.5]$, $\text{Free Ammonia} \le 1.2 \text{ mg/L}$.
- **Class E**: $\text{pH} \in [6.0, 8.5]$, $\text{Conductivity} \le 2250 \text{ µS/cm}$.

### 3. Non-Parametric Trend Testing
- **Mann-Kendall Test**: Tests for monotonic trends in non-normal, skewed monthly data.
- **Hamed-Rao Variance Correction**: Adjusts test statistic for lag-1 serial autocorrelation.
- **Sen's Slope Estimator**: Median of all pairwise slopes $\frac{x_j - x_k}{j - k}$, converted to annual rate (units/year).
- **Domain Interpretation**: Evaluated against parameter `worse_if` policy (e.g. rising BOD is worsening; rising DO is improving).

### 4. Principal Component Analysis (PCA) & Driver Ranking
- Skewed parameters (coliform, turbidity) undergo logarithmic transformation: $x' = \log_{10}(x + 1)$.
- Z-score standardization: $z = \frac{x - \mu}{\sigma}$.
- Multi-signal Composite Driver Ranking:
  $$\text{Driver Score} = 0.35 \times \text{norm}(S_{\text{PCA}}) + 0.35 \times \text{norm}(S_{\text{corr}}) + 0.30 \times \text{norm}(S_{\text{change}})$$

### 5. Sampling Priority Allocation
Stations are ranked to optimize sampling logistics and early intervention:
$$\text{Priority} = 0.30 \cdot \text{norm}(\text{WQI}_{12m}) + 0.25 \cdot \text{norm}(\text{Sen Slope}) + 0.20 \cdot \text{norm}(\text{Violations}) + 0.15 \cdot \text{norm}(\text{Recency}) + 0.10 \cdot \text{norm}(\text{Gaps})$$

---

## 📄 License & Attribution
Developed for the River Health Intelligence Project adhering strictly to CPCB and BIS standards. Designed and engineered for 2026 environmental telemetry standards.
