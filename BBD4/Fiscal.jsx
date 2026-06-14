// pages/Fiscal.jsx — Reportes fiscales + pagos + estado compliance
import React, { useState, useEffect } from "react";
import { useStore } from "../store/store";
import api from "../services/api";
import StripeCheckout from "../components/forms/StripeCheckout";

const C = { bg:"#0b0f14",bg2:"#111820",bg3:"#171f2a",bg4:"#1E2835",
  border:"#2a3545",g:"#17cc85",g2:"#12a068",b:"#2196f3",a:"#f5a623",r:"#f44336",p:"#ab47bc",t:"#26c6da",
  text:"#dde4f0",text2:"#8fa0b8",text3:"#576880" };
const fmtUSD = n=>`$${parseFloat(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;

function StatusRow({ label, value, status }) {
  const col = status==="ok"?C.g:status==="warn"?C.a:status==="error"?C.r:C.text3;
  const ico = status==="ok"?"fa-check-circle":status==="warn"?"fa-exclamation-triangle":status==="error"?"fa-times-circle":"fa-circle";
  return (
    <div style={{display:"flex",alignItems:"center",gap:10,padding:"8px 0",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
      <i className={`fas ${ico}`} style={{color:col,fontSize:13,width:16}} />
      <span style={{flex:1,fontSize:11,color:C.text2}}>{label}</span>
      <span style={{fontSize:11,color:col,fontWeight:600}}>{value}</span>
    </div>
  );
}

export default function Fiscal() {
  const { state, actions } = useStore();
  const { metricas, portafolio } = state;
  const [tab, setTab] = useState("resumen");
  const [historialPagos, setHistorialPagos] = useState([]);
  const [configPagos, setConfigPagos] = useState({});
  const [depositoMonto, setDepositoMonto] = useState(100);
  const [depositoMetodo, setDepositoMetodo] = useState("stripe");
  const [loadingDeposito, setLoadingDeposito] = useState(false);
  const [showStripe, setShowStripe] = useState(false);
  const [stripePK, setStripePK] = useState("");
  const [mpURL, setMpURL] = useState(null);
  const [cryptoAddr, setCryptoAddr] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);

  useEffect(()=>{
    // Cargar Stripe publishable key desde backend
    fetch("/api/v1/pagos/config").then(r=>r.json()).then(d=>{
      if(d.stripe_publishable_key) setStripePK(d.stripe_publishable_key);
      else setStripePK(process.env.REACT_APP_STRIPE_PK || "pk_test_demo");
    }).catch(()=>setStripePK("pk_test_demo"));
  },[]);

  useEffect(()=>{
    fetch("/api/v1/pagos/historial").then(r=>r.json()).then(setHistorialPagos).catch(()=>{});
    fetch("/api/v1/pagos/config").then(r=>r.json()).then(setConfigPagos).catch(()=>{});
    api.getAuditoria().then(setAuditLogs).catch(()=>{});
  },[]);

  const totalGP = portafolio.ganancia_perdida_total || 0;
  const impuesto = Math.max(totalGP,0)*0.20;
  const totalDiv = metricas.dividendos_total || 0;
  const valorPort = portafolio.total_valor_usd || 0;

  const iniciarStripe = async () => {
    setLoadingDeposito(true);
    try {
      const r = await fetch("/api/v1/pagos/stripe/intent",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({monto_usd:depositoMonto,metodo:"stripe"})}).then(r=>r.json());
      if(r.error) throw new Error(r.error);
      actions.toast(`Stripe Payment Intent creado: ${r.payment_intent_id}`);
      actions.toast("Integra Stripe.js en el frontend para completar el pago con tarjeta");
    } catch(e){ actions.toast(e.message,"error"); }
    setLoadingDeposito(false);
  };

  const iniciarMP = async () => {
    setLoadingDeposito(true);
    try {
      const r = await fetch("/api/v1/pagos/mercadopago/preferencia",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({monto_usd:depositoMonto})}).then(r=>r.json());
      if(r.error) throw new Error(r.error);
      setMpURL(r.sandbox_init_point || r.init_point);
      actions.toast("Preferencia MercadoPago creada");
    } catch(e){ actions.toast(e.message,"error"); }
    setLoadingDeposito(false);
  };

  const getCrypto = async () => {
    const r = await fetch("/api/v1/pagos/crypto/direccion").then(r=>r.json());
    setCryptoAddr(r);
  };

  const depositar = async () => {
    if(depositoMetodo==="stripe") { setShowStripe(true); return; }
    else if(depositoMetodo==="mercadopago") await iniciarMP();
    else if(depositoMetodo==="crypto") await getCrypto();
    else { const r = await actions.depositar(depositoMonto); }
  };

  return (
    <div style={{display:"flex",flexDirection:"column",gap:12}}>

      {/* KPIs fiscales */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
        {[
          {label:"Valor portafolio",value:fmtUSD(valorPort),color:C.g,icon:"fa-briefcase"},
          {label:"G/P capital",value:fmtUSD(totalGP),color:totalGP>=0?C.g:C.r,icon:"fa-chart-line"},
          {label:"Impuesto estimado 20%",value:fmtUSD(impuesto),color:C.a,icon:"fa-receipt"},
          {label:"Dividendos recibidos",value:fmtUSD(totalDiv),color:C.p,icon:"fa-coins"},
        ].map(m=>(
          <div key={m.label} style={{background:C.bg2,border:`1px solid ${C.border}`,borderTop:`2.5px solid ${m.color}`,borderRadius:10,padding:"12px 14px"}}>
            <div style={{width:30,height:30,borderRadius:7,background:`${m.color}22`,display:"flex",alignItems:"center",justifyContent:"center",marginBottom:8}}>
              <i className={`fas ${m.icon}`} style={{color:m.color,fontSize:13}} />
            </div>
            <div style={{fontSize:9,color:C.text3,textTransform:"uppercase",letterSpacing:".07em",marginBottom:3}}>{m.label}</div>
            <div style={{fontSize:18,fontWeight:700,color:m.color}}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{display:"flex",gap:4}}>
        {["resumen","pagos","compliance","auditoria"].map(t=>(
          <button key={t} onClick={()=>setTab(t)}
            style={{padding:"7px 14px",borderRadius:7,fontSize:11,cursor:"pointer",
              border:`1px solid ${tab===t?C.g2:C.border}`,
              background:tab===t?C.g2:"transparent",
              color:tab===t?C.g:C.text2,textTransform:"capitalize"}}>
            {t.charAt(0).toUpperCase()+t.slice(1)}
          </button>
        ))}
      </div>

      {/* RESUMEN FISCAL */}
      {tab==="resumen" && (
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:14}}>
              <i className="fas fa-file-invoice-dollar" style={{color:C.a,marginRight:6}} />Resumen fiscal del periodo
            </div>
            {[
              ["Valor portafolio total",fmtUSD(valorPort),"ok"],
              ["Ganancias de capital",fmtUSD(Math.max(totalGP,0)),totalGP>=0?"ok":"warn"],
              ["Pérdidas de capital",fmtUSD(Math.abs(Math.min(totalGP,0))),totalGP<0?"warn":"ok"],
              ["Dividendos recibidos",fmtUSD(totalDiv),"ok"],
              ["Impuesto estimado (20%)",fmtUSD(impuesto),impuesto>0?"warn":"ok"],
              ["Órdenes ejecutadas",String(metricas.ordenes_total||0),"ok"],
              ["Saldo disponible",fmtUSD(metricas.saldo_disponible||0),"ok"],
            ].map(([l,v,s])=><StatusRow key={l} label={l} value={v} status={s} />)}
          </div>

          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:14}}>
              <i className="fas fa-download" style={{color:C.b,marginRight:6}} />Generar reportes
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:10}}>
              {[
                {label:"Reporte Excel completo",sub:"4 hojas: portafolio, órdenes, dividendos, resumen",ico:"fa-file-excel",color:C.b,action:()=>api.exportarExcel()},
                {label:"Reporte PDF ejecutivo",sub:"KPIs, posiciones, firma digital",ico:"fa-file-pdf",color:C.r,action:()=>api.exportarPDF()},
              ].map(r=>(
                <button key={r.label} onClick={r.action}
                  style={{background:C.bg4,border:`1px solid ${C.border}`,borderRadius:9,padding:"12px 14px",cursor:"pointer",textAlign:"left",transition:"all .2s"}}>
                  <div style={{display:"flex",alignItems:"center",gap:10}}>
                    <i className={`fas ${r.ico}`} style={{color:r.color,fontSize:20}} />
                    <div>
                      <div style={{fontSize:12,color:C.text,fontWeight:600,marginBottom:2}}>{r.label}</div>
                      <div style={{fontSize:10,color:C.text3}}>{r.sub}</div>
                    </div>
                    <i className="fas fa-download" style={{marginLeft:"auto",color:C.text3,fontSize:12}} />
                  </div>
                </button>
              ))}
              <div style={{marginTop:6,padding:"10px 14px",background:C.bg3,borderRadius:8,fontSize:10,color:C.text3,lineHeight:1.6}}>
                <b style={{color:C.text2}}>Nota fiscal:</b> Los reportes incluyen ganancias/pérdidas de capital realizadas. Consulta con tu asesor tributario para la declaración oficial en tu país.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PAGOS */}
      {tab==="pagos" && (
        <div style={{display:"grid",gridTemplateColumns:"360px 1fr",gap:12}}>

          {/* Form depósito */}
          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:14}}>
              <i className="fas fa-plus-circle" style={{color:C.g,marginRight:6}} />Depositar fondos
            </div>

            <div style={{marginBottom:10}}>
              <div style={{fontSize:9,color:C.text3,textTransform:"uppercase",marginBottom:5}}>Monto USD</div>
              <input type="number" value={depositoMonto} min={1} step={10}
                onChange={e=>setDepositoMonto(parseFloat(e.target.value)||1)}
                style={{width:"100%",background:C.bg4,border:`1px solid ${C.border}`,color:C.text,padding:"9px 12px",borderRadius:8,fontSize:14,fontWeight:600,outline:"none"}} />
              <div style={{display:"flex",gap:6,marginTop:6}}>
                {[50,100,500,1000].map(v=>(
                  <button key={v} onClick={()=>setDepositoMonto(v)}
                    style={{flex:1,background:depositoMonto===v?C.g2:C.bg4,color:depositoMonto===v?"#fff":C.text2,border:`1px solid ${depositoMonto===v?C.g2:C.border}`,borderRadius:6,padding:"5px 0",fontSize:10,cursor:"pointer"}}>
                    ${v}
                  </button>
                ))}
              </div>
            </div>

            <div style={{marginBottom:14}}>
              <div style={{fontSize:9,color:C.text3,textTransform:"uppercase",marginBottom:5}}>Método de pago</div>
              {[
                {key:"stripe",label:"Tarjeta (Stripe)",sub:"Visa, Mastercard, AMEX",ico:"fa-credit-card",status:configPagos.stripe?"active":"config"},
                {key:"mercadopago",label:"MercadoPago",sub:"LATAM — Perú, Colombia, etc.",ico:"fa-wallet",status:configPagos.mercadopago?"active":"config"},
                {key:"crypto",label:"Crypto USDC/USDT",sub:"Ethereum · Polygon",ico:"fa-coins",status:configPagos.crypto?"active":"config"},
                {key:"bank",label:"Transferencia bancaria",sub:"1-3 días hábiles",ico:"fa-university",status:"active"},
              ].map(m=>(
                <div key={m.key} onClick={()=>setDepositoMetodo(m.key)}
                  style={{display:"flex",alignItems:"center",gap:10,padding:"10px 12px",
                    border:`1px solid ${depositoMetodo===m.key?C.g2:C.border}`,
                    background:depositoMetodo===m.key?"rgba(23,204,133,.08)":C.bg4,
                    borderRadius:8,cursor:"pointer",marginBottom:6,transition:"all .18s"}}>
                  <i className={`fas ${m.ico}`} style={{color:depositoMetodo===m.key?C.g:C.text3,fontSize:16,width:20}} />
                  <div style={{flex:1}}>
                    <div style={{fontSize:11,color:C.text,fontWeight:600}}>{m.label}</div>
                    <div style={{fontSize:9,color:C.text3}}>{m.sub}</div>
                  </div>
                  {m.status==="config" && <span style={{fontSize:8,padding:"2px 6px",borderRadius:4,background:"rgba(245,166,35,.2)",color:C.a}}>CONFIG</span>}
                  {depositoMetodo===m.key && <i className="fas fa-check-circle" style={{color:C.g,fontSize:13}} />}
                </div>
              ))}
            </div>

            <button onClick={depositar} disabled={loadingDeposito}
              style={{width:"100%",background:C.g2,color:"#fff",border:"none",borderRadius:9,padding:"12px",fontSize:13,fontWeight:700,cursor:"pointer",boxShadow:"0 0 15px rgba(18,160,104,.3)",opacity:loadingDeposito?0.7:1}}>
              <i className="fas fa-arrow-up" style={{marginRight:7}} />
              {loadingDeposito ? "Procesando…" : `Depositar ${fmtUSD(depositoMonto)}`}
            </button>

            {mpURL && (
              <div style={{marginTop:12,padding:12,background:"rgba(33,150,243,.1)",border:`1px solid ${C.b}`,borderRadius:8}}>
                <div style={{fontSize:11,color:C.b,marginBottom:8,fontWeight:600}}>MercadoPago listo</div>
                {showStripe && depositoMetodo==="stripe" && (
          <div style={{marginTop:14,padding:16,background:C.bg3,borderRadius:10,border:`1px solid ${C.border}`}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
              <div style={{fontSize:12,fontWeight:600,color:C.text}}>
                <i className="fas fa-credit-card" style={{color:C.b,marginRight:7}} />
                Pago con tarjeta — Stripe
              </div>
              <button onClick={()=>setShowStripe(false)}
                style={{background:"none",border:"none",color:C.text3,cursor:"pointer",fontSize:14}}>✕</button>
            </div>
            <StripeCheckout
              montoUSD={depositoMonto}
              publishableKey={stripePK}
              onSuccess={(data)=>{
                setShowStripe(false);
                actions.toast(`✓ Pago exitoso: $${data.montoAcreditado} acreditado. Saldo: $${data.saldoNuevo}`);
                actions.loadMetricas();
                fetch("/api/v1/pagos/historial").then(r=>r.json()).then(setHistorialPagos).catch(()=>{});
              }}
              onError={(msg)=>actions.toast(msg,"error")}
            />
          </div>
        )}

        <a href={mpURL} target="_blank" rel="noreferrer"
                  style={{color:C.b,fontSize:11,textDecoration:"underline"}}>
                  Ir al checkout de MercadoPago →
                </a>
              </div>
            )}

            {cryptoAddr && (
              <div style={{marginTop:12,padding:12,background:"rgba(23,204,133,.08)",border:`1px solid ${C.g2}`,borderRadius:8}}>
                <div style={{fontSize:11,color:C.g,marginBottom:6,fontWeight:600}}>Dirección USDC</div>
                <div style={{fontSize:10,color:C.text,fontFamily:"monospace",wordBreak:"break-all",marginBottom:6}}>{cryptoAddr.direccion}</div>
                <div style={{fontSize:9,color:C.text3}}>Red: {cryptoAddr.red} · Mínimo: {cryptoAddr.minimo}</div>
                <div style={{fontSize:9,color:C.text3,marginTop:2}}>{cryptoAddr.confirmaciones}</div>
              </div>
            )}
          </div>

          {/* Historial pagos */}
          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,overflow:"hidden"}}>
            <div style={{padding:"12px 14px",borderBottom:`1px solid ${C.border}`,fontSize:12,fontWeight:600,color:C.text}}>
              <i className="fas fa-history" style={{color:C.b,marginRight:6}} />Historial de pagos
            </div>
            <div style={{overflowY:"auto",maxHeight:400}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
                <thead><tr>
                  {["#","Tipo","Monto","Método","Estado","Descripción","Fecha"].map(h=>(
                    <th key={h} style={{padding:"7px 10px",background:C.bg3,color:C.text3,fontWeight:600,textAlign:"left",fontSize:9,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`,whiteSpace:"nowrap"}}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {historialPagos.map(t=>(
                    <tr key={t.id}>
                      <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3}}>#{t.id}</td>
                      <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
                        <span style={{padding:"2px 8px",borderRadius:6,fontSize:9,fontWeight:700,
                          background:t.tipo==="deposito"?"rgba(23,204,133,.15)":"rgba(244,67,54,.15)",
                          color:t.tipo==="deposito"?C.g:C.r}}>{t.tipo?.toUpperCase()}</span>
                      </td>
                      <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,fontWeight:700,color:t.tipo==="deposito"?C.g:C.r}}>{fmtUSD(t.monto_usd)}</td>
                      <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3,fontSize:10}}>{t.metodo}</td>
                      <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
                        <span style={{padding:"2px 7px",borderRadius:6,fontSize:9,fontWeight:700,
                          background:t.estado==="completed"?"rgba(23,204,133,.15)":"rgba(245,166,35,.15)",
                          color:t.estado==="completed"?C.g:C.a}}>{t.estado}</span>
                      </td>
                      <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text2,fontSize:10}}>{t.descripcion}</td>
                      <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3,fontSize:9}}>{t.fecha?.slice(0,16)}</td>
                    </tr>
                  ))}
                  {historialPagos.length===0 && <tr><td colSpan={7} style={{padding:"24px",textAlign:"center",color:C.text3,fontSize:11}}>Sin historial de pagos aún</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* COMPLIANCE */}
      {tab==="compliance" && (
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:14}}>
              <i className="fas fa-id-card" style={{color:C.b,marginRight:6}} />Estado KYC / AML
            </div>
            <StatusRow label="KYC básico (documento)" value="Verificado ✓" status="ok" />
            <StatusRow label="Verificación AML/OFAC" value="Clear ✓" status="ok" />
            <StatusRow label="OpenSanctions check" value="Sin coincidencias" status="ok" />
            <StatusRow label="Biometría (selfie+doc)" value="Pendiente" status="warn" />
            <StatusRow label="MFA / 2FA activo" value="No configurado" status="warn" />
            <StatusRow label="Firma ECDSA P-256" value="Activa en cada orden" status="ok" />
            <StatusRow label="Nivel KYC alcanzado" value="Basic" status="warn" />
            <div style={{marginTop:14}}>
              <button onClick={()=>actions.openPanel("kyc")}
                style={{width:"100%",background:C.b,color:"#fff",border:"none",borderRadius:8,padding:"10px",fontSize:11,fontWeight:700,cursor:"pointer"}}>
                <i className="fas fa-id-card" style={{marginRight:6}} />Completar verificación KYC
              </button>
            </div>
          </div>

          <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:16}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:14}}>
              <i className="fas fa-lock" style={{color:C.p,marginRight:6}} />Seguridad de la cuenta
            </div>
            <StatusRow label="Contraseña" value="Configurada ✓" status="ok" />
            <StatusRow label="JWT tokens" value="15 min expiry" status="ok" />
            <StatusRow label="MFA Google Authenticator" value="No activado" status="warn" />
            <StatusRow label="IP de acceso registrada" value="✓ Auditoría activa" status="ok" />
            <StatusRow label="Sesiones activas" value="1 dispositivo" status="ok" />
            <StatusRow label="Alertas de seguridad" value="Activadas" status="ok" />
            <div style={{marginTop:14}}>
              <button onClick={()=>actions.openPanel("kyc")}
                style={{width:"100%",background:C.p,color:"#fff",border:"none",borderRadius:8,padding:"10px",fontSize:11,fontWeight:700,cursor:"pointer"}}>
                <i className="fas fa-lock" style={{marginRight:6}} />Activar MFA 2FA
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AUDITORÍA */}
      {tab==="auditoria" && (
        <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,overflow:"hidden"}}>
          <div style={{padding:"12px 14px",borderBottom:`1px solid ${C.border}`,display:"flex",alignItems:"center",gap:8}}>
            <span style={{fontSize:12,fontWeight:600,color:C.text}}>
              <i className="fas fa-list-check" style={{color:C.t,marginRight:6}} />Log de auditoría completo
            </span>
            <button onClick={()=>api.getAuditoria().then(setAuditLogs)}
              style={{marginLeft:"auto",background:C.bg4,border:`1px solid ${C.border}`,color:C.text2,borderRadius:6,padding:"5px 10px",fontSize:10,cursor:"pointer"}}>
              <i className="fas fa-sync-alt" style={{marginRight:4}} />Recargar
            </button>
          </div>
          <div style={{overflowY:"auto",maxHeight:400}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:11}}>
              <thead><tr>
                {["#","Acción","Módulo","Detalle","IP","Fecha"].map(h=>(
                  <th key={h} style={{padding:"7px 10px",background:C.bg3,color:C.text3,fontWeight:600,textAlign:"left",fontSize:9,textTransform:"uppercase",borderBottom:`1px solid ${C.border}`}}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {auditLogs.map(l=>(
                  <tr key={l.id}>
                    <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3}}>#{l.id}</td>
                    <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,fontWeight:600,color:C.text}}>{l.accion}</td>
                    <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`}}>
                      <span style={{padding:"2px 7px",borderRadius:5,fontSize:9,background:"rgba(38,198,218,.1)",color:C.t}}>{l.modulo}</span>
                    </td>
                    <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text2,fontSize:10,maxWidth:300,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{l.detalle}</td>
                    <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3,fontSize:9,fontFamily:"monospace"}}>{l.ip}</td>
                    <td style={{padding:"7px 10px",borderBottom:`1px solid rgba(42,53,69,.3)`,color:C.text3,fontSize:9}}>{l.fecha?.slice(0,16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}
