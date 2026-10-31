// 13F Terminal — data layer (Phase 5: hydrated by bootstrapFromJson)
// Mock data removed; bootstrap fetches /data/*.json (produced by `thirteen-f export`).
// See _claude_docs/FRONTEND_PARITY.md for which fields are exporter-owned vs derived.

let QUARTERS = [];      // ["2024Q2", ...] — exporter quarters.json[i].key
let Q_LABELS = [];      // ["Q2'24", ...] — exporter quarters.json[i].label
let Q_DATES = [];       // ["2024-06-30", ...] — exporter quarters.json[i].date (ISO; /api/ask period에 사용)
let STOCKS = [];        // [{t, n, s, i?, mc?, px:[N], yld?}] — exporter stocks.json
let STOCK_MAP = {};     // {ticker: stock}
let MANAGERS = [];      // [{id, name, firm, style, color, avatar, note}]
let MGR_MAP = {};       // {id: manager}
let HOLDINGS = {};      // {mgrId: {ticker: [shares_M_per_quarter]}}
let HOLDINGS_UNMAPPED = {}; // {mgrId: {cusip: {name_of_issuer, shares:[...]}}}
let BACKTESTS = [];     // [{run_id, name, equity, dd, qrets, holdingsLog, metrics}]
let TARGETS = null;     // targets.json — {as_of, rule, recommended, strategies:[{name, type, period, positions, sells, metrics}]} (Plan 탭)
let LLM_SUMMARY = {};   // {[period]: {headline, top_signals}}
let META = {};          // {generated_at, latest_period, data_version, ...}

const SECTOR_COLORS = {
  Tech: "#1d6dc8",
  Technology: "#1d6dc8",
  Financials: "#6d28d9",
  "Financial Services": "#6d28d9",
  Energy: "#b45309",
  Consumer: "#0e8a3b",
  "Consumer Cyclical": "#0e8a3b",
  "Consumer Defensive": "#0e8a3b",
  Healthcare: "#0e7490",
  Other: "#475569",
};

// Daily-ish price series for charting (12 quarters, 65 weekly samples)
function buildWeeklyPrices(quarterly, drift = 0) {
  // interpolate between quarter-end prices with mild noise; result length = (q-1)*8 + 1
  const out = [];
  let s = 1;
  for (let i = 0; i < quarterly.length - 1; i++) {
    const a = quarterly[i], b = quarterly[i + 1];
    for (let j = 0; j < 8; j++) {
      const f = j / 8;
      const interp = a + (b - a) * f;
      const noise = Math.sin(s * 1.7 + i * 1.3) * (a + b) * 0.008;
      out.push(+(interp + noise).toFixed(2));
      s++;
    }
  }
  out.push(quarterly[quarterly.length - 1]);
  return out;
}
// pxWeekly is rebuilt inside bootstrapFromJson once STOCKS is hydrated.

// ─── Derived helpers ────────────────────────────────────────────────────────
// classify action between two quarters
function classifyAction(prev, curr) {
  if (prev === 0 && curr === 0) return null;
  if (prev === 0 && curr > 0) return "NEW";
  if (prev > 0 && curr === 0) return "EXIT";
  const ratio = curr / prev;
  if (ratio >= 1.05) return "ADD";
  if (ratio <= 0.95) return "CUT";
  return "HOLD";
}

// position-level: dollar value, weight
function positionValue(shares, ticker, qIdx) {
  const s = STOCK_MAP[ticker];
  if (!s) return 0;
  return shares * s.px[qIdx]; // shares in millions * price -> $M
}

// manager total at a quarter (sum of held position values)
function managerTotal(mgrId, qIdx) {
  const h = HOLDINGS[mgrId] || {};
  let total = 0;
  for (const tk in h) {
    total += positionValue(h[tk][qIdx], tk, qIdx);
  }
  return total;
}

