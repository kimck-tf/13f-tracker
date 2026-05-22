// 13F Terminal — Manager screens (list + detail)

function ManagersListScreen({ quarter, setQuarter }) {
  const rows = useMemo(() => MANAGERS.map(m => {
    const port = managerPortfolio(m.id, quarter);
    const total = port.reduce((a, b) => a + b.value, 0);
    const top10 = port.slice(0, 10).reduce((a, b) => a + b.weight, 0);
    const acts = port.filter(p => p.action && p.action !== "HOLD");
    const newCt = acts.filter(a => a.action === "NEW").length;
    const cutCt = acts.filter(a => a.action === "CUT" || a.action === "EXIT").length;
    // 8-quarter total value series
    const series = QUARTERS.map((_, q) => managerTotal(m.id, q));
    return { ...m, total, top10, positions: port.length, newCt, cutCt, series };
  }), [quarter]);

  return (
    <>
      <Topbar crumbs={[{ label: "Managers" }]} quarter={quarter} onQuarter={setQuarter} />
      <div className="hf-pg">
        <Section title="Super-investors" sub={`${MANAGERS.length} tracked · ${Q_LABELS[quarter]}`}>
          <Table
            cols={[
              { key: "name", label: "MANAGER", flex: 1.4, render: r => (
                <button className="hf-link mgrcell b" onClick={(e) => { e.stopPropagation(); navigate("/managers/" + r.id); }}>
                  <Avatar mgr={r} sz={26} /> {r.name}
                  <span className="muted" style={{ marginLeft: 6, fontWeight: 400 }}>· {r.firm}</span>
                </button>
              ), value: r => r.name },
              { key: "positions", label: "POSITIONS", w: 90, align: "right", render: r => <span className="mono num">{r.positions}</span> },
              { key: "total", label: "VALUE", w: 100, align: "right", render: r => <span className="mono num">{fmtMoney(r.total * 1e6)}</span> },
              { key: "top10", label: "TOP 10 %", w: 90, align: "right", render: r => <span className="mono num">{fmtPct(r.top10, { decimals: 1 })}</span> },
              { key: "newCt", label: "NEW", w: 50, align: "right", render: r => <span className="mono num pos">+{r.newCt}</span>, value: r => r.newCt },
              { key: "cutCt", label: "CUT/EXIT", w: 80, align: "right", render: r => <span className="mono num neg">−{r.cutCt}</span>, value: r => r.cutCt },
              { key: "spark", label: "8Q VALUE", w: 110, sortable: false, render: r => <Spark values={r.series} w={100} h={26} fill /> },
              { key: "note", label: "STYLE", flex: 1, render: r => <span className="hf-tx muted">{r.note}</span> },
            ]}
            rows={rows}
            initialSort={{ key: "total", dir: "desc" }}
            onRowClick={r => navigate("/managers/" + r.id)}
          />
        </Section>
      </div>
    </>
  );
}

