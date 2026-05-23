// 13F Terminal — Manager Compare screen

function CompareScreen({ route, quarter, setQuarter }) {
  const [mgrIds, setMgrIds] = useState(() => {
    const init = (route.params.mgrs || "buffett,burry").split(",").filter(id => MGR_MAP[id]);
    return init.length ? init : ["buffett", "burry"];
  });

  // Sync from URL when it changes externally (e.g. nav from manager detail)
  useEffect(() => {
    if (!route.params.mgrs) return;
    const fromUrl = route.params.mgrs.split(",").filter(id => MGR_MAP[id]);
    if (fromUrl.length === 0) return;
    if (fromUrl.join(",") !== mgrIds.join(",")) {
      setMgrIds(fromUrl);
    }
  }, [route.params.mgrs]);

  const mgrs = mgrIds.map(id => MGR_MAP[id]);

  function toggleMgr(id) {
    setMgrIds(ids => {
      let next;
      if (ids.includes(id)) {
        if (ids.length <= 1) return ids;
        next = ids.filter(x => x !== id);
      } else {
        if (ids.length >= 4) next = [...ids.slice(1), id];
        else next = [...ids, id];
      }
      return next;
    });
  }

  // Per-manager portfolios at the current quarter
  const ports = useMemo(() => mgrIds.map(id => ({
    id,
    mgr: MGR_MAP[id],
    port: managerPortfolio(id, quarter),
    portMap: Object.fromEntries(managerPortfolio(id, quarter).filter(p => p.held).map(p => [p.ticker, p])),
    total: managerTotal(id, quarter),
    series: QUARTERS.map((_, q) => managerTotal(id, q)),
  })), [mgrIds, quarter]);

  // Union of held tickers across selected managers
  const tickersUnion = useMemo(() => {
    const set = new Set();
    ports.forEach(p => Object.keys(p.portMap).forEach(t => set.add(t)));
    return Array.from(set);
  }, [ports]);

  // Per-ticker comparison row
  const compareRows = useMemo(() => tickersUnion.map(t => {
    const cells = ports.map(p => p.portMap[t] || null);
    const heldCount = cells.filter(c => c).length;
    const weights = cells.map(c => c?.weight || 0);
    const directions = cells.map(c => c ? (c.action === "ADD" || c.action === "NEW" ? 1 : c.action === "CUT" || c.action === "EXIT" ? -1 : 0) : null);
    const validDirs = directions.filter(d => d !== null && d !== 0);
    const agreeUp = validDirs.length && validDirs.every(d => d > 0);
    const agreeDown = validDirs.length && validDirs.every(d => d < 0);
    const agreement = agreeUp ? "up" : agreeDown ? "down" : (validDirs.length > 1 ? "split" : "");
    return { ticker: t, stock: STOCK_MAP[t], cells, heldCount, weights, agreement, maxW: Math.max(...weights) };
  }), [tickersUnion, ports]);

  // Overlap categories
  const inAll = compareRows.filter(r => r.heldCount === ports.length);
  const inMost = compareRows.filter(r => r.heldCount === ports.length - 1 && ports.length > 1);
  const uniquePerMgr = ports.map((p, idx) => ({
    mgr: p.mgr,
    rows: compareRows.filter(r => r.cells[idx] && r.heldCount === 1),
  }));

  // Sector exposure comparison
  const sectorExposure = useMemo(() => {
    const sectors = Object.keys(SECTOR_COLORS);
    return sectors.map(sec => {
      const byMgr = ports.map(p => {
        const port = p.port.filter(x => x.held && x.stock.s === sec);
        return port.reduce((a, b) => a + b.weight, 0);
      });
      return { sec, byMgr };
    });
  }, [ports]);

  return (
    <>
      <Topbar
        crumbs={[{ label: "Compare" }]}
        quarter={quarter}
        onQuarter={setQuarter}
        right={
          <button className="hf-btn" onClick={() => navigate("/backtest", { mgr: mgrIds[0] })}>
            ▶ Backtest primary
          </button>
        }
      />
      <div className="hf-pg cmp">
        {/* Manager picker */}
        <Section title="Compare managers" sub="pick 2–4 super-investors to compare side-by-side" pad={true}>
          <div className="cmp-pickers">
            {MANAGERS.map(m => {
              const on = mgrIds.includes(m.id);
              return (
                <button
                  key={m.id}
                  className={"cmp-pick" + (on ? " on" : "")}
                  onClick={() => toggleMgr(m.id)}
                  style={on ? { borderColor: m.color, boxShadow: `inset 0 0 0 1px ${m.color}` } : {}}
                >
                  <Avatar mgr={m} sz={26} />
                  <div className="cmp-pick-id">
                    <div className="cmp-pick-n">{m.name}</div>
                    <div className="cmp-pick-f mono">{m.firm}</div>
                  </div>
                  {on && <span className="cmp-pick-on mono" style={{ background: m.color }}>✓</span>}
                </button>
              );
            })}
          </div>
        </Section>

        {/* KPI strip */}
        <div className="cmp-kpis">
          <Stat label="MANAGERS" value={mgrIds.length} sub="selected" />
          <Stat label="UNION HOLDINGS" value={tickersUnion.length} sub="distinct tickers" />
          <Stat label="HELD BY ALL" value={inAll.length} sub={mgrIds.length > 1 ? "intersection" : "—"} accent={inAll.length > 0} />
          <Stat label="HELD BY N-1" value={inMost.length} sub="near-consensus" />
          <Stat
            label="AGREEMENT ▲▼"
            value={
              <span>
                <span className="pos">{compareRows.filter(r => r.agreement === "up").length}</span>
                <span className="muted mono" style={{ margin: "0 4px" }}>/</span>
                <span className="neg">{compareRows.filter(r => r.agreement === "down").length}</span>
                <span className="muted mono" style={{ margin: "0 4px" }}>/</span>
                <span className="muted">{compareRows.filter(r => r.agreement === "split").length}</span>
              </span>
            }
            sub="same-direction actions"
          />
          <Stat label="QUARTER" value={Q_LABELS[quarter]} sub="snapshot" />
        </div>

        {/* Mirror treemaps */}
        <Section title="Portfolios side-by-side" sub={`treemap by % of port · ${Q_LABELS[quarter]}`} right={<TmapLegend />}>
          <div className={"cmp-mirror cols-" + ports.length}>
            {ports.map(p => (
              <CompareTmap key={p.id} mgr={p.mgr} port={p.port} total={p.total} />
            ))}
          </div>
        </Section>

        {/* Diff table */}
        <Section
          title="Position-by-position diff"
          sub={`${compareRows.length} distinct tickers · sort any column · click ticker → stock detail`}
          right={
            <div className="cmp-legend-mini">
              <span><span className="agg-sw up"></span>same-dir buy</span>
              <span><span className="agg-sw down"></span>same-dir sell</span>
              <span><span className="agg-sw split"></span>split</span>
            </div>
          }
        >
          <Table
            dense
            cols={[
              { key: "rank", label: "#", w: 36, sortable: false, render: (r, i) => <span className="mono muted">{i + 1}</span> },
              { key: "tk", label: "TICKER", w: 80, render: r => <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>, value: r => r.ticker },
              { key: "name", label: "COMPANY", flex: 1.4, render: r => <span className="hf-tx">{r.stock.n}</span>, value: r => r.stock.n },
              { key: "sec", label: "SECTOR", w: 100, render: r => <span className="hf-pill" style={{ color: SECTOR_COLORS[r.stock.s], borderColor: SECTOR_COLORS[r.stock.s] }}>{r.stock.s}</span>, value: r => r.stock.s },
              { key: "held", label: "HELD BY", w: 80, align: "center", render: r => <span className="mono num b">{r.heldCount}<span className="muted">/{ports.length}</span></span>, value: r => r.heldCount },
              ...ports.map((p, idx) => ({
                key: "m" + idx,
                label: p.mgr.name.split(" ").slice(-1)[0].toUpperCase().slice(0, 8),
                flex: 1,
                value: r => r.weights[idx],
                render: r => {
                  const c = r.cells[idx];
                  if (!c) return <span className="muted mono cmp-dash">—</span>;
                  return (
                    <div className="cmp-cell">
                      <span className="mono num b">{fmtPct(c.weight, { decimals: 1 })}</span>
                      <div className="cmp-cell-bar"><BarCell value={c.weight} max={r.maxW || 1} color={p.mgr.color} /></div>
                      {c.action && c.action !== "HOLD" && <Badge kind={c.action} sm />}
                    </div>
                  );
                },
              })),
              { key: "agree", label: "AGREE", w: 70, align: "center", render: r => r.agreement ? <span className={"agg-sw " + r.agreement} title={r.agreement}></span> : <span className="muted mono cmp-dash">—</span>, value: r => r.agreement },
            ]}
            rows={compareRows}
            rowKey={r => r.ticker}
            initialSort={{ key: "held", dir: "desc" }}
            onRowClick={r => navigate("/stocks/" + r.ticker)}
          />
        </Section>

        {/* Overlap buckets */}
        <div className="cmp-overlap-grid">
          <Section title={`Held by all ${ports.length}`} sub={inAll.length === 0 ? "no overlap" : "consensus picks"} dense>
            {inAll.length === 0 && <div className="muted hf-tx">— none —</div>}
            {inAll.map(r => (
              <div key={r.ticker} className="cmp-ov-row" onClick={() => navigate("/stocks/" + r.ticker)}>
                <button className="hf-link mono b cmp-ov-tk" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>
                <span className="hf-tx muted">{r.stock.n}</span>
                <span className="cmp-ov-avg mono">avg {fmtPct(r.weights.reduce((a, b) => a + b, 0) / ports.length, { decimals: 1 })}</span>
              </div>
            ))}
          </Section>

          {ports.length > 1 && (
            <Section title={`Held by ${ports.length - 1} of ${ports.length}`} sub="near-consensus, one outlier" dense>
              {inMost.length === 0 && <div className="muted hf-tx">— none —</div>}
              {inMost.map(r => {
                const missing = ports.find((_, idx) => !r.cells[idx]);
                return (
                  <div key={r.ticker} className="cmp-ov-row" onClick={() => navigate("/stocks/" + r.ticker)}>
                    <button className="hf-link mono b cmp-ov-tk" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>
                    <span className="hf-tx muted">{r.stock.n}</span>
                    <span className="cmp-ov-miss mono">missing: <span className="b">{missing?.mgr.name.split(" ").slice(-1)[0]}</span></span>
                  </div>
                );
              })}
            </Section>
          )}
        </div>

        {/* Unique per manager */}
        <Section title="Unique positions" sub="held only by this manager among the selected group">
          <div className={"cmp-unique cols-" + ports.length}>
            {uniquePerMgr.map(({ mgr, rows }) => (
              <div key={mgr.id} className="cmp-unique-col">
                <div className="cmp-unique-hd">
                  <Avatar mgr={mgr} sz={22} />
                  <span className="b">{mgr.name}</span>
                  <span className="mono muted">{rows.length}</span>
                </div>
                {rows.length === 0 && <div className="muted hf-tx" style={{ padding: 8 }}>— none unique —</div>}
                {rows.slice(0, 10).map(r => {
                  const cell = r.cells[ports.findIndex(p => p.mgr.id === mgr.id)];
                  return (
                    <div key={r.ticker} className="cmp-unique-row" onClick={() => navigate("/stocks/" + r.ticker)}>
                      <button className="hf-link mono b" onClick={(e) => { e.stopPropagation(); navigate("/stocks/" + r.ticker); }}>{r.ticker}</button>
                      <span className="hf-tx muted">{r.stock.n}</span>
                      <span className="mono num">{fmtPct(cell.weight, { decimals: 1 })}</span>
                      {cell.action && cell.action !== "HOLD" && <Badge kind={cell.action} sm />}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </Section>

        {/* Sector exposure */}
        <Section title="Sector exposure" sub="% of each manager's portfolio per sector">
          <div className="cmp-sec-table">
            <div className="cmp-sec-head">
              <div className="cmp-sec-h cmp-sec-cell-label">SECTOR</div>
              {ports.map(p => (
                <div key={p.id} className="cmp-sec-h">
                  <Avatar mgr={p.mgr} sz={18} /> {p.mgr.name.split(" ").slice(-1)[0]}
                </div>
              ))}
            </div>
            {sectorExposure.map(({ sec, byMgr }) => (
              <div key={sec} className="cmp-sec-row">
                <div className="cmp-sec-cell-label">
                  <span className="dash-sector-sw" style={{ background: SECTOR_COLORS[sec] }}></span>
                  {sec}
                </div>
                {byMgr.map((w, i) => (
                  <div key={i} className="cmp-sec-cell">
                    <BarCell value={w} max={1} color={ports[i].mgr.color} />
                    <span className="cmp-sec-cell-pct mono num">{fmtPct(w, { decimals: 1 })}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Section>

        {/* Portfolio value over time */}
        <Section title="Portfolio value · 8 quarters" sub="indexed to each manager's peak quarter = 1.00×">
          <LineChart
            series={ports.map(p => {
              const peak = Math.max(...p.series.filter(v => v > 0));
              return {
                label: p.mgr.name.split(" ").slice(-1)[0],
                color: p.mgr.color,
                values: p.series.map(v => peak > 0 ? v / peak : 0),
                width: 1.8,
              };
            })}
            w={960} h={220}
            padding={{ l: 50, r: 12, t: 12, b: 24 }}
            formatY={v => v.toFixed(2) + "×"}
            formatX={i => Q_LABELS[i]}
          />
        </Section>
      </div>
    </>
  );
}

function CompareTmap({ mgr, port, total }) {
  const items = port.filter(p => p.held).map(p => ({
    key: p.ticker,
    label: p.ticker,
    sublabel: fmtPct(p.weight, { decimals: 1 }),
    value: p.weight,
    color: SECTOR_COLORS[p.stock.s] || "var(--accent)",
  }));
  return (
    <div className="cmp-tmap-cell">
      <div className="cmp-tmap-hd">
        <Avatar mgr={mgr} sz={24} />
        <div>
          <div className="cmp-tmap-n b">{mgr.name}</div>
          <div className="cmp-tmap-sub mono muted">{port.filter(p => p.held).length} pos · {fmtMoney(total * 1e6, { decimals: 1 })}</div>
        </div>
      </div>
      <Treemap items={items} w={360} h={320} onSelect={(it) => navigate("/stocks/" + it.key)} />
    </div>
  );
}

Object.assign(window, { CompareScreen, CompareTmap });
