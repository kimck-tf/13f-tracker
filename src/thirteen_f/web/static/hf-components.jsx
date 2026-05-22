// 13F Terminal — shared hi-fi components
// Real-data charts (line/treemap/bar/spark), table, sidebar, badges, formatters.

const { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } = React;

// ─── Formatters ────────────────────────────────────────────────────────────
function fmtMoney(v, opts = {}) {
  const { signed = false, compact = true, dollars = true, decimals = 1 } = opts;
  if (v == null || isNaN(v)) return "—";
  const sign = v >= 0 ? signed ? "+" : "" : "−";
  const abs = Math.abs(v);
  const pre = dollars ? "$" : "";
  if (!compact) return sign + pre + abs.toLocaleString("en-US", { maximumFractionDigits: decimals });
  if (abs >= 1e9) return sign + pre + (abs / 1e9).toFixed(decimals) + "B";
  if (abs >= 1e6) return sign + pre + (abs / 1e6).toFixed(decimals) + "M";
  if (abs >= 1e3) return sign + pre + (abs / 1e3).toFixed(decimals) + "K";
  return sign + pre + abs.toFixed(decimals);
}
function fmtPct(v, opts = {}) {
  const { signed = false, decimals = 2 } = opts;
  if (v == null || isNaN(v)) return "—";
  const sign = v >= 0 ? signed ? "+" : "" : "−";
  return sign + Math.abs(v * 100).toFixed(decimals) + "%";
}
function fmtNum(v, decimals = 0) {
  if (v == null || isNaN(v)) return "—";
  return v.toLocaleString("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}
function fmtShares(v) {
  if (v == null) return "—";
  if (v >= 1) return v.toFixed(1) + "M";
  return (v * 1000).toFixed(0) + "K";
}

// ─── Badge ─────────────────────────────────────────────────────────────────
function Badge({ kind, children, sm }) {
  const variant = {
    NEW: "pos", ADD: "pos", HOLD: "", CUT: "neg", EXIT: "neg"
  }[kind] || "";
  return <span className={"hf-badge " + variant + (sm ? " sm" : "")}>{children || kind}</span>;
}

// ─── Avatar ────────────────────────────────────────────────────────────────
function Avatar({ mgr, sz = 22 }) {
  if (!mgr) return null;
  return (
    <span className="hf-avatar" style={{ width: sz, height: sz, background: mgr.color, fontSize: sz * 0.42 }}>
      {mgr.avatar}
    </span>);

}

// ─── ChangeNum (signed % or $) ─────────────────────────────────────────────
function Delta({ value, kind = "pct", decimals = 2, bold = false }) {
  if (value == null) return <span className="hf-tx mono num muted">—</span>;
  const v = value;
  const cls = v >= 0 ? "pos" : "neg";
  const txt = kind === "pct" ? fmtPct(v, { signed: true, decimals }) : fmtMoney(v, { signed: true, decimals });
  return <span className={"hf-tx mono num " + cls + (bold ? " b" : "")}>{txt}</span>;
}

// ─── Sparkline ─────────────────────────────────────────────────────────────
function Spark({ values, w = 80, h = 22, color, signedTrend = true, fill = false }) {
  if (!values || values.length < 2) return <svg width={w} height={h}></svg>;
  const min = Math.min(...values),max = Math.max(...values);
  const range = max - min || 1;
  const trend = values[values.length - 1] - values[0];
  const stroke = color || (signedTrend ? trend >= 0 ? "var(--pos)" : "var(--neg)" : "var(--ink-2)");
  const pts = values.map((v, i) => [
  i / (values.length - 1) * (w - 2) + 1,
  h - 2 - (v - min) / range * (h - 4)]
  );
  const d = "M " + pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L ");
  const dFill = d + ` L ${w - 1},${h - 1} L 1,${h - 1} Z`;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {fill && <path d={dFill} fill={stroke} opacity="0.1" />}
      <path d={d} stroke={stroke} fill="none" strokeWidth="1.2" />
    </svg>);

}

// ─── Line chart with hover tooltip ─────────────────────────────────────────
function LineChart({ series, labels, w = 600, h = 220, padding = { l: 44, r: 16, t: 12, b: 24 }, formatY = (v) => v.toFixed(2), formatX = (i) => i, onHover, focusIdx, asPct = false }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null); // {idx, x, y}
  const cw = w - padding.l - padding.r;
  const ch = h - padding.t - padding.b;
  const n = series[0]?.values.length || 0;

  // Compute scales
  const allVals = series.flatMap((s) => s.values);
  let yMin = Math.min(...allVals);
  let yMax = Math.max(...allVals);
  const pad = (yMax - yMin) * 0.08;
  yMin -= pad;yMax += pad;
  const xScale = (i) => padding.l + i / Math.max(1, n - 1) * cw;
  const yScale = (v) => padding.t + (1 - (v - yMin) / (yMax - yMin || 1)) * ch;

  // Mouse handler
  function onMove(e) {
    const rect = ref.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const idx = Math.round((x - padding.l) / cw * (n - 1));
    if (idx >= 0 && idx < n) {
      setHover({ idx, x: xScale(idx) });
      onHover && onHover(idx);
    }
  }
  function onLeave() {
    setHover(null);
    onHover && onHover(null);
  }

  // Y-axis ticks
  const ticks = [yMin, yMin + (yMax - yMin) * 0.25, yMin + (yMax - yMin) * 0.5, yMin + (yMax - yMin) * 0.75, yMax];
  // X-axis ticks (use formatX)
  const xTicks = [];
  const xLabelEvery = Math.max(1, Math.ceil(n / 8));
  for (let i = 0; i < n; i += xLabelEvery) xTicks.push(i);

  return (
    <div className="hf-chart" style={{ position: "relative", width: w, height: h }} ref={ref}
    onMouseMove={onMove} onMouseLeave={onLeave}>
      <svg width={w} height={h} style={{ display: "block" }}>
        {/* Grid + y-axis labels */}
        {ticks.map((t, i) =>
        <g key={"y" + i}>
            <line x1={padding.l} x2={w - padding.r} y1={yScale(t)} y2={yScale(t)} stroke="var(--rule-soft)" strokeWidth="0.5" strokeDasharray={i === 0 || i === ticks.length - 1 ? null : "2 3"} />
            <text x={padding.l - 6} y={yScale(t) + 3} fontSize="10" fontFamily="var(--mono)" textAnchor="end" fill="var(--ink-3)">{formatY(t)}</text>
          </g>
        )}
        {/* X labels */}
        {xTicks.map((i) =>
        <text key={"x" + i} x={xScale(i)} y={h - padding.b + 14} fontSize="10" fontFamily="var(--mono)" textAnchor="middle" fill="var(--ink-3)">
            {formatX(i)}
          </text>
        )}
        {/* Series lines */}
        {series.map((s, idx) => {
          const d = "M " + s.values.map((v, i) => xScale(i).toFixed(1) + "," + yScale(v).toFixed(1)).join(" L ");
          return (
            <g key={"s" + idx}>
              {s.fill && <path d={d + ` L ${xScale(n - 1)},${yScale(yMin)} L ${xScale(0)},${yScale(yMin)} Z`} fill={s.color} opacity="0.06" />}
              <path d={d} stroke={s.color} fill="none" strokeWidth={s.width || 1.6} strokeDasharray={s.dashed ? "4 3" : null} />
            </g>);

        })}
        {/* Hover line */}
        {hover != null &&
        <g>
            <line x1={hover.x} x2={hover.x} y1={padding.t} y2={h - padding.b} stroke="var(--ink)" strokeWidth="0.5" strokeDasharray="2 2" />
            {series.map((s, idx) =>
          <circle key={"c" + idx} cx={hover.x} cy={yScale(s.values[hover.idx])} r="3.5" fill="var(--bg-tile)" stroke={s.color} strokeWidth="1.5" />
          )}
          </g>
        }
        {focusIdx != null && hover == null &&
        <line x1={xScale(focusIdx)} x2={xScale(focusIdx)} y1={padding.t} y2={h - padding.b} stroke="var(--ink-3)" strokeWidth="0.5" strokeDasharray="3 3" />
        }
      </svg>
      {/* Tooltip */}
      {hover != null &&
      <div className="hf-chart-tip" style={{ left: hover.x + 8, top: padding.t }}>
          <div className="hf-chart-tip-x mono">{formatX(hover.idx)}</div>
          {series.map((s, idx) =>
        <div key={idx} className="hf-chart-tip-row">
              <span className="hf-chart-tip-sw" style={{ background: s.color }}></span>
              <span className="hf-chart-tip-l">{s.label}</span>
              <span className="hf-chart-tip-v mono">{asPct ? fmtPct(s.values[hover.idx] - 1, { signed: true, decimals: 1 }) : formatY(s.values[hover.idx])}</span>
            </div>
        )}
        </div>
      }
      {/* Legend */}
      {labels &&
      <div className="hf-chart-legend">
          {series.map((s, i) =>
        <span key={i} className="hf-chart-legend-it">
              <span className="hf-chart-legend-sw" style={{ background: s.color, borderStyle: s.dashed ? "dashed" : "solid" }}></span>
              {s.label}
            </span>
        )}
        </div>
      }
    </div>);

}