function ManagerScreen({ mgrId, quarter, setQuarter }) {
  const mgr = MGR_MAP[mgrId];
  const [tab, setTab] = useState("holdings");

  if (!mgr) {
    return (
      <>
        <Topbar crumbs={[{ label: "Managers", onClick: () => navigate("/managers") }, { label: mgrId }]} />
        <div className="hf-pg"><Section title="Not found"><div className="muted">Manager '{mgrId}' not in database.</div></Section></div>
      </>
    );
  }

  const port = useMemo(() => managerPortfolio(mgrId, quarter), [mgrId, quarter]);
  const portPrev = useMemo(() => quarter > 0 ? managerPortfolio(mgrId, quarter - 1) : [], [mgrId, quarter]);
  const total = port.reduce((a, b) => a + b.value, 0);
  const totalPrev = portPrev.reduce((a, b) => a + b.value, 0);
  const top10 = port.slice(0, 10).reduce((a, b) => a + b.weight, 0);
  const totalSeries = QUARTERS.map((_, q) => managerTotal(mgrId, q));

  // Treemap items
  const tmapItems = useMemo(() => port.filter(p => p.held).map(p => ({
    key: p.ticker,
    label: p.ticker,
    sublabel: fmtPct(p.weight, { decimals: 1 }),
    note: p.stock.n,
    value: p.weight,
    color: SECTOR_COLORS[p.stock.s] || "var(--accent)",
    _p: p,
  })), [port]);
  const [selectedTk, setSelectedTk] = useState(null);

  const acts = port.filter(p => p.action && p.action !== "HOLD");
  const newPos = acts.filter(a => a.action === "NEW");
  const exits = portPrev.filter(p => !port.find(c => c.ticker === p.ticker && c.held)).map(p => ({ ...p, action: "EXIT", weight: 0, deltaValue: -p.value }));

  return (
    <>
      <Topbar
        crumbs={[
          { label: "Managers", onClick: () => navigate("/managers") },
          { label: mgr.name },
        ]}
        quarter={quarter}
        onQuarter={setQuarter}
      />
      <div className="hf-pg mgr">
        {/* Manager header */}
        <div className="mgr-h">
          <Avatar mgr={mgr} sz={48} />
          <div className="mgr-h-id">
            <div className="mgr-h-name">{mgr.name}</div>
            <div className="mgr-h-firm">{mgr.firm}</div>
            <div className="mgr-h-note muted">{mgr.note}</div>
          </div>
          <div className="mgr-h-kpis">
            <Stat label="AUM (filed)" value={fmtMoney(mgr.aum * 1e9)} />
            <Stat label="Positions" value={port.filter(p => p.held).length} />
            <Stat label="Top 10 %" value={fmtPct(top10, { decimals: 1 })} />
            <Stat label="QoQ value" value={<Delta value={(total - totalPrev) / (totalPrev || 1)} />} />
            <Stat label="New / Exit" value={<span><span className="pos">+{newPos.length}</span> <span className="muted mono">/</span> <span className="neg">−{exits.length}</span></span>} />
          </div>
        </div>

        {/* Tabs */}
        <div className="mgr-tabs">
          {[
            { id: "holdings", label: "Holdings" },
            { id: "activity", label: "Activity" },
            { id: "compose", label: "Composition" },
          ].map(t => (
            <button key={t.id} className={"mgr-tab" + (tab === t.id ? " on" : "")} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
          <div className="mgr-tabs-r">
            <button className="hf-btn" onClick={() => navigate("/backtest", { mgr: mgrId })}>▶ Backtest "Follow {mgr.name.split(" ")[0]}"</button>
          </div>
        </div>

        {tab === "holdings" && (
          <div className="mgr-holdings">
            <div className="mgr-tmap">
              <Section title={`Portfolio — ${Q_LABELS[quarter]}`} sub={`${port.filter(p => p.held).length} positions · total value ${fmtMoney(total * 1e6)}`} right={<TmapLegend />}>
                <Treemap items={tmapItems} w={720} h={420} selectedKey={selectedTk} onSelect={(it) => setSelectedTk(it.key === selectedTk ? null : it.key)} />
              </Section>
            </div>
            <div className="mgr-table">
              <Section title="All positions" sub="sort by any column · click row → stock detail" dense>
                <Table
                  dense
                  cols={[
                    { key: "tk", label: "TICKER", w: 64, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>, value: r => r.ticker },
                    { key: "name", label: "COMPANY", flex: 1, render: r => <span className="hf-tx">{r.stock.n}</span>, value: r => r.stock.n },
                    { key: "sec", label: "SEC", w: 70, render: r => <span className="hf-pill" style={{ color: SECTOR_COLORS[r.stock.s], borderColor: SECTOR_COLORS[r.stock.s] }}>{r.stock.s.slice(0, 4)}</span>, value: r => r.stock.s },
                    { key: "val", label: "VALUE", w: 78, align: "right", render: r => <span className="mono num">{fmtMoney(r.value * 1e6)}</span>, value: r => r.value },
                    { key: "w", label: "% PORT", w: 70, align: "right", render: r => <span className="mono num b">{fmtPct(r.weight, { decimals: 2 })}</span>, value: r => r.weight },
                    { key: "bar", label: "", flex: 0.8, sortable: false, render: r => <BarCell value={r.weight} max={port[0]?.weight || 1} color={selectedTk === r.ticker ? "var(--accent)" : "var(--ink)"} /> },
                    { key: "dw", label: "Δ %PT", w: 70, align: "right", render: r => <Delta value={r.deltaWeight} kind="pct" decimals={2} />, value: r => r.deltaWeight },
                    { key: "act", label: "ACT", w: 50, render: r => r.action && r.action !== "HOLD" ? <Badge kind={r.action} /> : <span className="muted mono" style={{ fontSize: 10 }}>hold</span>, value: r => r.action || "HOLD" },
                    { key: "trend", label: "8Q WEIGHT", w: 100, sortable: false, render: r => {
                      const series = QUARTERS.map((_, q) => {
                        const total = managerTotal(mgrId, q);
                        return total > 0 ? positionValue(r.seriesShares[q], r.ticker, q) / total : 0;
                      });
                      return <Spark values={series} w={90} h={20} signedTrend={false} color="var(--ink-3)" fill />;
                    } },
                  ]}
                  rows={port.filter(p => p.held)}
                  rowKey={r => r.ticker}
                  initialSort={{ key: "w", dir: "desc" }}
                  onRowClick={r => navigate("/stocks/" + r.ticker)}
                />
              </Section>
            </div>
          </div>
        )}

        {tab === "activity" && (
          <Section title={`Activity — ${Q_LABELS[quarter]}`} sub={`${acts.length + exits.length} actions vs prior quarter`}>
            <Table
              dense
              cols={[
                { key: "act", label: "ACT", w: 50, render: r => <Badge kind={r.action} />, value: r => r.action },
                { key: "tk", label: "TICKER", w: 64, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>, value: r => r.ticker },
                { key: "name", label: "COMPANY", flex: 1, render: r => <span className="hf-tx muted">{r.stock.n}</span>, value: r => r.stock.n },
                { key: "from", label: "FROM %", w: 70, align: "right", render: r => <span className="mono num">{fmtPct((r.weight || 0) - (r.deltaWeight || 0), { decimals: 1 })}</span>, value: r => (r.weight - (r.deltaWeight || 0)) },
                { key: "to", label: "TO %", w: 70, align: "right", render: r => <span className="mono num b">{fmtPct(r.weight, { decimals: 1 })}</span>, value: r => r.weight },
                { key: "dw", label: "Δ %PT", w: 70, align: "right", render: r => <Delta value={r.deltaWeight} kind="pct" decimals={2} />, value: r => r.deltaWeight },
                { key: "dv", label: "Δ VALUE", w: 90, align: "right", render: r => <Delta value={(r.deltaValue || (-r.value)) * 1e6} kind="money" decimals={1} />, value: r => r.deltaValue || (-r.value) },
                { key: "share", label: "SHARES", w: 80, align: "right", render: r => <span className="mono num">{fmtShares(r.shares)}</span> },
              ]}
              rows={[...acts, ...exits]}
              initialSort={{ key: "dv", dir: "desc" }}
              striped
            />
          </Section>
        )}

        {tab === "compose" && (
          <div className="mgr-compose">
            <Section title="Portfolio value (8 quarters)" sub="approximated from filed positions × close prices">
              <LineChart
                series={[{ label: "Total value $M", color: mgr.color, values: totalSeries, fill: true, width: 1.8 }]}
                w={760} h={220}
                formatY={v => fmtMoney(v * 1e6, { decimals: 0 })}
                formatX={i => Q_LABELS[i]}
              />
            </Section>
            <Section title="Sector composition" sub={Q_LABELS[quarter]}>
              {(() => {
                const bySec = {};
                for (const p of port.filter(p => p.held)) {
                  bySec[p.stock.s] = (bySec[p.stock.s] || 0) + p.weight;
                }
                const rows = Object.entries(bySec).sort((a, b) => b[1] - a[1]);
                return (
                  <div className="mgr-sec-list">
                    {rows.map(([sec, w]) => (
                      <div key={sec} className="mgr-sec-row">
                        <div className="mgr-sec-label">
                          <span className="dash-sector-sw" style={{ background: SECTOR_COLORS[sec] }}></span>
                          {sec}
                        </div>
                        <div className="mgr-sec-bar"><BarCell value={w} max={1} color={SECTOR_COLORS[sec]} /></div>
                        <div className="mgr-sec-w mono num b">{fmtPct(w, { decimals: 1 })}</div>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </Section>
          </div>
        )}
      </div>
    </>
  );
}

function TmapLegend() {
  return (
    <div className="tmap-lg">
      {Object.entries(SECTOR_COLORS).map(([sec, c]) => (
        <span key={sec} className="tmap-lg-it">
          <span className="tmap-lg-sw" style={{ background: c }}></span>
          {sec}
        </span>
      ))}
    </div>
  );
}

Object.assign(window, { ManagersListScreen, ManagerScreen });
