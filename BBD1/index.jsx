// components/panels/index.jsx — Todos los paneles flotantes
import React, { useRef, useState, useEffect } from "react";
import { useStore } from "../../store/store";
import { useTTS } from "../../hooks";
import api from "../../services/api";

const C = { bg2:"#111820", bg3:"#171f2a", bg4:"#1E2835", border:"#2a3545", border2:"#3a4a60",
  g:"#17cc85", g2:"#12a068", b:"#2196f3", a:"#f5a623", r:"#f44336", p:"#ab47bc", t:"#26c6da",
  text:"#dde4f0", text2:"#8fa0b8", text3:"#576880" };

// ── Draggable wrapper ─────────────────────────────────────
export function FloatPanel({ panelKey, title, icon, color = C.g, children, initialPos = { top: 90, left: 220 } }) {
  const { state, actions } = useStore();
  const [pos, setPos] = useState(initialPos);
  const drag = useRef(false); const off = useRef({});
  const visible = state.panels[panelKey];

  useEffect(() => {
    const mv = e => { if (drag.current) setPos({ left: e.clientX - off.current.x, top: e.clientY - off.current.y }); };
    const up = () => drag.current = false;
    document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
    return () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); };
  }, []);

  if (!visible) return null;
  return (
    <div style={{ position: "fixed", top: pos.top, left: pos.left, background: C.bg2,
      border: `1px solid ${C.border2}`, borderRadius: 10, zIndex: 500, minWidth: 340,
      boxShadow: "0 20px 60px rgba(0,0,0,.7)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: `2px solid ${color}`,
        background: C.bg3, borderRadius: "10px 10px 0 0", cursor: "move" }}
        onMouseDown={e => { drag.current = true; off.current = { x: e.clientX - pos.left, y: e.clientY - pos.top }; }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>
          <i className={`fas ${icon}`} style={{ color, marginRight: 7 }} />{title}
        </span>
        <button onClick={() => actions.closePanel(panelKey)}
          style={{ background: "none", border: "none", color: C.text3, cursor: "pointer", fontSize: 14, padding: "2px 5px" }}>✕</button>
      </div>
      <div style={{ padding: 14, maxHeight: "72vh", overflowY: "auto" }}>{children}</div>
    </div>
  );
}