// ─── Treemap (real data) ───────────────────────────────────────────────────
function Treemap({ items, w = 480, h = 320, onSelect, selectedKey }) {
  // items: [{ key, label, sublabel, value, color, _meta }]
  const layout = useMemo(() => squarify(items, w, h), [items, w, h]);
  return (
    <svg width={w} height={h} style={{ display: "block" }} className="hf-tmap">
      {layout.map((r) => {
        const isSel = selectedKey && r.item.key === selectedKey;
        const fill = r.item.color || "var(--accent)";
        return (
          <g key={r.item.key} className="hf-tmap-cell" onClick={() => onSelect && onSelect(r.item)} style={{ cursor: onSelect ? "pointer" : "default" }}>
            <rect x={r.x + 0.5} y={r.y + 0.5} width={r.w - 1} height={r.h - 1}
            fill={fill}
            opacity={isSel ? 0.32 : 0.14}
            stroke={isSel ? fill : "var(--rule)"}
            strokeWidth={isSel ? 1.5 : 0.5} />
            
            {r.w > 36 && r.h > 18 &&
            <text x={r.x + 6} y={r.y + 14} fontSize="11" fontFamily="var(--mono)" fontWeight="600" fill="var(--ink)">{r.item.label}</text>
            }
            {r.w > 50 && r.h > 32 &&
            <text x={r.x + 6} y={r.y + 26} fontSize="10" fontFamily="var(--mono)" fill="var(--ink-2)">{r.item.sublabel}</text>
            }
            {r.w > 80 && r.h > 50 && r.item.note &&
            <text x={r.x + 6} y={r.y + 38} fontSize="9" fontFamily="var(--sans)" fill="var(--ink-3)">{r.item.note}</text>
            }
          </g>);

      })}
    </svg>);

}
function squarify(items, w, h) {
  // simple slice-and-dice
  const sorted = items.slice().sort((a, b) => b.value - a.value);
  const total = sorted.reduce((a, b) => a + b.value, 0);
  if (total === 0) return [];
  const out = [];
  let x = 0,y = 0,rowW = w,rowH = h,dir = "h",i = 0;
  while (i < sorted.length) {
    const rem = sorted.slice(i).reduce((a, b) => a + b.value, 0);
    const it = sorted[i];
    if (dir === "h") {
      const colW = it.value / rem * rowW;
      out.push({ item: it, x, y, w: colW, h: rowH });
      x += colW;rowW -= colW;
    } else {
      const colH = it.value / rem * rowH;
      out.push({ item: it, x, y, w: rowW, h: colH });
      y += colH;rowH -= colH;
    }
    i++;
    if (i > 0 && i % 3 === 0) dir = dir === "h" ? "v" : "h";
  }
  return out;
}

