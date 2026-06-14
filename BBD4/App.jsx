// App.jsx — InvestIQ COMPLETO — todas las páginas + PWA + Push + Onboarding
import React, { useEffect, useState, useCallback } from "react";
import { StoreProvider, useStore } from "./store/store";
import { useWebSocket } from "./hooks";
import Topbar from "./components/layout/Topbar";
import ActionBar from "./components/layout/ActionBar";
import TickerBar from "./components/layout/TickerBar";
import Sidebar from "./components/layout/Sidebar";
import RightPanel from "./components/layout/RightPanel";
import Dashboard from "./pages/Dashboard";
import Mercado from "./pages/Mercado";
import Portafolio from "./pages/Portafolio";
import Ordenes from "./pages/Ordenes";
import Fiscal from "./pages/Fiscal";
import Admin from "./pages/Admin";
import Onboarding from "./pages/Onboarding";
import { RoboAdvisorPanel, OrderPanel, KYCPanel, FiscalPanel, AuditPanel } from "./components/panels";

// ── PWA: registrar service worker ─────────────────────────
if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js")
      .then(reg => console.log("SW registrado:", reg.scope))
      .catch(err => console.log("SW error:", err));
  });
}

// ── Toast ─────────────────────────────────────────────────
function Toast() {
  const { state } = useStore();
  const t = state.toast;
  if (!t) return null;
  const isErr = t.type === "error";
  return (
    <div style={{ position:"fixed", bottom:20, right:20, zIndex:9999,
      background:"#171f2a", border:`1px solid ${isErr?"#f44336":"#17cc85"}`,
      color:isErr?"#f44336":"#17cc85", padding:"10px 18px", borderRadius:10,
      fontSize:11, display:"flex", alignItems:"center", gap:8,
      boxShadow:"0 4px 24px rgba(0,0,0,.7)", maxWidth:380,
      animation:"slideUp .25s ease" }}>
      <i className={`fas ${isErr?"fa-times-circle":"fa-check-circle"}`} style={{ flexShrink:0 }} />
      <span>{t.msg}</span>
    </div>
  );
}

// ── Install PWA banner ────────────────────────────────────
function PWABanner() {
  const [prompt, setPrompt] = useState(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    window.addEventListener("beforeinstallprompt", e => {
      e.preventDefault(); setPrompt(e); setVisible(true);
    });
  }, []);
  if (!visible) return null;
  return (
    <div style={{ position:"fixed", bottom:20, left:20, zIndex:999,
      background:"#111820", border:"1px solid #17cc85", borderRadius:10,
      padding:"12px 16px", display:"flex", alignItems:"center", gap:12,
      boxShadow:"0 4px 24px rgba(0,0,0,.6)", fontSize:11, maxWidth:320 }}>
      <i className="fas fa-mobile-alt" style={{ color:"#17cc85", fontSize:20 }} />
      <div style={{ flex:1, color:"#8fa0b8" }}>
        <div style={{ color:"#dde4f0", fontWeight:600, marginBottom:2 }}>Instalar InvestIQ</div>
        Acceso rápido desde tu pantalla de inicio
      </div>
      <button onClick={()=>{prompt.prompt();setVisible(false);}}
        style={{ background:"#12a068",color:"#fff",border:"none",borderRadius:6,
          padding:"6px 12px",cursor:"pointer",fontSize:10,fontWeight:700,whiteSpace:"nowrap" }}>
        Instalar
      </button>
      <button onClick={()=>setVisible(false)}
        style={{ background:"none",border:"none",color:"#576880",cursor:"pointer",fontSize:14 }}>✕</button>
    </div>
  );
}