// ── Robo-Advisor Panel ────────────────────────────────────
export function RoboAdvisorPanel() {
  const { state, actions } = useStore();
  const { speak } = useTTS(state.ttsEnabled);
  const [form, setForm] = useState({ edad: 30, ingresos_anuales_usd: 15000, tolerancia_riesgo: "moderada" });
  const result = state.roboResult;
  const loading = state.loading.robo;

  const ejecutar = async () => {
    const r = await actions.ejecutarRobo(form);
    if (r) speak(r.explicacion_voz || `Tu perfil es ${r.perfil}. Score de riesgo: ${r.score_riesgo} de 100.`);
  };

  return (
    <FloatPanel panelKey="robo" title="Robo-Advisor IA — Prompts JSON → Claude" icon="fa-robot" color={C.p} initialPos={{ top: 85, left: 210 }}>
      <div style={{ minWidth: 380 }}>
        <div style={{ fontSize: 10, color: C.text2, marginBottom: 12, lineHeight: 1.6,
          background: C.bg4, padding: 8, borderRadius: 6, borderLeft: `3px solid ${C.p}` }}>
          El perfil se envía como Prompt JSON a Claude API → recibe JSON estructurado con análisis de riesgo.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
          <div><div style={{ fontSize: 9, color: C.text3, textTransform: "uppercase", marginBottom: 3 }}>Edad</div>
            <input type="number" value={form.edad} min={18} max={90} style={inpStyle}
              onChange={e => setForm(f => ({ ...f, edad: parseInt(e.target.value) || 30 }))} /></div>
          <div><div style={{ fontSize: 9, color: C.text3, textTransform: "uppercase", marginBottom: 3 }}>Ingresos anuales USD</div>
            <input type="number" value={form.ingresos_anuales_usd} style={inpStyle}
              onChange={e => setForm(f => ({ ...f, ingresos_anuales_usd: parseFloat(e.target.value) || 15000 }))} /></div>
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 9, color: C.text3, textTransform: "uppercase", marginBottom: 3 }}>Tolerancia al riesgo</div>
          <select value={form.tolerancia_riesgo} onChange={e => setForm(f => ({ ...f, tolerancia_riesgo: e.target.value }))} style={selStyle}>
            <option value="baja">Baja — Conservador</option>
            <option value="moderada">Moderada — Moderado</option>
            <option value="alta">Alta — Agresivo</option>
          </select>
        </div>

        <button disabled={loading} onClick={ejecutar}
          style={{ width: "100%", padding: "9px", borderRadius: 6, border: "none", cursor: "pointer",
            background: loading ? "#3d0066" : C.p, color: "#fff", fontSize: 11, fontWeight: 700,
            boxShadow: `0 0 16px rgba(123,31,162,.3)` }}>
          <i className="fas fa-brain" style={{ marginRight: 6 }} />
          {loading ? "Analizando con Claude IA…" : "Ejecutar análisis con Claude"}
        </button>

        {result && (
          <div style={{ marginTop: 14 }}>
            {/* Prompt JSON enviado */}
            <div style={{ fontSize: 9, color: C.text3, marginBottom: 6, textTransform: "uppercase" }}>
              Prompt JSON enviado → Claude API
            </div>
            <pre style={{ background: C.bg4, padding: 8, borderRadius: 6, fontSize: 8,
              color: "#64b5f6", overflowX: "auto", marginBottom: 10, border: `1px solid ${C.border}` }}>
              {JSON.stringify(result._prompt_json_enviado || {}, null, 2)}
            </pre>

            {/* Resultado */}
            <div style={{ fontSize: 9, color: C.text3, marginBottom: 6, textTransform: "uppercase" }}>
              Respuesta JSON ← Claude API
            </div>
            {[
              ["Perfil IA", result.perfil?.toUpperCase(), C.p],
              ["Score riesgo", `${result.score_riesgo}/100`, result.score_riesgo > 65 ? C.r : C.g],
              ["Alerta riesgo", result.alerta_riesgo ? "⚠ SÍ — Rebalancear" : "✓ Sin alerta", result.alerta_riesgo ? C.a : C.g],
              ["Concentración máx.", `${result.concentracion_max_ticker} ${result.concentracion_max_pct}%`,
               result.concentracion_max_pct > 35 ? C.a : C.g],
              ["Sugerencia", result.sugerencia_rebalanceo, C.text2],
              ["Modelo IA", result._modelo || "local_deterministic", C.text3],
            ].map(([l, v, col]) => (
              <div key={l} style={{ background: C.bg4, borderRadius: 6, padding: "7px 10px", marginBottom: 5 }}>
                <div style={{ fontSize: 9, color: C.text3, textTransform: "uppercase", marginBottom: 2 }}>{l}</div>
                <div style={{ fontSize: 11, color: col, fontWeight: 600, lineHeight: 1.4 }}>{v}</div>
              </div>
            ))}
            <div style={{ background: C.bg4, borderRadius: 6, padding: "7px 10px", marginBottom: 5 }}>
              <div style={{ fontSize: 9, color: C.text3, textTransform: "uppercase", marginBottom: 4 }}>Recomendaciones</div>
              {(result.acciones_recomendadas || []).map((a, i) => (
                <div key={i} style={{ fontSize: 10, color: C.g, marginBottom: 3 }}>→ {a}</div>
              ))}
            </div>
          </div>
        )}
      </div>
    </FloatPanel>
  );
}

