// 13F Terminal — app shell + hash router

const { useState: hUseState, useEffect: hUseEffect, useMemo: hUseMemo } = React;

// ─── Hash router ──────────────────────────────────────────────────────────
function parseHash() {
  const raw = window.location.hash.replace(/^#/, "") || "/home";
  const [path, ...query] = raw.split("?");
  const params = {};
  if (query.length) {
    const qs = query.join("?");
    qs.split("&").forEach(p => {
      const [k, v] = p.split("=");
      if (k) params[decodeURIComponent(k)] = decodeURIComponent(v || "");
    });
  }
  return { path: path || "/home", params };
}

function useRoute() {
  const [route, setRoute] = hUseState(parseHash);
  hUseEffect(() => {
    const h = () => setRoute(parseHash());
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  return route;
}

function navigate(path, params) {
  let hash = "#" + path;
  if (params) {
    const qs = Object.entries(params).map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("&");
    if (qs) hash += "?" + qs;
  }
  window.location.hash = hash;
}

// ─── Tweak defaults (theme/font/density) ──────────────────────────────────
const HF_TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "regular",
  "accent": "#1d6dc8",
  "showWireLink": true
}/*EDITMODE-END*/;

// ─── Main App ──────────────────────────────────────────────────────────────
function App() {
  const route = useRoute();
  const [t, setTweak] = useTweaks(HF_TWEAK_DEFAULTS);
  // current quarter (global, overridable per-screen via param)
  const [quarter, setQuarter] = hUseState(QUARTERS.length - 1); // default = latest

  hUseEffect(() => {
    document.body.dataset.density = t.density;
    document.documentElement.style.setProperty("--accent", t.accent);
  }, [t.density, t.accent]);

  const [root, sub] = route.path.split("/").filter(Boolean);

  return (
    <div className="hf-root">
      <Sidebar route={route} onNav={navigate} />
      <main className="hf-main">
        {renderScreen({ root, sub, route, quarter, setQuarter })}
      </main>
      <TweaksPanel>
        <TweakSection label="Layout" />
        <TweakRadio label="Density" value={t.density} options={["compact", "regular", "cozy"]} onChange={v => setTweak("density", v)} />
        <TweakSection label="Accent" />
        <TweakColor label="Accent" value={t.accent} options={["#1d6dc8", "#0e8a3b", "#7c3aed", "#0a0d14"]} onChange={v => setTweak("accent", v)} />
        <TweakSection label="More" />
        <TweakButton label="Open wireframes" onClick={() => window.open("13F Tracker Wireframes.html", "_blank")} />
      </TweaksPanel>
    </div>
  );
}

function renderScreen({ root, sub, route, quarter, setQuarter }) {
  const r = root || "home";
  const props = { route, quarter, setQuarter, sub };
  switch (r) {
    case "home":      return <DashboardScreen {...props} />;
    case "managers":  return sub ? <ManagerScreen mgrId={sub} {...props} /> : <ManagersListScreen {...props} />;
    case "stocks":    return sub ? <StockScreen ticker={sub} {...props} /> : <StocksListScreen {...props} />;
    case "compare":   return <CompareScreen {...props} />;
    case "backtest":  return <BacktestScreen {...props} />;
    case "ask":       return <AskScreen {...props} />;
    case "qoq":       return <QoQScreen {...props} />;
    case "consensus": return <ConsensusScreen {...props} />;
    case "builder":   return <BuilderScreen {...props} />;
    default:          return <DashboardScreen {...props} />;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