// ─── Bar chart (real data) ─────────────────────────────────────────────────
function BarChart({ values, w = 560, h = 100, labels, signed = true, colors, onHover, formatY = (v) => v.toFixed(1) }) {
  const n = values.length;
  const bw = (w - 16) / n - 2;
  const max = Math.max(...values.map((v) => Math.abs(v)));
  if (signed) {
    return (
      <svg width={w} height={h} style={{ display: "block" }}>
        <line x1="0" x2={w} y1={h / 2} y2={h / 2} stroke="var(--rule)" strokeWidth="0.5" />
        {values.map((v, i) => {
          const isPos = v >= 0;
          const bh = Math.abs(v) / (max || 1) * (h / 2 - 4);
          const y = isPos ? h / 2 - bh : h / 2;
          const color = colors ? colors[i] : isPos ? "var(--pos)" : "var(--neg)";
          return <rect key={i} x={8 + i * (bw + 2)} y={y} width={bw} height={bh} fill={color} opacity="0.78" />;
        })}
      </svg>);

  }
  // unsigned
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {values.map((v, i) => {
        const bh = v / (max || 1) * (h - 8);
        return <rect key={i} x={8 + i * (bw + 2)} y={h - bh - 1} width={bw} height={bh} fill={colors && colors[i] || "var(--accent)"} opacity="0.8" />;
      })}
    </svg>);

}