// portfolio at quarter: array of { ticker, shares, prevShares, value, weight, action, deltaWeight }
function managerPortfolio(mgrId, qIdx) {
  const h = HOLDINGS[mgrId] || {};
  const total = managerTotal(mgrId, qIdx);
  const totalPrev = qIdx > 0 ? managerTotal(mgrId, qIdx - 1) : total;
  const rows = [];
  for (const tk in h) {
    if (!STOCK_MAP[tk]) continue; // skip unknown tickers
    const shares = h[tk][qIdx];
    const prev = qIdx > 0 ? h[tk][qIdx - 1] : 0;
    if (shares === 0 && prev === 0) continue;
    const value = positionValue(shares, tk, qIdx);
    const valuePrev = qIdx > 0 ? positionValue(prev, tk, qIdx - 1) : 0;
    const weight = total > 0 ? value / total : 0;
    const weightPrev = totalPrev > 0 ? valuePrev / totalPrev : 0;
    const action = classifyAction(prev, shares);
    rows.push({
      ticker: tk,
      stock: STOCK_MAP[tk],
      shares, prevShares: prev,
      value, valuePrev,
      weight, weightPrev,
      deltaWeight: weight - weightPrev,
      deltaShares: shares - prev,
      action,
      held: shares > 0,
      seriesShares: h[tk],
    });
  }
  rows.sort((a, b) => b.weight - a.weight);
  return rows;
}

// all activity in a quarter (across managers): array of { mgrId, ticker, action, weight, deltaWeight, value, deltaValue }
function quarterActivity(qIdx) {
  const acts = [];
  for (const mgrId in HOLDINGS) {
    const port = managerPortfolio(mgrId, qIdx);
    for (const r of port) {
      if (r.action && r.action !== "HOLD") {
        acts.push({
          mgrId,
          mgr: MGR_MAP[mgrId],
          ticker: r.ticker,
          stock: r.stock,
          action: r.action,
          weight: r.weight,
          deltaWeight: r.deltaWeight,
          value: r.value,
          deltaValue: r.value - r.valuePrev,
        });
      }
    }
  }
  return acts;
}

// for a given ticker, who holds it across quarters
function tickerHolders(ticker, qIdx) {
  const arr = [];
  for (const mgrId in HOLDINGS) {
    const series = HOLDINGS[mgrId][ticker];
    if (!series) continue;
    const shares = series[qIdx];
    if (shares === 0) continue;
    const total = managerTotal(mgrId, qIdx);
    const value = positionValue(shares, ticker, qIdx);
    const weight = total > 0 ? value / total : 0;
    const prev = qIdx > 0 ? series[qIdx - 1] : 0;
    const action = classifyAction(prev, shares);
    arr.push({
      mgrId,
      mgr: MGR_MAP[mgrId],
      shares,
      value,
      weight,
      prevShares: prev,
      action,
      series,
    });
  }
  arr.sort((a, b) => b.weight - a.weight);
  return arr;
}

// crowdedness for a ticker — how many managers hold at qIdx
function tickerCrowdedness(ticker, qIdx) {
  let n = 0, sumWeight = 0;
  const holders = tickerHolders(ticker, qIdx);
  return { n: holders.length, holders };
}

// summary: count by action across all managers for a quarter
function quarterSummary(qIdx) {
  const acts = quarterActivity(qIdx);
  const by = { NEW: 0, ADD: 0, CUT: 0, EXIT: 0 };
  for (const a of acts) by[a.action] = (by[a.action] || 0) + 1;
  return { acts, by };
}

// Find the "spotlight" move for the latest quarter — biggest abs deltaValue
function spotlight(qIdx) {
  const acts = quarterActivity(qIdx);
  if (acts.length === 0) return null;
  return acts.slice().sort((a, b) => Math.abs(b.deltaValue) - Math.abs(a.deltaValue))[0];
}

// Strategy type metadata for UI
const STRATEGY_TYPES = [
  {
    type: "SingleManagerClone",
    name: "Single Manager Clone",
    desc: "한 매니저의 Top N 포지션을 그대로 복제",
    color: "#1d6dc8",
  },
  {
    type: "MultiManager",
    name: "Multi-Manager Blend",
    desc: "여러 매니저의 Top 포지션을 합쳐 점수 순으로 선정",
    color: "#0e7490",
  },
  {
    type: "NewBuyOnly",
    name: "New Buys Only",
    desc: "이번 분기 신규 매수·추가 매수만 — 모멘텀 추종",
    color: "#0e8a3b",
  },
  {
    type: "ScoreTopK",
    name: "Score Top K",
    desc: "Conviction × #holders × Persistence 점수 상위 K",
    color: "#7c3aed",
  },
  {
    type: "ConvictionFollow",
    name: "Conviction Follow",
    desc: "매니저 포트의 비중이 임계값 이상인 모든 종목",
    color: "#b45309",
  },
  {
    type: "ConsensusTopK",
    name: "Consensus Top K",
    desc: "최소 N명이 보유한 종목 중 # holders 상위 K",
    color: "#c8261e",
  },
  {
    type: "Ensemble",
    name: "Ensemble",
    desc: "여러 전략을 가중치로 블렌드",
    color: "#0a0d14",
  },
];