// ── Push permission request ───────────────────────────────
function PushPermission() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      setTimeout(() => setShow(true), 5000);
    }
  }, []);
  const solicitar = async () => {
    const perm = await Notification.requestPermission();
    setShow(false);
    if (perm === "granted") {
      new Notification("InvestIQ", {
        body: "Recibirás alertas de tus órdenes y mercado",
        icon: "/logo192.png"
      });
    }
  };
  if (!show) return null;
  return (
    <div style={{ position:"fixed", top:60, right:16, zIndex:999,
      background:"#111820", border:"1px solid #2a3545", borderRadius:10,
      padding:"12px 16px", display:"flex", alignItems:"center", gap:12,
      boxShadow:"0 4px 24px rgba(0,0,0,.6)", fontSize:11, maxWidth:300 }}>
      <i className="fas fa-bell" style={{ color:"#f5a623", fontSize:18 }} />
      <div style={{ flex:1, color:"#8fa0b8" }}>
        <div style={{ color:"#dde4f0", fontWeight:600, marginBottom:2 }}>Activar alertas</div>
        Notificaciones de órdenes y mercado
      </div>
      <div style={{ display:"flex", gap:6, flexDirection:"column" }}>
        <button onClick={solicitar}
          style={{ background:"#f5a623",color:"#fff",border:"none",borderRadius:5,padding:"4px 10px",cursor:"pointer",fontSize:9,fontWeight:700 }}>
          Activar
        </button>
        <button onClick={()=>setShow(false)}
          style={{ background:"none",border:"1px solid #2a3545",color:"#576880",borderRadius:5,padding:"4px 10px",cursor:"pointer",fontSize:9 }}>
          No ahora
        </button>
      </div>
    </div>
  );
}

// ── Router ────────────────────────────────────────────────
const PAGES = {
  dashboard: Dashboard,
  mercado: Mercado,
  portafolio: Portafolio,
  ordenes: Ordenes,
  fiscal: Fiscal,
  admin: Admin,
  onboarding: Onboarding,
  kyc: Onboarding,
};