// ─── Sortable Table ────────────────────────────────────────────────────────
function Table({ cols, rows, dense = false, onRowClick, rowKey = (r, i) => i, initialSort, striped = false }) {
  // cols: [{ key, label, w?, flex?, align?, sortable?, sort?: (a,b)=>n, render?: (row)=>node, value?: (row)=>any }]
  const [sort, setSort] = useState(initialSort || { key: null, dir: "desc" });

  const sortedRows = useMemo(() => {
    if (!sort.key) return rows;
    const c = cols.find((x) => x.key === sort.key);
    if (!c) return rows;
    const getter = c.value || ((r) => r[c.key]);
    const cmp = c.sort || ((a, b) => {
      const va = getter(a),vb = getter(b);
      if (typeof va === "number" && typeof vb === "number") return va - vb;
      return String(va).localeCompare(String(vb));
    });
    const out = rows.slice().sort(cmp);
    if (sort.dir === "desc") out.reverse();
    return out;
  }, [rows, sort, cols]);

  function toggleSort(key) {
    setSort((s) => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" });
  }

  return (
    <div className={"hf-table" + (dense ? " dense" : "") + (striped ? " striped" : "")}>
      <div className="hf-trow hf-thead">
        {cols.map((c) =>
        <div
          key={c.key}
          className={"hf-tcell " + (c.align === "right" ? "ar" : c.align === "center" ? "ac" : "") + (c.sortable !== false ? " sortable" : "")}
          style={{ flex: c.flex || "0 0 " + (c.w || 80) + "px" }}
          onClick={() => c.sortable !== false && toggleSort(c.key)}>
          
            <span className="hf-thh">{c.label}</span>
            {sort.key === c.key && <span className="hf-sort-arr mono">{sort.dir === "asc" ? "↑" : "↓"}</span>}
          </div>
        )}
      </div>
      {sortedRows.map((r, i) =>
      <div
        key={rowKey(r, i)}
        className={"hf-trow" + (onRowClick ? " clickable" : "")}
        onClick={() => onRowClick && onRowClick(r)}>
        
          {cols.map((c) =>
        <div key={c.key} className={"hf-tcell " + (c.align === "right" ? "ar" : c.align === "center" ? "ac" : "")} style={{ flex: c.flex || "0 0 " + (c.w || 80) + "px" }}>
              {c.render ? c.render(r, i) : c.value ? c.value(r) : r[c.key]}
            </div>
        )}
        </div>
      )}
      {sortedRows.length === 0 &&
      <div className="hf-trow empty"><div className="hf-tcell muted" style={{ flex: 1, textAlign: "center" }}>— no rows —</div></div>
      }
    </div>);

}

// ─── Bar cell (horizontal % bar in a table cell) ───────────────────────────
function BarCell({ value, max = 1, color = "var(--accent)", showLabel = false }) {
  const pct = Math.max(0, Math.min(1, value / max));
  return (
    <div className="hf-barcell">
      <div className="hf-barcell-fill" style={{ width: (pct * 100).toFixed(2) + "%", background: color }}></div>
      {showLabel && <span className="hf-barcell-lbl mono">{fmtPct(value, { decimals: 1 })}</span>}
    </div>);

}

// ─── Sidebar nav ───────────────────────────────────────────────────────────
function Sidebar({ route, onNav }) {
  const items = [
  { id: "home", label: "Home", k: "H" },
  { id: "managers", label: "Managers", k: "M" },
  { id: "compare", label: "Compare", k: "V" },
  { id: "stocks", label: "Stocks", k: "S" },
  { id: "qoq", label: "Changes", k: "Q" },
  { id: "consensus", label: "Consensus", k: "C" },
  { id: "backtest", label: "Backtest", k: "B" },
  { id: "builder", label: "Builder", k: "X" },
  { id: "ask", label: "Ask", k: "A" }];

  const currentRoot = route.path.split("/")[1] || "home";
  return (
    <aside className="hf-side">
      <div className="hf-side-logo">
        <div className="hf-side-logo-mark">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none">
            {/* rounded frame */}
            <rect x="2" y="2" width="20" height="20" rx="3.5" stroke="currentColor" strokeWidth="1.4" />
            {/* treemap — biggest cell is brand block, others fade */}
            <rect x="5" y="5" width="9" height="9" fill="currentColor" />
            <rect x="15" y="5" width="4" height="5.5" fill="currentColor" opacity="0.55" />
            <rect x="15" y="11.5" width="4" height="2.5" fill="currentColor" opacity="0.35" />
            <rect x="5" y="15" width="5.5" height="4" fill="currentColor" opacity="0.5" />
            <rect x="11.5" y="15" width="3.5" height="4" fill="currentColor" opacity="0.35" />
            <rect x="16" y="15" width="3" height="4" fill="currentColor" opacity="0.25" />
          </svg>
        </div>
        <div>
          <div className="hf-side-name" style={{ fontSize: "14px", fontFamily: "Pretendard" }}>13F TERMINAL</div>
          <div className="hf-side-sub mono" style={{ fontFamily: "Pretendard" }}>v 0.3 · quiet</div>
        </div>
      </div>
      <nav className="hf-side-nav">
        {items.map((it) =>
        <button
          key={it.id}
          className={"hf-side-it" + (currentRoot === it.id ? " on" : "")}
          onClick={() => onNav("/" + it.id)}>
          
            <span className="hf-side-it-k mono">{it.k}</span>
            <span className="hf-side-it-l">{it.label}</span>
          </button>
        )}
      </nav>
      <div className="hf-side-foot">
        <div className="hf-side-foot-row mono">
          <span>Q1 2026</span>
          <span className="hf-pill on">FILED 100%</span>
        </div>
        <div className="hf-side-foot-row mono">
          <span>22 mgrs · 64 tk</span>
        </div>
      </div>
    </aside>);

}

// ─── Topbar ────────────────────────────────────────────────────────────────
function Topbar({ crumbs, right, onSearch, quarter, onQuarter }) {
  return (
    <header className="hf-top">
      <div className="hf-top-crumbs">
        {crumbs.map((c, i) =>
        <React.Fragment key={i}>
            {i > 0 && <span className="hf-top-sep mono">›</span>}
            {c.onClick ?
          <button className="hf-top-crumb link" onClick={c.onClick}>{c.label}</button> :

          <span className="hf-top-crumb">{c.label}</span>
          }
          </React.Fragment>
        )}
      </div>
      <div className="hf-top-search">
        <span className="mono hf-top-search-k">⌘K</span>
        <input className="hf-top-search-in" placeholder="search ticker, manager, query…" />
      </div>
      <div className="hf-top-right">
        {quarter != null &&
        <div className="hf-top-q">
            <button className="hf-top-q-btn mono" onClick={() => onQuarter(Math.max(0, quarter - 1))} disabled={quarter === 0}>‹</button>
            <span className="mono hf-top-q-lbl">{Q_LABELS[quarter]}</span>
            <button className="hf-top-q-btn mono" onClick={() => onQuarter(Math.min(Q_LABELS.length - 1, quarter + 1))} disabled={quarter === Q_LABELS.length - 1}>›</button>
          </div>
        }
        {right}
      </div>
    </header>);

}

// ─── Section ───────────────────────────────────────────────────────────────
function Section({ title, sub, right, children, dense = false, pad = true }) {
  return (
    <section className={"hf-sect" + (dense ? " dense" : "") + (pad ? "" : " nopad")}>
      <div className="hf-sect-hd">
        <div>
          <h3 className="hf-sect-t">{title}</h3>
          {sub && <div className="hf-sect-s">{sub}</div>}
        </div>
        {right && <div className="hf-sect-r">{right}</div>}
      </div>
      <div className="hf-sect-body">{children}</div>
    </section>);

}

// ─── Stat block ────────────────────────────────────────────────────────────
function Stat({ label, value, delta, sub, spark, accent }) {
  return (
    <div className={"hf-stat" + (accent ? " accent" : "")}>
      <div className="hf-stat-l">{label}</div>
      <div className="hf-stat-v mono num">{value}</div>
      {(delta != null || sub) &&
      <div className="hf-stat-d">
          {delta != null && <Delta value={delta} kind="pct" decimals={2} />}
          {sub && <span className="hf-stat-sub">{sub}</span>}
        </div>
      }
      {spark && <div className="hf-stat-sp">{spark}</div>}
    </div>);

}

// ─── Pill ──────────────────────────────────────────────────────────────────
function Pill({ children, on, onClick, kind }) {
  return <button className={"hf-pill" + (on ? " on" : "") + (kind ? " " + kind : "")} onClick={onClick}>{children}</button>;
}

Object.assign(window, {
  fmtMoney, fmtPct, fmtNum, fmtShares,
  Badge, Avatar, Delta, Spark, LineChart, Treemap, BarChart, BarCell,
  Table, Sidebar, Topbar, Section, Stat, Pill
});