// App.jsx — InvestIQ aplicación completa refactorizada
import React, { useEffect, useState, useCallback } from "react";
import { StoreProvider, useStore } from "./store/store";
import { useWebSocket } from "./hooks";
import Topbar from "./components/layout/Topbar";
import ActionBar from "./components/layout/ActionBar";
import TickerBar from "./components/layout/TickerBar";
import Sidebar from "./components/layout/Sidebar";
import RightPanel from "./components/layout/RightPanel";
import Dashboard from "./pages/Dashboard";
import { RoboAdvisorPanel, OrderPanel, KYCPanel, FiscalPanel, AuditPanel } from "./components/panels";

function Toast() {
  const { state } = useStore();
  const t = state.toast;
  if (!t) return null;
  return (
    <div style={{ position:"fixed", bottom:20, right:20, zIndex:999,
      background:"#171f2a", border:`1px solid ${t.type==="error"?"#f44336":"#17cc85"}`,
      color:t.type==="error"?"#f44336":"#17cc85",
      padding:"10px 18px", borderRadius:10, fontSize:11,
      display:"flex", alignItems:"center", gap:8,
      boxShadow:`0 4px 24px rgba(0,0,0,.6)` }}>
      <i className={`fas ${t.type==="error"?"fa-times-circle":"fa-check-circle"}`} />
      {t.msg}
    </div>
  );
}

function InnerApp() {
  const { state, dispatch, actions } = useStore();
  const [wsStatus, setWsStatus] = useState("connecting");

  useWebSocket(useCallback((msg) => {
    setWsStatus("connected");
    if (msg.type === "prices" || msg.type === "init")
      dispatch({ type:"SET_PRICES", payload: msg.data || msg.prices || {} });
    if (msg.type === "orden") {
      dispatch({ type:"PREPEND_ORDEN", payload: msg.data });
      actions.loadMetricas();
    }
    if (msg.type === "saldo") actions.loadMetricas();
  }, []));

  useEffect(() => {
    actions.loadAll();
    const tid = setTimeout(() => {
      if (state.ttsEnabled && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance("InvestIQ iniciado. Panel de microinversión listo.");
        u.lang = "es-ES"; u.rate = 1.0; u.pitch = 0.85;
        const v = window.speechSynthesis.getVoices().find(v => v.lang.startsWith("es"));
        if (v) u.voice = v;
        window.speechSynthesis.speak(u);
      }
    }, 2000);
    return () => clearTimeout(tid);
  }, []);

  useEffect(() => {
    const iv = setInterval(() => { actions.loadMetricas(); actions.loadPortafolio(); }, 15000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div style={{ background:"#0b0f14", color:"#dde4f0", minHeight:"100vh",
      fontFamily:"'Segoe UI',system-ui,sans-serif", fontSize:12, overflow:"hidden" }}>
      <Topbar wsStatus={wsStatus} />
      <ActionBar />
      <TickerBar />
      <div style={{ display:"grid", gridTemplateColumns:"190px 1fr 268px",
        height:"calc(100vh - 124px)", overflow:"hidden" }}>
        <Sidebar />
        <main style={{ overflowY:"auto", padding:14, background:"#0b0f14",
          display:"flex", flexDirection:"column", gap:12 }}>
          <Dashboard />
        </main>
        <RightPanel prices={state.prices} />
      </div>
      <RoboAdvisorPanel />
      <OrderPanel prices={state.prices} />
      <KYCPanel />
      <FiscalPanel />
      <AuditPanel />
      <Toast />
    </div>
  );
}

export default function App() {
  return <StoreProvider><InnerApp /></StoreProvider>;
}
