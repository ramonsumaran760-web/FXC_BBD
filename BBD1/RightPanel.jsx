// components/layout/RightPanel.jsx — Panel derecho completo
import React, { useState } from "react";
import { useStore } from "../../store/store";
import { useLiveClock, useTTS } from "../../hooks";

const C = { bg2:"#111820", bg3:"#171f2a", bg4:"#1E2835", border:"#2a3545",
  g:"#17cc85", g2:"#12a068", b:"#2196f3", a:"#f5a623", r:"#f44336", p:"#ab47bc", t:"#26c6da",
  text:"#dde4f0", text2:"#8fa0b8", text3:"#576880", text4:"#3a4e65" };

const fmtUSD = n => `$${parseFloat(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;

export default function RightPanel({ prices = {} }) {
  const { state, actions } = useStore();
  const { speak } = useTTS(state.ttsEnabled);
  const now = useLiveClock();
  const timeStr = now.toTimeString().slice(0, 8);
  const dateStr = now.toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const [taskInput, setTaskInput] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [monto, setMonto] = useState(25);
  const [tipo, setTipo] = useState("buy");
  const price = prices[ticker]?.price || 0;
  const fracs = price > 0 ? (monto / price).toFixed(8) : "—";
  const tasksDone = state.tasks.filter(t => t.completada).length;
  const unread = state.alertas.filter(a => !a.leida).length;

  const ejecutarOrden = async () => {
    const r = await actions.crearOrden({ ticker, monto_usd: monto, tipo });
    if (r) speak(`Orden ${tipo} ejecutada. ${fracs} acciones de ${ticker} por ${fmtUSD(monto)}. Firma verificada.`);
  };

  return (
    <aside style={{ background: C.bg2, borderLeft: `1px solid ${C.border}`,
      display: "flex", flexDirection: "column", overflowY: "auto" }}>

      {/* ── Clock ── */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}`, textAlign: "center" }}>
        <div style={{ fontSize: 30, fontWeight: 700, color: C.g, letterSpacing: 3,
          fontVariantNumeric: "tabular-nums", textShadow: `0 0 18px rgba(23,204,133,.2)` }}>{timeStr}</div>
        <div style={{ fontSize: 9, color: C.text2, marginTop: 3 }}>{dateStr}</div>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 9, marginTop: 6,
          padding: "3px 10px", borderRadius: 9, background: "rgba(23,204,133,.1)", color: C.g,
          border: "1px solid rgba(23,204,133,.2)" }}>
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: C.g,
            animation: "blink 1.5s infinite", display: "inline-block" }} />
          NYSE · Mercado abierto
        </div>
      </div>

      {/* ── Portafolio mini ── */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 10 }}>
          <i className="fas fa-briefcase" style={{ color: C.g, marginRight: 6 }} />Portafolio en vivo
        </div>
        {(state.portafolio.posiciones || []).map(p => {
          const live = prices[p.ticker]?.price || p.precio_actual;
          const pct = p.precio_promedio_compra > 0 ? (live - p.precio_promedio_compra) / p.precio_promedio_compra * 100 : 0;
          const up = pct >= 0;
          const TICK_COLORS = { AAPL:"#0D7A4E", MSFT:"#0D3D7A", NVDA:"#4A0D7A", TSLA:"#7A4E0D", AMZN:"#6B0D3A", SPY:"#2D5C1A" };
          return (
            <div key={p.ticker} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0",
              borderBottom: `1px solid rgba(42,53,69,.3)` }}>
              <div style={{ width: 30, height: 30, borderRadius: 7, flexShrink: 0, fontSize: 8, fontWeight: 700,
                background: TICK_COLORS[p.ticker] || "#1a3a5c",
                display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}>{p.ticker}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: C.text }}>{p.ticker}</div>
                <div style={{ fontSize: 9, color: C.text3 }}>{parseFloat(p.acciones).toFixed(4)} acc.</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{fmtUSD(live)}</div>
                <div style={{ fontSize: 9, color: up ? C.g : C.r }}>{up ? "+" : ""}{pct.toFixed(2)}%</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Quick Order ── */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 8 }}>
          <i className="fas fa-bolt" style={{ color: C.a, marginRight: 6 }} />Orden rápida fraccionada
        </div>
        <div style={{ display: "flex", border: `1px solid ${C.border}`, borderRadius: 6, overflow: "hidden", marginBottom: 8 }}>
          {["buy","sell"].map(t => (
            <div key={t} onClick={() => setTipo(t)}
              style={{ flex: 1, textAlign: "center", padding: 6, fontSize: 10, cursor: "pointer", fontWeight: 600,
                background: tipo === t ? (t==="buy"?"rgba(23,204,133,.2)":"rgba(244,67,54,.15)") : "transparent",
                color: tipo === t ? (t==="buy"?C.g:C.r) : C.text2 }}>
              {t === "buy" ? "COMPRAR" : "VENDER"}
            </div>
          ))}
        </div>
        <div style={{ marginBottom: 6 }}>
          <select value={ticker} onChange={e => setTicker(e.target.value)}
            style={{ width:"100%", background:C.bg4, border:`1px solid ${C.border}`, color:C.text, padding:"6px 9px", borderRadius:6, fontSize:11, outline:"none" }}>
            {["AAPL","MSFT","TSLA","NVDA","AMZN","GOOGL","META","SPY","QQQ","BND"].map(t => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div style={{ marginBottom: 6 }}>
          <input type="number" value={monto} min={1} step={1}
            onChange={e => setMonto(Math.max(1, parseFloat(e.target.value)||1))}
            style={{ width:"100%", background:C.bg4, border:`1px solid ${C.border}`, color:C.text, padding:"6px 9px", borderRadius:6, fontSize:11, outline:"none" }} />
        </div>
        <div style={{ fontSize: 9, color: C.text2, marginBottom: 4 }}>
          Precio: <b style={{ color: C.g }}>{fmtUSD(price)}</b> · Acciones: <b style={{ color: C.text }}>{fracs}</b>
        </div>
        <button onClick={ejecutarOrden} disabled={state.loading.orden}
          style={{ width:"100%", padding:8, borderRadius:6, border:"none", cursor:"pointer",
            background: tipo==="buy" ? C.g2 : C.r, color:"#fff", fontSize:11, fontWeight:700,
            boxShadow:`0 0 12px rgba(${tipo==="buy"?"18,160,104":"244,67,54"},.3)`,
            opacity: state.loading.orden ? 0.7 : 1 }}>
          <i className="fas fa-bolt" style={{ marginRight: 5 }} />
          {state.loading.orden ? "Ejecutando…" : `${tipo==="buy"?"Comprar":"Vender"} · ECDSA`}
        </button>
      </div>

      {/* ── Robo-Advisor mini ── */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ background:"linear-gradient(135deg,rgba(74,13,122,.12),rgba(13,61,122,.08))",
          border:"1px solid rgba(123,31,162,.25)", borderRadius:10, padding:12 }}>
          <div style={{ display:"flex", alignItems:"center", gap:7, marginBottom:8 }}>
            <span style={{ width:7, height:7, borderRadius:"50%", background:C.p, animation:"blink 1.8s infinite", display:"inline-block" }} />
            <span style={{ fontSize:11, fontWeight:600, color:C.p }}>Motor IA · Robo-Advisor</span>
          </div>
          <div style={{ fontSize:10, color:C.text2, lineHeight:1.6, marginBottom:9 }}>
            {state.roboResult
              ? `Perfil: ${state.roboResult.perfil} · Score: ${state.roboResult.score_riesgo}/100`
              : "Listo para analizar portafolio con Claude API."}
          </div>
          <button onClick={() => { actions.openPanel("robo"); speak("Abriendo panel de Robo-Advisor con inteligencia artificial."); }}
            style={{ background:"rgba(123,31,162,.25)", color:C.p, border:"1px solid rgba(123,31,162,.35)",
              padding:"6px 10px", borderRadius:6, fontSize:10, cursor:"pointer", width:"100%", textAlign:"center" }}>
            <i className="fas fa-brain" style={{ marginRight:5 }} />Analizar con IA ↗
          </button>
        </div>
      </div>

      {/* ── Checklist ── */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize:11, fontWeight:600, color:C.text, display:"flex", alignItems:"center", gap:6, marginBottom:10 }}>
          <i className="fas fa-check-square" style={{ color:C.g }} />
          Checklist fiscal
          <span style={{ marginLeft:"auto", fontSize:9, color:C.text3 }}>{tasksDone}/{state.tasks.length}</span>
        </div>
        {state.tasks.map(t => (
          <div key={t.id} onClick={() => actions.toggleTask(t.id)}
            style={{ display:"flex", alignItems:"center", gap:7, padding:"5px 3px", borderRadius:4, cursor:"pointer",
              opacity: t.completada ? 0.5 : 1 }}>
            <div style={{ width:14, height:14, borderRadius:3,
              border:`1.5px solid ${t.completada ? C.g2 : C.border}`,
              background: t.completada ? C.g2 : "transparent",
              display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
              {t.completada && <i className="fas fa-check" style={{ fontSize:8, color:"#fff" }} />}
            </div>
            <span style={{ flex:1, fontSize:10, color:C.text2,
              textDecoration: t.completada ? "line-through" : "none" }}>{t.titulo}</span>
            <span style={{ fontSize:7, padding:"1px 4px", borderRadius:3, fontWeight:700,
              background: t.prioridad===3?"rgba(244,67,54,.25)":t.prioridad===2?"rgba(245,166,35,.25)":"rgba(33,150,243,.2)",
              color: t.prioridad===3?C.r:t.prioridad===2?C.a:C.b }}>
              {t.prioridad===3?"ALTA":t.prioridad===2?"MED":"BAJA"}
            </span>
          </div>
        ))}
        <div style={{ display:"flex", gap:5, marginTop:8 }}>
          <input value={taskInput} onChange={e => setTaskInput(e.target.value)}
            onKeyDown={e => { if(e.key==="Enter"&&taskInput.trim()){ actions.addTask(taskInput); setTaskInput(""); }}}
            placeholder="Nueva tarea…"
            style={{ flex:1, background:C.bg4, border:`1px solid ${C.border}`, color:C.text,
              padding:"5px 8px", borderRadius:6, fontSize:10, outline:"none" }} />
          <button onClick={() => { if(taskInput.trim()){ actions.addTask(taskInput); setTaskInput(""); }}}
            style={{ background:C.g2, color:"#fff", border:"none", borderRadius:6, padding:"5px 9px", cursor:"pointer", fontWeight:700 }}>
            <i className="fas fa-plus" />
          </button>
        </div>
      </div>

      {/* ── Alertas ── */}
      <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize:11, fontWeight:600, color:C.text, display:"flex", alignItems:"center", gap:6, marginBottom:10 }}>
          <i className="fas fa-exclamation-triangle" style={{ color:C.a }} />
          Alertas IA
          <span style={{ marginLeft:"auto", fontSize:9, background:C.bg4, padding:"2px 7px", borderRadius:8, color:C.text3 }}>{unread} nuevas</span>
        </div>
        {state.alertas.slice(0, 6).map(a => {
          const col = a.tipo==="danger"?C.r:a.tipo==="warning"?C.a:C.b;
          const ico = a.tipo==="danger"?"fa-times-circle":a.tipo==="warning"?"fa-exclamation-triangle":"fa-info-circle";
          return (
            <div key={a.id} onClick={() => actions.leerAlerta(a.id)}
              style={{ display:"flex", gap:7, padding:7, borderRadius:6, marginBottom:5, cursor:"pointer",
                borderLeft:`3px solid ${col}`, background:`${col}11`, opacity: a.leida ? 0.35 : 1 }}>
              <i className={`fas ${ico}`} style={{ color:col, fontSize:12, marginTop:1, flexShrink:0 }} />
              <div>
                <div style={{ fontSize:10, color:C.text, fontWeight:600 }}>{a.titulo}</div>
                <div style={{ fontSize:9, color:C.text2, lineHeight:1.4 }}>{a.mensaje?.slice(0,80)}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── TTS bar ── */}
      <div style={{ padding:"8px 12px", display:"flex", alignItems:"center", gap:10, marginTop:"auto",
        borderTop:`1px solid ${C.border}` }}>
        <i className="fas fa-microphone" style={{ fontSize:13, color:C.g2, flexShrink:0 }} />
        <span style={{ flex:1, fontSize:10, color:C.text2, fontStyle:"italic" }}>
          {state.ttsEnabled ? "Voz activa · Web Speech API (español hombre)" : "Narración desactivada"}
        </span>
        <button onClick={() => { actions.setTTS(!state.ttsEnabled); if(!state.ttsEnabled) speak("Narración activada."); }}
          style={{ width:26, height:26, borderRadius:5, border:`1px solid ${state.ttsEnabled?C.g2:C.border}`,
            background: state.ttsEnabled?"rgba(23,204,133,.15)":"transparent",
            color: state.ttsEnabled?C.g:C.text2, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center" }}>
          <i className={`fas fa-volume-${state.ttsEnabled?"up":"mute"}`} />
        </button>
        <button onClick={() => window.speechSynthesis?.cancel()}
          style={{ width:26, height:26, borderRadius:5, border:`1px solid ${C.border}`,
            background:"transparent", color:C.text2, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center" }}>
          <i className="fas fa-stop" />
        </button>
      </div>
    </aside>
  );
}
