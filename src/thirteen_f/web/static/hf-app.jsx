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

// ─── Tweak defaults (theme/density) ───────────────────────────────────────
// Phase 5 C5: host protocol 제거 후 EDITMODE 마커 불필요. density만 유지.
const HF_TWEAK_DEFAULTS = {
  density: "regular",
};

// ─── Loading / error screens (Phase 5 C2) ─────────────────────────────────
function LoadingScreen() {
  return (
    <div style={{ padding: 40, fontFamily: "Pretendard, sans-serif" }}>
      <div className="mono muted" style={{ fontSize: 14, letterSpacing: 1 }}>
        LOADING 13F TERMINAL…
      </div>
      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
        fetching /data/*.json
      </div>
    </div>
  );
}

function ErrorScreen({ error }) {
  return (
    <div style={{ padding: 40, fontFamily: "Pretendard, sans-serif" }}>
      <h2 style={{ margin: 0 }}>데이터 로드 실패</h2>
      <p className="muted" style={{ marginTop: 8 }}>
        서버가 켜져 있고 <code>thirteen-f export</code>가 실행됐는지 확인하세요.
      </p>
      <pre
        style={{
          padding: 12,
          background: "#f1f5f9",
          borderRadius: 6,
          marginTop: 12,
          overflow: "auto",
          fontSize: 12,
        }}
      >
        {String(error && error.stack ? error.stack : error)}
      </pre>
    </div>
  );
}

// ─── Main App ──────────────────────────────────────────────────────────────
function App() {
  const route = useRoute();
  const [t, setTweak] = useTweaks(HF_TWEAK_DEFAULTS);
  const [bootStatus, setBootStatus] = hUseState("loading"); // loading | ready | error
  const [bootError, setBootError] = hUseState(null);
  // current quarter (global, overridable per-screen via param)
  const [quarter, setQuarter] = hUseState(0);

  hUseEffect(() => {
    bootstrapFromJson()
      .then(() => {
        setQuarter(Math.max(0, QUARTERS.length - 1));
        setBootStatus("ready");
      })
      .catch((e) => {
        setBootError(e);
        setBootStatus("error");
      });
  }, []);

  hUseEffect(() => {
    document.body.dataset.density = t.density;
  }, [t.density]);

  if (bootStatus === "loading") return <LoadingScreen />;
  if (bootStatus === "error") return <ErrorScreen error={bootError} />;

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
