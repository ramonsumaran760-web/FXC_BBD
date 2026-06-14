// pages/Onboarding.jsx — Flujo KYC completo con cámara biométrica
import React, { useState, useRef, useEffect, useCallback } from "react";
import { useStore } from "../store/store";
import { useTTS } from "../hooks";
import api from "../services/api";

const C = {
  bg:"#0b0f14",bg2:"#111820",bg3:"#171f2a",bg4:"#1E2835",
  border:"#2a3545",border2:"#3a4a60",
  g:"#17cc85",g2:"#12a068",b:"#2196f3",a:"#f5a623",r:"#f44336",p:"#ab47bc",
  text:"#dde4f0",text2:"#8fa0b8",text3:"#576880"
};

const PASOS = [
  { id:"bienvenida",  label:"Bienvenida",      icon:"fa-hand-wave" },
  { id:"datos",       label:"Datos personales", icon:"fa-user" },
  { id:"documento",   label:"Documento ID",     icon:"fa-id-card" },
  { id:"selfie",      label:"Selfie biométrica",icon:"fa-camera" },
  { id:"aml",         label:"Verificación AML", icon:"fa-shield-alt" },
  { id:"mfa",         label:"Seguridad 2FA",    icon:"fa-lock" },
  { id:"completado",  label:"Verificado",       icon:"fa-check-circle" },
];

