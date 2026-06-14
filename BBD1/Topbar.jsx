// components/layout/Topbar.jsx
import React from "react";
import { useStore } from "../../store/store";
import { useLiveClock } from "../../hooks";

const C = { bg2:"#111820", border:"#2a3545", g:"#17cc85", g2:"#12a068", text:"#dde4f0", text2:"#8fa0b8" };

export default function Topbar({ wsStatus }) {
  const { state, actions } = useStore();
  const now = useLiveClock();
  const timeStr = now.toTimeString().slice(0, 8);
  const unread = state.unreadAlerts;

  return (
    <div style={{ height: 52, background: C.bg2, borderBottom: `1px solid ${C.border}`,
      display: "flex", alignItems: "center", padding: "0 16px", gap: 12, position: "sticky", top: 0, zIndex: 200 }}>

      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 15, fontWeight: 700, whiteSpace: "nowrap" }}>
        <div style={{ width: 30, height: 30, borderRadius: 7,
          background: "linear-gradient(135deg,#12a068,#1565c0)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 0 14px rgba(18,160,104,.2)" }}>
          <i className="fas fa-chart-line" style={{ color: "#fff", fontSize: 13 }} />
        </div>
        InvestIQ
      </div>

      {/* Nav pills */}
      <div style={{ display: "flex", gap: 2, flex: 1, overflowX: "auto" }}>
        {[
          { key: "dashboard", label: "Dashboard" },
          { key: "mercado", label: "Mercado Live" },
          { key: "portafolio", label: "Portafolio" },
          { key: "ordenes", label: "Órdenes" },
          { key: "fiscal", label: "Fiscal" },
          { key: "admin", label: "Owner Portal" },
        ].map(n => (
          <button key={n.key} onClick={() => actions.setNav(n.key)}
            style={{ padding: "5px 12px", borderRadius: 4, fontSize: 11, border: "none", cursor: "pointer",
              background: state.activeNav === n.key ? "#1E2835" : "transparent",
              color: state.activeNav === n.key ? C.text : C.text2, transition: "all .2s" }}>
            {n.label}
          </button>
        ))}
      </div>

      {/* Right */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
        {/* WS status */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: C.g,
          padding: "3px 9px", borderRadius: 10, background: "rgba(23,204,133,.1)", border: "1px solid rgba(23,204,133,.2)" }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%",
            background: wsStatus === "connected" ? C.g : "#f44336",
            display: "inline-block", animation: "blink 1.2s infinite" }} />
          {wsStatus === "connected" ? "EN VIVO" : "RECONECTANDO"}
        </div>

        {/* Clock */}
        <div style={{ fontSize: 16, fontWeight: 700, color: C.g, letterSpacing: 2, fontVariantNumeric: "tabular-nums" }}>
          {timeStr}
        </div>

        {/* Alerts bell */}
        <div style={{ position: "relative", cursor: "pointer" }}
          onClick={() => actions.openPanel("audit")}>
          <i className="fas fa-bell" style={{ fontSize: 18, color: C.text2 }} />
          {unread > 0 && (
            <span style={{ position: "absolute", top: -5, right: -5, background: "#c41a1a",
              color: "#fff", fontSize: 8, width: 15, height: 15, borderRadius: "50%",
              display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}>
              {unread}
            </span>
          )}
        </div>

        {/* TTS toggle */}
        <button onClick={() => actions.setTTS(!state.ttsEnabled)}
          style={{ width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", border: `1px solid ${state.ttsEnabled ? C.g2 : C.border}`,
            background: state.ttsEnabled ? "rgba(23,204,133,.15)" : "transparent",
            color: state.ttsEnabled ? C.g : C.text2, fontSize: 14 }}>
          <i className={`fas fa-volume-${state.ttsEnabled ? "up" : "mute"}`} />
        </button>

        {/* Avatar */}
        <div style={{ width: 32, height: 32, borderRadius: "50%",
          background: "linear-gradient(135deg,#7b1fa2,#1565c0)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 700, cursor: "pointer" }}>
          IN
        </div>
      </div>
    </div>
  );
}
