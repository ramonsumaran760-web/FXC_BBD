// components/layout/ActionBar.jsx
import React, { useState } from "react";
import { useStore } from "../../store/store";
import api from "../../services/api";

function Btn3D({ label, icon, onClick, color, dark, glow = "none", style = {} }) {
  const [pressed, setPressed] = useState(false);
  return (
    <button onClick={onClick}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      onMouseLeave={() => setPressed(false)}
      style={{ border: "none", padding: "7px 13px", borderRadius: 6, cursor: "pointer",
        fontSize: 11, fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 5,
        color: "#fff", textTransform: "uppercase", letterSpacing: .4, whiteSpace: "nowrap",
        background: color, transition: "all .12s",
        boxShadow: pressed ? "none" : `0 6px 0 ${dark},0 8px 18px rgba(0,0,0,.5),0 0 16px ${glow}`,
        transform: pressed ? "translateY(4px)" : "translateY(0)", ...style }}>
      {icon && <i className={`fas ${icon}`} />}
      {label}
    </button>
  );
}

export default function ActionBar() {
  const { state, actions } = useStore();
  const { ttsEnabled } = state;

  const handleDepositar = async () => {
    const monto = parseFloat(prompt("Monto a depositar (USD):") || "0");
    if (monto > 0) await actions.depositar(monto);
  };

  return (
    <div style={{ height: 46, background: "#111820", borderBottom: "1px solid #2a3545",
      display: "flex", alignItems: "center", padding: "0 12px", gap: 6, overflowX: "auto" }}>

      <Btn3D label="Comprar / Vender" icon="fa-bolt" color="#12a068" dark="#065c34"
        glow="rgba(18,160,104,.3)" onClick={() => actions.openPanel("ordenes")} />
      <Btn3D label="Robo-Advisor IA" icon="fa-robot" color="#7b1fa2" dark="#3d0066"
        glow="rgba(123,31,162,.3)" onClick={() => actions.openPanel("robo")} />
      <Btn3D label="KYC / AML" icon="fa-id-card" color="#1565c0" dark="#0d3060"
        glow="rgba(21,101,192,.3)" onClick={() => actions.openPanel("kyc")} />
      <Btn3D label="Pre-cierre Fiscal" icon="fa-file-invoice-dollar" color="#c47a10" dark="#6b4200"
        glow="rgba(196,122,16,.3)" onClick={() => actions.openPanel("fiscal")} />
      <Btn3D label="Depositar" icon="fa-plus-circle" color="#00838f" dark="#004040"
        glow="rgba(0,131,143,.3)" onClick={handleDepositar} />

      <div style={{ width: 1, height: 22, background: "#2a3545", flexShrink: 0, margin: "0 4px" }} />

      <Btn3D label="Excel" icon="fa-file-excel" color="#1565c0" dark="#0d3060"
        glow="rgba(21,101,192,.3)" onClick={() => api.exportarExcel()} />
      <Btn3D label="PDF" icon="fa-file-pdf" color="#c41a1a" dark="#660000"
        glow="rgba(196,26,26,.3)" onClick={() => api.exportarPDF()} />

      <div style={{ width: 1, height: 22, background: "#2a3545", flexShrink: 0, margin: "0 4px" }} />

      <Btn3D label="Refresh" icon="fa-sync-alt" color="#252f3e" dark="#0b0f14"
        onClick={() => actions.loadAll()} style={{ border: "1px solid #2a3545" }} />

      <Btn3D label={ttsEnabled ? "Voz ON" : "Voz OFF"} icon={`fa-volume-${ttsEnabled ? "up" : "mute"}`}
        color={ttsEnabled ? "#0D7A4E" : "#252f3e"} dark="#0b0f14"
        glow={ttsEnabled ? "rgba(13,122,78,.3)" : "none"}
        onClick={() => actions.setTTS(!ttsEnabled)}
        style={{ border: "1px solid #2a3545" }} />
    </div>
  );
}