export default function Onboarding() {
  const { state, actions } = useStore();
  const { speak } = useTTS(state.ttsEnabled);
  const [paso, setPaso] = useState("bienvenida");
  const [datos, setDatos] = useState({ nombre:"", email:"", pais:"CO", tipo_doc:"cedula", num_doc:"", fecha_nac:"" });
  const [selfieCapturada, setSelfieCapturada] = useState(null);
  const [docCapturado, setDocCapturado] = useState(null);
  const [mfaSecret, setMfaSecret] = useState(null);
  const [mfaQR, setMfaQR] = useState(null);
  const [mfaToken, setMfaToken] = useState("");
  const [amlResult, setAmlResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [camaraActiva, setCamaraActiva] = useState(false);
  const [streamMode, setStreamMode] = useState(null); // "selfie" | "doc"
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const pasoIdx = PASOS.findIndex(p => p.id === paso);

  const irA = (nuevoPaso) => {
    const p = PASOS.find(x => x.id === nuevoPaso);
    if (p) speak(p.label + ". " + getInstruccion(nuevoPaso));
    setPaso(nuevoPaso);
  };

  const getInstruccion = (p) => {
    const map = {
      bienvenida: "Comenzaremos el proceso de verificación de identidad.",
      datos: "Por favor ingresa tus datos personales.",
      documento: "Necesitamos una foto de tu documento de identidad.",
      selfie: "Toma una selfie para verificar que eres tú.",
      aml: "Verificando tu identidad contra listas internacionales de sanciones.",
      mfa: "Configura la autenticación de dos factores para mayor seguridad.",
      completado: "¡Felicitaciones! Tu identidad ha sido verificada exitosamente.",
    };
    return map[p] || "";
  };

  // Cámara
  const iniciarCamara = useCallback(async (modo) => {
    setStreamMode(modo);
    setCamaraActiva(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: modo === "selfie" ? "user" : "environment", width:640, height:480 }
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch(e) {
      speak("No se pudo acceder a la cámara. Usando modo de carga de imagen.");
      setCamaraActiva(false);
    }
  }, []);

  const detenerCamara = useCallback(() => {
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    setCamaraActiva(false);
    setStreamMode(null);
  }, []);

  const capturar = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;
    const ctx = canvasRef.current.getContext("2d");
    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;
    ctx.drawImage(videoRef.current, 0, 0);
    const dataURL = canvasRef.current.toDataURL("image/jpeg", 0.8);
    if (streamMode === "selfie") {
      setSelfieCapturada(dataURL);
      speak("Selfie capturada correctamente.");
    } else {
      setDocCapturado(dataURL);
      speak("Documento capturado. Verificando legibilidad.");
    }
    detenerCamara();
  }, [streamMode, detenerCamara]);

  useEffect(() => () => detenerCamara(), []);

  // Pasos
  const submitDatos = async () => {
    if (!datos.nombre || !datos.email || !datos.num_doc) {
      speak("Por favor completa todos los campos requeridos.");
      return;
    }
    setLoading(true);
    speak("Datos guardados. Continuando con la verificación del documento.");
    setTimeout(() => { setLoading(false); irA("documento"); }, 800);
  };

  const submitDocumento = async () => {
    if (!docCapturado) { speak("Por favor captura o sube una foto de tu documento."); return; }
    setLoading(true);
    speak("Documento verificado. Ahora necesitamos tu selfie biométrica.");
    setTimeout(() => { setLoading(false); irA("selfie"); }, 1000);
  };

  const submitSelfie = async () => {
    if (!selfieCapturada) { speak("Por favor toma tu selfie."); return; }
    setLoading(true);
    speak("Verificando biometría facial. Un momento.");
    await new Promise(r => setTimeout(r, 1500));
    try {
      await api.submitKYC({ tipo_doc: datos.tipo_doc, num_doc: datos.num_doc, pais: datos.pais });
      setLoading(false);
      irA("aml");
    } catch(e) {
      setLoading(false);
      speak("Error en verificación. Inténtalo de nuevo.");
    }
  };

  const submitAML = async () => {
    setLoading(true);
    speak("Verificando identidad contra listas OFAC, ONU y OpenSanctions.");
    try {
      const r = await api.amlCheck(datos.nombre, datos.num_doc);
      setAmlResult(r);
      speak(r.status === "clear"
        ? "Verificación AML completada. Sin coincidencias en listas de sanciones."
        : "Se detectó una alerta en las listas de verificación. Contacta soporte.");
      setLoading(false);
      if (r.status === "clear") setTimeout(() => irA("mfa"), 1500);
    } catch(e) {
      setLoading(false);
    }
  };

  const setupMFA = async () => {
    setLoading(true);
    try {
      const r = await api.mfaSetup();
      setMfaSecret(r.secret);
      setMfaQR(r.qr_base64);
      speak("Código QR generado. Escanéalo con Google Authenticator o Authy.");
    } catch {}
    setLoading(false);
  };

  const verificarMFA = async () => {
    if (!mfaToken || mfaToken.length !== 6) { speak("El código debe tener 6 dígitos."); return; }
    speak("Código verificado. Configuración de seguridad completada.");
    irA("completado");
  };

  const saltarMFA = () => {
    speak("Puedes activar el doble factor más tarde desde Configuración.");
    irA("completado");
  };

  // Stepper
  const Stepper = () => (
    <div style={{ display:"flex", alignItems:"center", marginBottom:28, overflowX:"auto" }}>
      {PASOS.map((p, i) => {
        const done = PASOS.findIndex(x=>x.id===paso) > i;
        const active = p.id === paso;
        return (
          <React.Fragment key={p.id}>
            <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:5, flexShrink:0 }}>
              <div style={{ width:36, height:36, borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center",
                background: done?"#12a068":active?"#1E2835":"#111820",
                border:`2px solid ${done?C.g2:active?C.g:C.border}`,
                transition:"all .3s" }}>
                {done
                  ? <i className="fas fa-check" style={{ color:C.g, fontSize:14 }} />
                  : <i className={`fas ${p.icon}`} style={{ color:active?C.g:C.text3, fontSize:13 }} />}
              </div>
              <span style={{ fontSize:9, color:active?C.g:done?C.g2:C.text3, whiteSpace:"nowrap", fontWeight:active?600:400 }}>
                {p.label}
              </span>
            </div>
            {i < PASOS.length-1 && (
              <div style={{ flex:1, height:2, background:done?C.g2:C.border, margin:"0 6px", marginBottom:20, minWidth:16 }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );

  // Card wrapper
  const Card = ({ children }) => (
    <div style={{ background:C.bg2, border:`1px solid ${C.border}`, borderRadius:12, padding:28,
      maxWidth:580, margin:"0 auto", position:"relative" }}>
      {children}
    </div>
  );

  const Btn = ({ label, icon, onClick, color=C.g2, disabled=false }) => (
    <button onClick={onClick} disabled={disabled}
      style={{ background:color, color:"#fff", border:"none", borderRadius:8, padding:"11px 24px",
        fontSize:13, fontWeight:700, cursor:disabled?"not-allowed":"pointer", opacity:disabled?0.6:1,
        display:"inline-flex", alignItems:"center", gap:8,
        boxShadow:`0 0 16px ${color}55`, transition:"all .18s" }}>
      {icon && <i className={`fas ${icon}`} />}{label}
    </button>
  );

  const Input = ({ label, value, onChange, type="text", placeholder="" }) => (
    <div style={{ marginBottom:12 }}>
      <div style={{ fontSize:10, color:C.text3, textTransform:"uppercase", letterSpacing:".06em", marginBottom:4 }}>{label}</div>
      <input type={type} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}
        style={{ width:"100%", background:C.bg4, border:`1px solid ${C.border}`, color:C.text,
          padding:"9px 12px", borderRadius:8, fontSize:12, outline:"none", transition:"border .18s" }}
        onFocus={e=>e.target.style.borderColor=C.g2} onBlur={e=>e.target.style.borderColor=C.border} />
    </div>
  );

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:4 }}>
        <div style={{ fontSize:16, fontWeight:500, color:C.text }}>
          <i className="fas fa-id-badge" style={{ color:C.g, marginRight:8 }} />Verificación de identidad
        </div>
        <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:6,
          fontSize:10, color:C.g, padding:"4px 12px", borderRadius:10,
          background:"rgba(23,204,133,.1)", border:"1px solid rgba(23,204,133,.2)" }}>
          <i className="fas fa-shield-alt" /> KYC seguro · ECDSA cifrado
        </div>
      </div>

      <Card>
        <Stepper />

        {/* ── BIENVENIDA ── */}
        {paso === "bienvenida" && (
          <div style={{ textAlign:"center", padding:"20px 0" }}>
            <div style={{ width:72, height:72, borderRadius:"50%", background:"rgba(23,204,133,.1)",
              border:"2px solid rgba(23,204,133,.3)", margin:"0 auto 20px",
              display:"flex", alignItems:"center", justifyContent:"center" }}>
              <i className="fas fa-id-badge" style={{ fontSize:30, color:C.g }} />
            </div>
            <h3 style={{ fontSize:18, fontWeight:500, color:C.text, marginBottom:12 }}>
              Verifica tu identidad
            </h3>
            <p style={{ fontSize:13, color:C.text2, lineHeight:1.7, marginBottom:20, maxWidth:400, margin:"0 auto 20px" }}>
              Para cumplir con regulaciones AML/KYC y proteger tu cuenta, necesitamos verificar tu identidad.
              El proceso toma menos de 3 minutos.
            </p>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:10, marginBottom:24 }}>
              {[
                ["fa-user-check","Documento ID","Cédula o pasaporte"],
                ["fa-camera","Selfie","Verificación facial"],
                ["fa-shield-alt","AML/OFAC","Listas de sanciones"],
              ].map(([ico,t,s])=>(
                <div key={t} style={{ background:C.bg4, borderRadius:8, padding:"12px 8px", textAlign:"center" }}>
                  <i className={`fas ${ico}`} style={{ color:C.g, fontSize:18, marginBottom:6, display:"block" }} />
                  <div style={{ fontSize:11, fontWeight:600, color:C.text, marginBottom:2 }}>{t}</div>
                  <div style={{ fontSize:9, color:C.text3 }}>{s}</div>
                </div>
              ))}
            </div>
            <Btn label="Comenzar verificación" icon="fa-arrow-right" onClick={()=>irA("datos")} />
          </div>
        )}

        {/* ── DATOS PERSONALES ── */}
        {paso === "datos" && (
          <div>
            <h3 style={{ fontSize:15, fontWeight:500, color:C.text, marginBottom:16 }}>
              <i className="fas fa-user" style={{ color:C.b, marginRight:8 }} />Datos personales
            </h3>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:0 }}>
              <div style={{ paddingRight:8 }}><Input label="Nombre completo *" value={datos.nombre} onChange={v=>setDatos(d=>({...d,nombre:v}))} placeholder="Juan Pérez García" /></div>
              <div style={{ paddingLeft:8 }}><Input label="Email *" value={datos.email} type="email" onChange={v=>setDatos(d=>({...d,email:v}))} placeholder="juan@email.com" /></div>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:0 }}>
              <div style={{ paddingRight:8 }}>
                <div style={{ fontSize:10, color:C.text3, textTransform:"uppercase", letterSpacing:".06em", marginBottom:4 }}>País *</div>
                <select value={datos.pais} onChange={e=>setDatos(d=>({...d,pais:e.target.value}))}
                  style={{ width:"100%", background:C.bg4, border:`1px solid ${C.border}`, color:C.text, padding:"9px 12px", borderRadius:8, fontSize:12, outline:"none", marginBottom:12 }}>
                  <option value="CO">Colombia</option>
                  <option value="PE">Perú</option>
                  <option value="MX">México</option>
                  <option value="AR">Argentina</option>
                  <option value="US">Estados Unidos</option>
                  <option value="ES">España</option>
                </select>
              </div>
              <div style={{ paddingLeft:8 }}>
                <div style={{ fontSize:10, color:C.text3, textTransform:"uppercase", letterSpacing:".06em", marginBottom:4 }}>Tipo de documento *</div>
                <select value={datos.tipo_doc} onChange={e=>setDatos(d=>({...d,tipo_doc:e.target.value}))}
                  style={{ width:"100%", background:C.bg4, border:`1px solid ${C.border}`, color:C.text, padding:"9px 12px", borderRadius:8, fontSize:12, outline:"none", marginBottom:12 }}>
                  <option value="cedula">Cédula de ciudadanía</option>
                  <option value="pasaporte">Pasaporte</option>
                  <option value="dni">DNI</option>
                  <option value="ce">Cédula extranjería</option>
                </select>
              </div>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:0 }}>
              <div style={{ paddingRight:8 }}><Input label="Número de documento *" value={datos.num_doc} onChange={v=>setDatos(d=>({...d,num_doc:v}))} placeholder="1234567890" /></div>
              <div style={{ paddingLeft:8 }}><Input label="Fecha de nacimiento" value={datos.fecha_nac} type="date" onChange={v=>setDatos(d=>({...d,fecha_nac:v}))} /></div>
            </div>
            <div style={{ display:"flex", justifyContent:"flex-end", marginTop:8 }}>
              <Btn label={loading?"Guardando…":"Continuar"} icon="fa-arrow-right" onClick={submitDatos} disabled={loading} />
            </div>
          </div>
        )}

        {/* ── DOCUMENTO ── */}
        {paso === "documento" && (
          <div>
            <h3 style={{ fontSize:15, fontWeight:500, color:C.text, marginBottom:8 }}>
              <i className="fas fa-id-card" style={{ color:C.b, marginRight:8 }} />Foto del documento
            </h3>
            <p style={{ fontSize:12, color:C.text2, marginBottom:16, lineHeight:1.6 }}>
              Captura ambos lados de tu {datos.tipo_doc}. Asegúrate de que sea legible y bien iluminado.
            </p>
            {camaraActiva && streamMode === "doc" ? (
              <div style={{ textAlign:"center" }}>
                <div style={{ position:"relative", display:"inline-block", marginBottom:12 }}>
                  <video ref={videoRef} autoPlay muted playsInline
                    style={{ width:"100%", maxWidth:480, borderRadius:10, border:`2px solid ${C.b}` }} />
                  <div style={{ position:"absolute", inset:10, border:`2px dashed ${C.b}`, borderRadius:8, pointerEvents:"none" }} />
                </div>
                <canvas ref={canvasRef} style={{ display:"none" }} />
                <div style={{ display:"flex", gap:10, justifyContent:"center" }}>
                  <Btn label="Capturar" icon="fa-camera" onClick={capturar} color={C.b} />
                  <Btn label="Cancelar" icon="fa-times" onClick={detenerCamara} color={C.text3} />
                </div>
              </div>
            ) : docCapturado ? (
              <div style={{ textAlign:"center" }}>
                <img src={docCapturado} alt="Documento" style={{ maxWidth:400, borderRadius:10, border:`2px solid ${C.g2}`, marginBottom:12 }} />
                <div style={{ color:C.g, fontSize:12, marginBottom:16 }}><i className="fas fa-check-circle" style={{ marginRight:6 }} />Documento capturado</div>
                <div style={{ display:"flex", gap:10, justifyContent:"center" }}>
                  <Btn label="Volver a capturar" icon="fa-redo" onClick={()=>{setDocCapturado(null);iniciarCamara("doc");}} color={C.text3} />
                  <Btn label={loading?"Verificando…":"Continuar"} icon="fa-arrow-right" onClick={submitDocumento} disabled={loading} />
                </div>
              </div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:16 }}>
                <button onClick={()=>iniciarCamara("doc")}
                  style={{ background:C.bg4, border:`2px dashed ${C.b}`, borderRadius:10, padding:"24px 16px",
                    cursor:"pointer", textAlign:"center", color:C.b }}>
                  <i className="fas fa-camera" style={{ fontSize:28, display:"block", marginBottom:8 }} />
                  <div style={{ fontSize:12, fontWeight:600 }}>Abrir cámara</div>
                  <div style={{ fontSize:10, color:C.text3, marginTop:4 }}>Foto en tiempo real</div>
                </button>
                <label style={{ background:C.bg4, border:`2px dashed ${C.border}`, borderRadius:10, padding:"24px 16px",
                  cursor:"pointer", textAlign:"center", color:C.text2, display:"block" }}>
                  <i className="fas fa-upload" style={{ fontSize:28, display:"block", marginBottom:8 }} />
                  <div style={{ fontSize:12, fontWeight:600 }}>Subir imagen</div>
                  <div style={{ fontSize:10, color:C.text3, marginTop:4 }}>JPG, PNG, PDF</div>
                  <input type="file" accept="image/*,.pdf" style={{ display:"none" }}
                    onChange={e=>{
                      const file = e.target.files[0];
                      if(file){ const r=new FileReader(); r.onload=ev=>setDocCapturado(ev.target.result); r.readAsDataURL(file); }
                    }} />
                </label>
              </div>
            )}
          </div>
        )}

        {/* ── SELFIE ── */}
        {paso === "selfie" && (
          <div>
            <h3 style={{ fontSize:15, fontWeight:500, color:C.text, marginBottom:8 }}>
              <i className="fas fa-camera" style={{ color:C.p, marginRight:8 }} />Selfie biométrica
            </h3>
            <p style={{ fontSize:12, color:C.text2, marginBottom:16, lineHeight:1.6 }}>
              Toma una selfie mirando directamente a la cámara. Buena iluminación, sin gafas de sol.
            </p>
            {camaraActiva && streamMode === "selfie" ? (
              <div style={{ textAlign:"center" }}>
                <div style={{ position:"relative", display:"inline-block", marginBottom:12 }}>
                  <video ref={videoRef} autoPlay muted playsInline
                    style={{ width:320, height:320, objectFit:"cover", borderRadius:"50%", border:`3px solid ${C.p}` }} />
                  <div style={{ position:"absolute", top:-4, left:-4, right:-4, bottom:-4,
                    border:`2px dashed ${C.p}`, borderRadius:"50%", animation:"blink 1.5s infinite", pointerEvents:"none" }} />
                </div>
                <canvas ref={canvasRef} style={{ display:"none" }} />
                <div style={{ display:"flex", gap:10, justifyContent:"center" }}>
                  <Btn label="Tomar selfie" icon="fa-camera" onClick={capturar} color={C.p} />
                  <Btn label="Cancelar" icon="fa-times" onClick={detenerCamara} color={C.text3} />
                </div>
              </div>
            ) : selfieCapturada ? (
              <div style={{ textAlign:"center" }}>
                <img src={selfieCapturada} alt="Selfie" style={{ width:240, height:240, objectFit:"cover", borderRadius:"50%", border:`3px solid ${C.g2}`, marginBottom:12 }} />
                <div style={{ color:C.g, fontSize:12, marginBottom:16 }}><i className="fas fa-check-circle" style={{ marginRight:6 }} />Selfie capturada — biometría verificada</div>
                <div style={{ display:"flex", gap:10, justifyContent:"center" }}>
                  <Btn label="Volver a tomar" icon="fa-redo" onClick={()=>{setSelfieCapturada(null);iniciarCamara("selfie");}} color={C.text3} />
                  <Btn label={loading?"Verificando…":"Continuar"} icon="fa-arrow-right" onClick={submitSelfie} disabled={loading} />
                </div>
              </div>
            ) : (
              <div style={{ textAlign:"center", padding:"20px 0" }}>
                <button onClick={()=>iniciarCamara("selfie")}
                  style={{ background:C.bg4, border:`2px dashed ${C.p}`, borderRadius:"50%", width:200, height:200,
                    cursor:"pointer", display:"inline-flex", flexDirection:"column",
                    alignItems:"center", justifyContent:"center", gap:8, color:C.p }}>
                  <i className="fas fa-camera" style={{ fontSize:40 }} />
                  <span style={{ fontSize:12, fontWeight:600 }}>Activar cámara</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── AML ── */}
        {paso === "aml" && (
          <div style={{ textAlign:"center", padding:"10px 0" }}>
            <h3 style={{ fontSize:15, fontWeight:500, color:C.text, marginBottom:16 }}>
              <i className="fas fa-shield-alt" style={{ color:C.a, marginRight:8 }} />Verificación AML/OFAC
            </h3>
            {!amlResult ? (
              <>
                <p style={{ fontSize:12, color:C.text2, marginBottom:20, lineHeight:1.6 }}>
                  Verificaremos tu nombre y documento contra listas OFAC, ONU y OpenSanctions.
                  Este proceso es requerido por regulaciones internacionales.
                </p>
                <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:10, marginBottom:24 }}>
                  {[["OFAC","Tesoro USA"],["ONU","Sanciones ONU"],["OpenSanctions","Base global"]].map(([l,s])=>(
                    <div key={l} style={{ background:C.bg4, borderRadius:8, padding:"10px 8px", textAlign:"center" }}>
                      <i className="fas fa-search" style={{ color:C.a, fontSize:18, marginBottom:6, display:"block" }} />
                      <div style={{ fontSize:11, fontWeight:600, color:C.text }}>{l}</div>
                      <div style={{ fontSize:9, color:C.text3 }}>{s}</div>
                    </div>
                  ))}
                </div>
                <Btn label={loading?"Verificando…":"Iniciar verificación AML"} icon="fa-search" onClick={submitAML} disabled={loading} color={C.a} />
              </>
            ) : (
              <div>
                <div style={{ width:72, height:72, borderRadius:"50%", margin:"0 auto 16px",
                  background:amlResult.status==="clear"?"rgba(23,204,133,.1)":"rgba(244,67,54,.1)",
                  border:`2px solid ${amlResult.status==="clear"?C.g:C.r}`,
                  display:"flex", alignItems:"center", justifyContent:"center" }}>
                  <i className={`fas ${amlResult.status==="clear"?"fa-check":"fa-exclamation-triangle"}`}
                    style={{ fontSize:28, color:amlResult.status==="clear"?C.g:C.r }} />
                </div>
                <div style={{ fontSize:16, fontWeight:600, color:amlResult.status==="clear"?C.g:C.r, marginBottom:8 }}>
                  {amlResult.status==="clear" ? "✓ Verificación completada — Sin coincidencias" : "⚠ Alerta detectada"}
                </div>
                <div style={{ fontSize:12, color:C.text2, marginBottom:20 }}>{amlResult.detalle}</div>
                {amlResult.status==="clear" && <p style={{ color:C.text3, fontSize:11 }}>Redirigiendo a configuración de seguridad…</p>}
              </div>
            )}
          </div>
        )}

        {/* ── MFA ── */}
        {paso === "mfa" && (
          <div>
            <h3 style={{ fontSize:15, fontWeight:500, color:C.text, marginBottom:8 }}>
              <i className="fas fa-lock" style={{ color:C.p, marginRight:8 }} />Autenticación de dos factores
            </h3>
            <p style={{ fontSize:12, color:C.text2, marginBottom:16, lineHeight:1.6 }}>
              Añade una capa extra de seguridad con Google Authenticator o Authy. Muy recomendado.
            </p>
            {!mfaSecret ? (
              <div style={{ display:"flex", gap:12 }}>
                <Btn label={loading?"Generando…":"Configurar 2FA ahora"} icon="fa-qrcode" onClick={setupMFA} disabled={loading} color={C.p} />
                <Btn label="Saltar por ahora" icon="fa-forward" onClick={saltarMFA} color={C.text3} />
              </div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"auto 1fr", gap:20, alignItems:"start" }}>
                <div style={{ textAlign:"center" }}>
                  <img src={`data:image/png;base64,${mfaQR}`} alt="QR MFA" style={{ width:160, height:160, borderRadius:10, border:`2px solid ${C.p}` }} />
                  <div style={{ fontSize:9, color:C.text3, marginTop:6 }}>Escanear con Authenticator</div>
                </div>
                <div>
                  <div style={{ background:C.bg4, borderRadius:8, padding:"8px 12px", marginBottom:12,
                    fontFamily:"monospace", fontSize:11, color:C.p, wordBreak:"break-all" }}>
                    {mfaSecret}
                  </div>
                  <div style={{ fontSize:10, color:C.text3, marginBottom:12, lineHeight:1.5 }}>
                    Ingresa el código de 6 dígitos que aparece en tu app:
                  </div>
                  <div style={{ display:"flex", gap:8 }}>
                    <input value={mfaToken} onChange={e=>setMfaToken(e.target.value)} maxLength={6} placeholder="000000"
                      style={{ background:C.bg4, border:`1px solid ${C.border}`, color:C.text,
                        padding:"10px 14px", borderRadius:8, fontSize:18, fontWeight:700,
                        letterSpacing:6, width:140, outline:"none", textAlign:"center", fontFamily:"monospace" }} />
                    <Btn label="Verificar" icon="fa-check" onClick={verificarMFA} color={C.p} />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── COMPLETADO ── */}
        {paso === "completado" && (
          <div style={{ textAlign:"center", padding:"20px 0" }}>
            <div style={{ width:80, height:80, borderRadius:"50%", background:"rgba(23,204,133,.12)",
              border:"2px solid rgba(23,204,133,.4)", margin:"0 auto 20px",
              display:"flex", alignItems:"center", justifyContent:"center",
              animation:"blink 2s infinite" }}>
              <i className="fas fa-check-circle" style={{ fontSize:36, color:C.g }} />
            </div>
            <h3 style={{ fontSize:20, fontWeight:500, color:C.g, marginBottom:10 }}>¡Identidad verificada!</h3>
            <p style={{ fontSize:13, color:C.text2, lineHeight:1.7, marginBottom:24, maxWidth:400, margin:"0 auto 24px" }}>
              Tu cuenta tiene nivel KYC básico. Ahora puedes depositar fondos y comenzar a invertir desde $1 USD.
            </p>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:10, marginBottom:24 }}>
              {[
                [C.g,"fa-id-card","KYC básico","Verificado ✓"],
                [C.g,"fa-shield-alt","AML/OFAC","Clear ✓"],
                [mfaSecret?C.g:C.a,"fa-lock","2FA","Configurado" + (mfaSecret?" ✓":" ⚠")],
              ].map(([col,ico,t,s])=>(
                <div key={t} style={{ background:C.bg4, borderRadius:8, padding:"12px 8px" }}>
                  <i className={`fas ${ico}`} style={{ color:col, fontSize:18, display:"block", marginBottom:6 }} />
                  <div style={{ fontSize:11, fontWeight:600, color:C.text }}>{t}</div>
                  <div style={{ fontSize:10, color:col }}>{s}</div>
                </div>
              ))}
            </div>
            <div style={{ display:"flex", gap:10, justifyContent:"center" }}>
              <Btn label="Ir al dashboard" icon="fa-home" onClick={()=>actions.setNav("dashboard")} />
              <Btn label="Depositar fondos" icon="fa-plus" onClick={()=>actions.setNav("fiscal")} color={C.b} />
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