// ── Order Panel ───────────────────────────────────────────
export function OrderPanel({ prices = {} }) {
  const { state, actions } = useStore();
  const { speak } = useTTS(state.ttsEnabled);
  const [ticker, setTicker] = useState("AAPL");
  const [monto, setMonto] = useState(25);
  const [tipo, setTipo] = useState("buy");
  const [tipoOrden, setTipoOrden] = useState("market");
  const [limitPrice, setLimitPrice] = useState("");
  const loading = state.loading.orden;
  const price = prices[ticker]?.price || 0;
  const fracs = price > 0 ? (monto / price).toFixed(8) : "—";

  const ejecutar = async () => {
    const r = await actions.crearOrden({ ticker, monto_usd: monto, tipo, tipo_orden: tipoOrden,
      limit_price: tipoOrden === "limit" ? parseFloat(limitPrice) : undefined });
    if (r) {
      speak(`Orden ${tipo} ejecutada. ${fracs} acciones de ${ticker} por $${monto}. Firma E C D S A verificada.`);
      actions.closePanel("ordenes");
    }
  };

  return (
    <FloatPanel panelKey="ordenes" title="Orden Fraccionada — Alpaca Paper" icon="fa-bolt" color={C.a} initialPos={{ top: 85, left: 240 }}>
      <div style={{ minWidth: 340 }}>
        <div style={{ display: "flex", border: `1px solid ${C.border}`, borderRadius: 6, overflow: "hidden", marginBottom: 12 }}>
          {["buy","sell"].map(t => (
            <div key={t} onClick={() => setTipo(t)}
              style={{ flex: 1, textAlign: "center", padding: 7, fontSize: 11, cursor: "pointer", fontWeight: 600,
                background: tipo === t ? (t === "buy" ? "rgba(23,204,133,.2)" : "rgba(244,67,54,.2)") : "transparent",
                color: tipo === t ? (t === "buy" ? C.g : C.r) : C.text2 }}>
              {t === "buy" ? "COMPRAR" : "VENDER"}
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 8 }}>
          <div style={lblStyle}>Activo</div>
          <select value={ticker} onChange={e => setTicker(e.target.value)} style={selStyle}>
            {["AAPL","MSFT","TSLA","NVDA","AMZN","GOOGL","META","SPY","QQQ","BND","VTI","GLD"].map(t => <option key={t}>{t}</option>)}
          </select>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
          <div><div style={lblStyle}>Monto USD (mín. $1)</div>
            <input type="number" value={monto} min={1} step={1} style={inpStyle}
              onChange={e => setMonto(Math.max(1, parseFloat(e.target.value) || 1))} /></div>
          <div><div style={lblStyle}>Tipo de orden</div>
            <select value={tipoOrden} onChange={e => setTipoOrden(e.target.value)} style={selStyle}>
              <option value="market">Market</option>
              <option value="limit">Limit</option>
            </select>
          </div>
        </div>

        {tipoOrden === "limit" && (
          <div style={{ marginBottom: 8 }}>
            <div style={lblStyle}>Precio límite USD</div>
            <input type="number" value={limitPrice} style={inpStyle}
              onChange={e => setLimitPrice(e.target.value)} placeholder="0.00" />
          </div>
        )}

        <div style={{ background: C.bg4, borderRadius: 6, padding: "8px 10px", marginBottom: 12, fontSize: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
            <span style={{ color: C.text2 }}>Precio actual</span>
            <span style={{ color: C.g, fontWeight: 700 }}>${price.toLocaleString("en-US", { maximumFractionDigits: 4 })}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
            <span style={{ color: C.text2 }}>Acciones a recibir ≈</span>
            <span style={{ color: C.text, fontWeight: 600 }}>{fracs}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
            <span style={{ color: C.text2 }}>Comisión</span>
            <span style={{ color: C.g }}>$0.00</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: C.text2 }}>Firma ECDSA P-256</span>
            <span style={{ color: C.g }}>✓ Automática</span>
          </div>
        </div>

        <button disabled={loading} onClick={ejecutar}
          style={{ width: "100%", padding: 9, borderRadius: 6, border: "none", cursor: "pointer",
            background: tipo === "buy" ? C.g2 : C.r, color: "#fff", fontSize: 11, fontWeight: 700,
            boxShadow: `0 0 12px rgba(${tipo === "buy" ? "18,160,104" : "244,67,54"},.3)`, opacity: loading ? 0.7 : 1 }}>
          <i className="fas fa-bolt" style={{ marginRight: 6 }} />
          {loading ? "Ejecutando en Alpaca…" : `${tipo === "buy" ? "Comprar" : "Vender"} · Firmado ECDSA`}
        </button>
      </div>
    </FloatPanel>
  );
}

// ── KYC Panel ─────────────────────────────────────────────
export function KYCPanel() {
  const { state, actions } = useStore();
  const { speak } = useTTS(state.ttsEnabled);
  const [form, setForm] = useState({ tipo_doc: "cedula", num_doc: "", pais: "CO" });
  const [amlResult, setAmlResult] = useState(null);

  const submitKYC = async () => {
    try {
      const r = await api.submitKYC(form);
      actions.toast(`KYC ${r.nivel} aprobado`, "success");
      speak("Verificación de identidad KYC completada exitosamente.");
    } catch (e) { actions.toast(e.message, "error"); }
  };

  const checkAML = async () => {
    try {
      const r = await api.amlCheck("Mi Empresa S.A.S", "900123456-7");
      setAmlResult(r);
      speak(`Verificación AML completada. Estado: ${r.status}. ${r.detalle}`);
    } catch (e) { actions.toast(e.message, "error"); }
  };

  return (
    <FloatPanel panelKey="kyc" title="KYC / AML — Verificación de Identidad" icon="fa-id-card" color={C.b} initialPos={{ top: 85, left: 260 }}>
      <div style={{ minWidth: 360 }}>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 10 }}>Estado KYC</div>
          {[
            ["KYC Básico (documento)", "✓ Verificado", C.g],
            ["AML / OFAC", "✓ Clear", C.g],
            ["Biometría (selfie)", "⚠ Pendiente", C.a],
            ["MFA 2FA", "✗ Inactivo", C.r],
            ["Firma ECDSA", "✓ Activa", C.g],
          ].map(([l, v, col]) => (
            <div key={l} style={{ display: "flex", justifyContent: "space-between", padding: "7px 0",
              borderBottom: `1px solid ${C.bg4}`, fontSize: 11 }}>
              <span style={{ color: C.text2 }}>{l}</span>
              <span style={{ color: col, fontWeight: 600 }}>{v}</span>
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 8 }}>Subir documento</div>
          <div style={{ marginBottom: 6 }}>
            <div style={lblStyle}>Tipo de documento</div>
            <select value={form.tipo_doc} onChange={e => setForm(f => ({ ...f, tipo_doc: e.target.value }))} style={selStyle}>
              <option value="cedula">Cédula de ciudadanía</option>
              <option value="pasaporte">Pasaporte</option>
              <option value="dni">DNI</option>
            </select>
          </div>
          <div style={{ marginBottom: 6 }}>
            <div style={lblStyle}>Número de documento</div>
            <input value={form.num_doc} onChange={e => setForm(f => ({ ...f, num_doc: e.target.value }))}
              style={inpStyle} placeholder="123456789" />
          </div>
          <button onClick={submitKYC} style={{ ...btnStyle, background: C.b, width: "100%", marginBottom: 8 }}>
            <i className="fas fa-id-card" style={{ marginRight: 5 }} />Enviar KYC
          </button>
        </div>

        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 8 }}>Verificación AML/OFAC</div>
          <button onClick={checkAML} style={{ ...btnStyle, background: "#c47a10", width: "100%", marginBottom: 8 }}>
            <i className="fas fa-search" style={{ marginRight: 5 }} />Verificar OpenSanctions + OFAC
          </button>
          {amlResult && (
            <div style={{ background: C.bg4, borderRadius: 6, padding: 10, fontSize: 10 }}>
              <div style={{ color: amlResult.status === "clear" ? C.g : C.r, fontWeight: 700, marginBottom: 4 }}>
                Estado: {amlResult.status?.toUpperCase()}
              </div>
              <div style={{ color: C.text2 }}>{amlResult.detalle}</div>
              <div style={{ color: C.text3, marginTop: 4 }}>Fuente: {amlResult.fuente}</div>
            </div>
          )}
        </div>
      </div>
    </FloatPanel>
  );
}