const STRATEGY_TYPE_MAP = Object.fromEntries(STRATEGY_TYPES.map(s => [s.type, s]));

// =============================================================================
// Bootstrap — fetch /data/*.json into module-level state (Phase 5 C1)
// =============================================================================

async function bootstrapFromJson(baseUrl = "/data") {
  async function fetchJson(path, fallback) {
    try {
      const r = await fetch(`${baseUrl}/${path}`);
      if (!r.ok) {
        // I6: 어떤 파일이 누락됐는지 명확히 (ErrorScreen에 표시)
        const err = new Error(`${path}: HTTP ${r.status}`);
        err.missingFile = path;
        err.httpStatus = r.status;
        throw err;
      }
      return await r.json();
    } catch (e) {
      if (fallback !== undefined) return fallback;
      if (!e.missingFile) {
        e.missingFile = path; // 네트워크 오류 등에도 어떤 파일 시도 중이었는지 정보 보존
      }
      throw e;
    }
  }

  const [meta, quarters, managers, stocks, holdings, holdingsUnmapped, backtests, llm, targets] = await Promise.all([
    fetchJson("meta.json"),
    fetchJson("quarters.json"),
    fetchJson("managers.json"),
    fetchJson("stocks.json"),
    fetchJson("holdings.json"),
    fetchJson("holdings_unmapped.json", {}),
    fetchJson("backtest.json", []),
    fetchJson("llm_summary.json", {}),
    fetchJson("targets.json", null),
  ]);

  META = meta;
  QUARTERS = quarters.map(q => q.key);
  Q_LABELS = quarters.map(q => q.label);
  Q_DATES = quarters.map(q => q.date);
  STOCKS = stocks;
  STOCK_MAP = Object.fromEntries(STOCKS.map(s => [s.t, s]));
  STOCKS.forEach(st => {
    if (Array.isArray(st.px) && st.px.length > 1) {
      st.pxWeekly = buildWeeklyPrices(st.px);
    } else {
      st.pxWeekly = st.px ? st.px.slice() : [];
    }
  });
  MANAGERS = managers;
  MGR_MAP = Object.fromEntries(MANAGERS.map(m => [m.id, m]));
  HOLDINGS = holdings;
  HOLDINGS_UNMAPPED = holdingsUnmapped;
  BACKTESTS = backtests;
  LLM_SUMMARY = llm;
  TARGETS = targets;

  Object.assign(window, {
    QUARTERS, Q_LABELS, Q_DATES, STOCKS, STOCK_MAP, MANAGERS, MGR_MAP,
    HOLDINGS, HOLDINGS_UNMAPPED, BACKTESTS, LLM_SUMMARY, TARGETS, META,
  });
  return META;
}

// Lazy daily price fetch — called per-ticker by StockScreen (Phase 5 C3).
// Returns {date:[], close:[]} fallback so consumers can treat as iterable.
async function fetchDailyPx(ticker, baseUrl = "/data") {
  try {
    const r = await fetch(`${baseUrl}/prices/${encodeURIComponent(ticker)}.json`);
    if (!r.ok) return { date: [], close: [] };
    return await r.json();
  } catch {
    return { date: [], close: [] };
  }
}

// expose globals + bootstrap (loaded as a plain script tag)
Object.assign(window, {
  QUARTERS, Q_LABELS, Q_DATES, STOCKS, STOCK_MAP, MANAGERS, MGR_MAP, HOLDINGS,
  HOLDINGS_UNMAPPED, BACKTESTS, LLM_SUMMARY, TARGETS, META, SECTOR_COLORS,
  classifyAction, positionValue, managerTotal, managerPortfolio,
  quarterActivity, tickerHolders, tickerCrowdedness, quarterSummary, spotlight,
  STRATEGY_TYPES, STRATEGY_TYPE_MAP,
  bootstrapFromJson, fetchDailyPx,
});
