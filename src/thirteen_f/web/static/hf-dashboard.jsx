// 13F Terminal — Dashboard screen (Feed + Spotlight)

function DashboardScreen({ quarter, setQuarter }) {
  const summary = quarterSummary(quarter);
  const spot = spotlight(quarter);
  const acts = summary.acts.slice().sort((a, b) => Math.abs(b.deltaValue) - Math.abs(a.deltaValue));

  // crowded: count holders per ticker, latest quarter
  const crowded = useMemo(() => {
    const map = {};
    for (const tk of Object.keys(STOCK_MAP)) {
      const h = tickerHolders(tk, quarter);
      if (h.length >= 2) map[tk] = { ticker: tk, stock: STOCK_MAP[tk], holders: h, n: h.length };
    }
    return Object.values(map).sort((a, b) => b.n - a.n).slice(0, 8);
  }, [quarter]);

  // sector flow: aggregate delta value by sector
  const sectorFlow = useMemo(() => {
    const flow = {};
    for (const a of summary.acts) {
      const sec = a.stock.s;
      flow[sec] = (flow[sec] || 0) + a.deltaValue;
    }
    return Object.entries(flow).map(([sec, v]) => ({ sec, v })).sort((a, b) => b.v - a.v);
  }, [summary]);

  // spotlight chart: ticker price series with manager entry marker
  const spotSeries = spot ? [{
    label: spot.ticker,
    color: "var(--ink)",
    values: spot.stock.pxWeekly,
    width: 1.8
  }] : [];

  return (
    <>
      <Topbar
        crumbs={[{ label: "Home" }]}
        quarter={quarter}
        onQuarter={setQuarter}
        right={<Pill on>Live</Pill>} />
      
      <div className="hf-pg dash">
        {/* KPI strip */}
        <div className="dash-kpis">
          <Stat label="QUARTER" value={Q_LABELS[quarter]} sub="13F filings" />
          <Stat label="NEW POSITIONS" value={summary.by.NEW || 0} accent />
          <Stat label="ADDED TO" value={summary.by.ADD || 0} />
          <Stat label="REDUCED" value={summary.by.CUT || 0} />
          <Stat label="EXITS" value={summary.by.EXIT || 0} />
          <Stat label="MGRS TRACKED" value={MANAGERS.length} sub="super-investors" />
        </div>

        {/* Spotlight */}
        {spot &&
        <Section
          title={<><span className="dash-spot-tag mono">SPOTLIGHT</span><span className="dash-spot-h">{spot.action === "NEW" ? "opens" : spot.action === "EXIT" ? "exits" : spot.action === "ADD" ? "adds to" : "trims"} <b className="mono">{spot.ticker}</b></span></>}
          sub={<span><Avatar mgr={spot.mgr} sz={16} /> <button className="hf-link" onClick={() => navigate("/managers/" + spot.mgrId)}>{spot.mgr.name}</button> · {spot.stock.n} · {spot.stock.s}</span>}
          right={
          <div className="dash-spot-stats">
                <div className="dash-spot-stat"><div className="dash-spot-stat-l" style={{ fontFamily: "Pretendard" }}>Δ value</div><Delta value={spot.deltaValue * 1e6} kind="money" bold /></div>
                <div className="dash-spot-stat"><div className="dash-spot-stat-l">portfolio %</div><div className="mono num b">{fmtPct(spot.weight, { decimals: 2 })}</div></div>
                <div className="dash-spot-stat"><div className="dash-spot-stat-l">action</div><Badge kind={spot.action} /></div>
              </div>
          }>
          
            <div className="dash-spot-body">
              <LineChart
              series={spotSeries}
              w={920}
              h={240}
              formatY={(v) => "$" + v.toFixed(0)}
              formatX={(i) => {
                const q = Math.floor(i / 8);
                return q < Q_LABELS.length ? Q_LABELS[q] : "";
              }} />
            
              <div className="dash-spot-side">
                <div className="dash-spot-side-hd mono">Also holding {spot.ticker} this quarter</div>
                <div className="dash-spot-holders">
                  {tickerHolders(spot.ticker, quarter).map((h) =>
                <button key={h.mgrId} className="dash-spot-holder" onClick={() => navigate("/managers/" + h.mgrId)}>
                      <Avatar mgr={h.mgr} sz={20} />
                      <span className="dash-spot-holder-n">{h.mgr.name.split(" ")[0]}</span>
                      <span className="mono num dash-spot-holder-w">{fmtPct(h.weight, { decimals: 1 })}</span>
                      {h.action && h.action !== "HOLD" && <Badge kind={h.action} sm />}
                    </button>
                )}
                </div>
                <button className="hf-btn" onClick={() => navigate("/stocks/" + spot.ticker)}>
                  Open {spot.ticker} →
                </button>
              </div>
            </div>
          </Section>
        }

        {/* Crowded buys */}
        <Section title="Most crowded" sub={`held by ≥ 2 super-investors, ${Q_LABELS[quarter]}`} right={<button className="hf-link mono" onClick={() => navigate("/consensus")}>view all →</button>}>
          <Table
            dense
            cols={[
            { key: "rank", label: "#", w: 36, sortable: false, render: (r, i) => <span className="mono muted">{i + 1}</span> },
            { key: "tk", label: "TICKER", w: 80, render: (r) => <button className="hf-link mono b" onClick={(e) => {e.stopPropagation();navigate("/stocks/" + r.ticker);}}>{r.ticker}</button> },
            { key: "name", label: "COMPANY", flex: 1.4, render: (r) => <span className="hf-tx">{r.stock.n}</span>, value: (r) => r.stock.n },
            { key: "sec", label: "SECTOR", w: 100, render: (r) => <span className="hf-pill" style={{ borderColor: SECTOR_COLORS[r.stock.s], color: SECTOR_COLORS[r.stock.s] }}>{r.stock.s}</span>, value: (r) => r.stock.s },
            { key: "holders", label: "HOLDERS", w: 160, render: (r) =>
              <div className="dash-stacked-av">
                  {r.holders.slice(0, 6).map((h, i) => <span key={h.mgrId} style={{ marginLeft: i ? -7 : 0 }}><Avatar mgr={h.mgr} sz={20} /></span>)}
                  {r.holders.length > 6 && <span className="mono dash-stacked-more">+{r.holders.length - 6}</span>}
                </div>,
              value: (r) => r.n },
            { key: "n", label: "#", w: 44, align: "right", render: (r) => <span className="mono num b">{r.n}</span> },
            { key: "avgw", label: "AVG %", w: 80, align: "right", render: (r) => {
                const avg = r.holders.reduce((a, b) => a + b.weight, 0) / r.holders.length;
                return <span className="mono num">{fmtPct(avg, { decimals: 1 })}</span>;
              }, value: (r) => r.holders.reduce((a, b) => a + b.weight, 0) / r.holders.length },
            { key: "bar", label: "", flex: 0.8, sortable: false, render: (r) => <BarCell value={r.n} max={Math.max(...crowded.map((x) => x.n))} color="var(--accent)" /> },
            { key: "spark", label: "PRICE 12W", w: 110, sortable: false, render: (r) => <Spark values={r.stock.pxWeekly.slice(-12)} w={100} h={22} fill /> }]
            }
            rows={crowded}
            rowKey={(r) => r.ticker}
            onRowClick={(r) => navigate("/stocks/" + r.ticker)}
            initialSort={{ key: "n", dir: "desc" }} />
          
        </Section>

        <div className="dash-grid-b">
          {/* Activity feed */}
          <Section title="Activity this quarter" sub={`${summary.acts.length} moves across ${MANAGERS.length} managers`} right={<DashActionFilter />}>
            <Table
              dense
              cols={[
              { key: "act", label: "ACT", w: 50, render: (r) => <Badge kind={r.action} />, value: (r) => r.action },
              { key: "tk", label: "TICKER", w: 64, render: (r) => <button className="hf-link mono b" onClick={(e) => {e.stopPropagation();navigate("/stocks/" + r.ticker);}}>{r.ticker}</button>, value: (r) => r.ticker },
              { key: "name", label: "COMPANY", flex: 1.2, render: (r) => <span className="hf-tx muted">{r.stock.n}</span>, value: (r) => r.stock.n },
              { key: "mgr", label: "MANAGER", flex: 1, render: (r) =>
                <button className="hf-link mgrcell" onClick={(e) => {e.stopPropagation();navigate("/managers/" + r.mgrId);}}>
                    <Avatar mgr={r.mgr} sz={18} /> <span>{r.mgr.name}</span>
                  </button>,
                value: (r) => r.mgr.name },
              { key: "w", label: "TO %", w: 60, align: "right", render: (r) => <span className="mono num">{fmtPct(r.weight, { decimals: 1 })}</span>, value: (r) => r.weight },
              { key: "dw", label: "Δ %PT", w: 70, align: "right", render: (r) => <Delta value={r.deltaWeight} kind="pct" decimals={2} />, value: (r) => r.deltaWeight },
              { key: "dv", label: "Δ $", w: 90, align: "right", render: (r) => <Delta value={r.deltaValue * 1e6} kind="money" decimals={1} />, value: (r) => r.deltaValue }]
              }
              rows={acts}
              initialSort={{ key: "dv", dir: "desc" }}
              striped />
            
          </Section>

          {/* Sector flow */}
          <Section title="Sector flow" sub={`net $ moved by sector, ${Q_LABELS[quarter]}`}>
            <div className="dash-sector">
              {sectorFlow.map(({ sec, v }) => {
                const max = Math.max(...sectorFlow.map((s) => Math.abs(s.v)));
                const w = max > 0 ? Math.abs(v) / max : 0;
                const pos = v >= 0;
                return (
                  <div key={sec} className="dash-sector-row">
                    <div className="dash-sector-label">
                      <span className="dash-sector-sw" style={{ background: SECTOR_COLORS[sec] || "var(--ink-3)" }}></span>
                      <span>{sec}</span>
                    </div>
                    <div className="dash-sector-track">
                      <div className="dash-sector-mid"></div>
                      <div
                        className={"dash-sector-bar " + (pos ? "pos" : "neg")}
                        style={{
                          width: (w * 50).toFixed(1) + "%",
                          left: pos ? "50%" : (50 - w * 50).toFixed(1) + "%",
                          background: pos ? "var(--pos)" : "var(--neg)"
                        }}>
                      </div>
                    </div>
                    <div className="dash-sector-val mono num">
                      <Delta value={v * 1e6} kind="money" decimals={1} />
                    </div>
                  </div>);

              })}
              {sectorFlow.length === 0 && <div className="muted hf-tx">— no net movement —</div>}
            </div>
          </Section>
        </div>
      </div>
    </>);

}

function DashActionFilter() {
  return (
    <div className="dash-act-filt mono">
      <Pill on>all</Pill>
      <Pill kind="pos">NEW · ADD</Pill>
      <Pill kind="neg">CUT · EXIT</Pill>
    </div>);

}

Object.assign(window, { DashboardScreen, DashActionFilter });