// ── Fiscal Panel ──────────────────────────────────────────
export function FiscalPanel() {
  const { state, actions } = useStore();
  const { speak } = useTTS(state.ttsEnabled);
  const m = state.metricas;
  const port = state.portafolio;

  return (
    <FloatPanel panelKey="fiscal" title="Pre-cierre Fiscal / Reporte" icon="fa-file-invoice-dollar" color={C.a} initialPos={{ top: 85, left: 280 }}>
      <div style={{ minWidth: 360 }}>
        <div style={{ fontSize: 10, color: C.text2, marginBottom: 12, lineHeight: 1.6 }}>
          Resumen fiscal del periodo · Ganancias de capital, dividendos e impuestos estimados.
        </div>
        {[
          ["Valor total portafolio", `$${(port.total_valor_usd || 0).toLocaleString("en-US", { maximumFractionDigits: 2 })}`],
          ["Ganancia / Pérdida total", `$${(port.ganancia_perdida_total || 0).toFixed(2)}`],
          ["Impuesto estimado (20%)", `$${(Math.max(port.ganancia_perdida_total || 0, 0) * 0.20).toFixed(2)}`],
          ["Dividendos recibidos", `$${(m.dividendos_total || 0).toFixed(4)}`],
          ["Saldo disponible", `$${(m.saldo_disponible || 0).toFixed(2)}`],
          ["Órdenes ejecutadas", String(m.ordenes_total || 0)],
        ].map(([l, v]) => (
          <div key={l} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0",
            borderBottom: `1px solid ${C.bg4}`, fontSize: 11 }}>
            <span style={{ color: C.text2 }}>{l}</span>
            <span style={{ color: C.text, fontWeight: 600 }}>{v}</span>
          </div>
        ))}

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button onClick={() => { api.exportarExcel(); speak("Generando reporte Excel con portafolio, órdenes y resumen fiscal."); }}
            style={{ ...btnStyle, background: C.b, flex: 1 }}>
            <i className="fas fa-file-excel" style={{ marginRight: 5 }} />Excel
          </button>
          <button onClick={() => { api.exportarPDF(); speak("Generando reporte ejecutivo PDF."); }}
            style={{ ...btnStyle, background: C.r, flex: 1 }}>
            <i className="fas fa-file-pdf" style={{ marginRight: 5 }} />PDF
          </button>
        </div>
      </div>
    </FloatPanel>
  );
}