// ── Inner App ─────────────────────────────────────────────
function InnerApp() {
  const { state, dispatch, actions } = useStore();
  const [wsStatus, setWsStatus] = useState("connecting");

  // WebSocket
  useWebSocket(useCallback((msg) => {
    if (msg.type === "prices" || msg.type === "init") {
      dispatch({ type:"SET_PRICES", payload: msg.data || msg.prices || {} });
      if (msg.type === "init") setWsStatus("connected");
    }
    if (msg.type === "heartbeat" || msg.type === "pong") setWsStatus("connected");
    if (msg.type === "orden") {
      dispatch({ type:"PREPEND_ORDEN", payload: msg.data });
      actions.loadMetricas();
      // Push notification si el browser lo permite
      if ("Notification" in window && Notification.permission === "granted" && msg.data) {
        new Notification("Orden ejecutada", {
          body: `${msg.data.tipo?.toUpperCase()} ${msg.data.ticker} · $${msg.data.monto_usd}`,
          icon: "/logo192.png"
        });
      }
    }
    if (msg.type === "saldo") actions.loadMetricas();
    if (msg.type === "alerta" && msg.data) {
      dispatch({ type:"PREPEND_ALERTA", payload: msg.data });
    }
  }, []));

  // Init
  useEffect(() => {
    actions.loadAll();
    const tid = setTimeout(() => {
      if (state.ttsEnabled && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance("InvestIQ listo. Plataforma de microinversión activa.");
        u.lang = "es-ES"; u.rate = 1.0; u.pitch = 0.85;
        const voices = window.speechSynthesis.getVoices();
        const v = voices.find(v => v.lang.startsWith("es") && !v.name.toLowerCase().includes("female"));
        if (v) u.voice = v;
        window.speechSynthesis.speak(u);
      }
    }, 2500);
    return () => clearTimeout(tid);
  }, []);

  // Auto-refresh
  useEffect(() => {
    const iv = setInterval(() => {
      actions.loadMetricas();
      actions.loadPortafolio();
    }, 20000);
    return () => clearInterval(iv);
  }, []);

  const ActivePage = PAGES[state.activeNav] || Dashboard;

  return (
    <div style={{ background:"#0b0f14", color:"#dde4f0", height:"100vh",
      fontFamily:"'Segoe UI',system-ui,sans-serif", fontSize:12, overflow:"hidden",
      display:"flex", flexDirection:"column" }}>

      <style>{`
        @keyframes slideUp{from{transform:translateY(16px);opacity:0}to{transform:translateY(0);opacity:1}}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
        @keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
        input[type=range]{-webkit-appearance:none;height:4px;border-radius:2px}
        input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:#12a068;cursor:pointer}
        ::-webkit-scrollbar{width:4px;height:4px}
        ::-webkit-scrollbar-track{background:#111820}
        ::-webkit-scrollbar-thumb{background:#2a3545;border-radius:2px}
        select option{background:#1E2835;color:#dde4f0}
        *{box-sizing:border-box}

        /* ── Mobile responsive ── */
        @media (max-width:900px){
          .layout-grid{grid-template-columns:1fr !important}
          .sidebar-desktop{display:none !important}
          .right-panel-desktop{display:none !important}
          .metrics-grid{grid-template-columns:repeat(2,1fr) !important}
          .charts-row{grid-template-columns:1fr !important}
          .two-col{grid-template-columns:1fr !important}
          .nav-pills{display:none !important}
          .abar{flex-wrap:wrap;height:auto !important;padding:6px 10px !important}
          .abar .btn3{padding:6px 10px !important;font-size:10px !important}
        }
        @media (max-width:600px){
          .metrics-grid{grid-template-columns:1fr 1fr !important}
          .topbar{padding:0 10px !important}
          .logo-text{display:none}
          .table-scroll{font-size:10px}
        }
        @media (max-width:400px){
          .metrics-grid{grid-template-columns:1fr !important}
          main{padding:8px !important}
        }

        /* ── Mobile bottom nav ── */
        .mobile-nav{display:none}
        @media (max-width:900px){
          .mobile-nav{
            display:flex;position:fixed;bottom:0;left:0;right:0;
            background:#111820;border-top:1px solid #2a3545;
            height:56px;z-index:300;
          }
          .mobile-nav-item{
            flex:1;display:flex;flex-direction:column;align-items:center;
            justify-content:center;gap:3px;cursor:pointer;
            font-size:9px;color:#576880;transition:color .18s;padding:4px 0;
          }
          .mobile-nav-item.active{color:#17cc85}
          .mobile-nav-item i{font-size:18px}
          main{padding-bottom:64px !important}
        }
      `}</style>

      <Topbar wsStatus={wsStatus} />
      <ActionBar />
      <TickerBar />

      <div className="layout-grid" style={{ display:"grid", gridTemplateColumns:"190px 1fr 268px", flex:1, overflow:"hidden", minHeight:0 }}>
        <div className="sidebar-desktop" style={{display:"contents"}}><Sidebar /></div>
        <main style={{ overflowY:"auto", padding:14, background:"#0b0f14" }}>
          <ActivePage />
        </main>
        <div className="right-panel-desktop" style={{display:"contents"}}><RightPanel prices={state.prices} /></div>
      </div>

      {/* Floating panels */}
      <RoboAdvisorPanel />
      <OrderPanel prices={state.prices} />
      <KYCPanel />
      <FiscalPanel />
      <AuditPanel />

      {/* Global UI */}
      <Toast />
      <PWABanner />
      <PushPermission />

      {/* Mobile bottom navigation */}
      <nav className="mobile-nav">
        {[
          {key:"dashboard",icon:"fa-tachometer-alt",label:"Home"},
          {key:"mercado",icon:"fa-chart-candlestick",label:"Mercado"},
          {key:"portafolio",icon:"fa-briefcase",label:"Portafolio"},
          {key:"ordenes",icon:"fa-bolt",label:"Órdenes"},
          {key:"fiscal",icon:"fa-wallet",label:"Cuenta"},
        ].map(item=>(
          <div key={item.key}
            className={"mobile-nav-item" + (state.activeNav===item.key?" active":"")}
            onClick={()=>actions.setNav(item.key)}>
            <i className={`fas ${item.icon}`} />
            <span>{item.label}</span>
          </div>
        ))}
      </nav>
    </div>
  );
}

export default function App() {
  return <StoreProvider><InnerApp /></StoreProvider>;
}