// ── Audit Panel ───────────────────────────────────────────
export function AuditPanel() {
  const { state, actions } = useStore();
  const [logs, setLogs] = useState([]);

  const cargar = async () => {
    try { const d = await api.getAuditoria(); setLogs(d); } catch {}
  };

  return (
    <FloatPanel panelKey="audit" title="Log de Auditoría + Alertas" icon="fa-list-check" color={C.t} initialPos={{ top: 85, left: 300 }}>
      <div style={{ minWidth: 400 }}>
        <button onClick={cargar} style={{ ...btnStyle, background: C.t, marginBottom: 12, width: "100%" }}>
          <i className="fas fa-sync-alt" style={{ marginRight: 5 }} />Cargar log completo
        </button>

        {/* Alertas */}
        <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 8 }}>Alertas activas</div>
        {state.alertas.slice(0, 6).map(a => {
          const col = a.tipo === "danger" ? C.r : a.tipo === "warning" ? C.a : C.b;
          const ico = a.tipo === "danger" ? "fa-times-circle" : a.tipo === "warning" ? "fa-exclamation-triangle" : "fa-info-circle";
          return (
            <div key={a.id} onClick={() => actions.leerAlerta(a.id)}
              style={{ display: "flex", gap: 8, padding: 7, borderRadius: 6, marginBottom: 5,
                cursor: "pointer", borderLeft: `3px solid ${col}`, background: `${col}11`,
                opacity: a.leida ? 0.35 : 1 }}>
              <i className={`fas ${ico}`} style={{ color: col, fontSize: 12, marginTop: 1 }} />
              <div>
                <div style={{ fontSize: 10, color: C.text, fontWeight: 600 }}>{a.titulo}</div>
                <div style={{ fontSize: 9, color: C.text2, lineHeight: 1.4 }}>{a.mensaje}</div>
                <div style={{ fontSize: 8, color: C.text3, marginTop: 2 }}>{a.modulo} · {a.fecha?.slice(0, 16)}</div>
              </div>
            </div>
          );
        })}

        {/* Audit log */}
        {logs.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 8 }}>Log de acciones</div>
            {logs.slice(0, 8).map(l => (
              <div key={l.id} style={{ display: "flex", gap: 8, padding: "5px 0",
                borderBottom: `1px solid ${C.bg4}`, fontSize: 9, color: C.text2 }}>
                <i className="fas fa-shield-alt" style={{ color: C.t, fontSize: 10, marginTop: 1 }} />
                <div>
                  <span style={{ color: C.text, fontWeight: 600 }}>{l.accion}</span>
                  {" · "}{l.modulo}{" · "}{l.fecha?.slice(0, 16)}
                  {l.detalle && <div style={{ color: C.text3, marginTop: 1 }}>{l.detalle?.slice(0, 80)}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </FloatPanel>
  );
}

// Shared styles
const inpStyle = { width: "100%", background: "#1E2835", border: "1px solid #2a3545",
  color: "#dde4f0", padding: "6px 9px", borderRadius: 6, fontSize: 11, outline: "none" };
const selStyle = { ...inpStyle };
const lblStyle = { fontSize: 9, color: "#576880", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 3 };
const btnStyle = { border: "none", padding: "8px 12px", borderRadius: 6, cursor: "pointer",
  fontSize: 11, fontWeight: 700, color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center" };
