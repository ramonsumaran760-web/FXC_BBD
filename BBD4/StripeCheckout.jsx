// components/forms/StripeCheckout.jsx
// Integración real con Stripe.js — carga el SDK desde CDN de Stripe
// No requiere npm install stripe — usa el script tag de Stripe

import React, { useState, useEffect, useRef } from "react";

const C = {
  bg4:"#1E2835", border:"#2a3545", border2:"#3a4a60",
  g:"#17cc85", g2:"#12a068", r:"#f44336", a:"#f5a623",
  text:"#dde4f0", text2:"#8fa0b8", text3:"#576880"
};

// Carga el script de Stripe una sola vez
let stripePromise = null;
function getStripe(publishableKey) {
  if (!stripePromise && window.Stripe) {
    stripePromise = Promise.resolve(window.Stripe(publishableKey));
  } else if (!stripePromise) {
    stripePromise = new Promise((resolve) => {
      const script = document.createElement("script");
      script.src = "https://js.stripe.com/v3/";
      script.async = true;
      script.onload = () => resolve(window.Stripe(publishableKey));
      script.onerror = () => resolve(null);
      document.head.appendChild(script);
    });
  }
  return stripePromise;
}

export default function StripeCheckout({ montoUSD, onSuccess, onError, publishableKey }) {
  const [stripe, setStripe] = useState(null);
  const [elements, setElements] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cardReady, setCardReady] = useState(false);
  const [cardError, setCardError] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | loading | processing | success | error
  const cardRef = useRef(null);
  const cardElementRef = useRef(null);

  const PUBLISHABLE_KEY = publishableKey
    || process.env.REACT_APP_STRIPE_PK
    || "pk_test_demo";

  // Cargar Stripe.js y montar el Card Element
  useEffect(() => {
    if (!montoUSD || montoUSD < 1) return;
    setStatus("loading");

    getStripe(PUBLISHABLE_KEY).then((stripeInstance) => {
      if (!stripeInstance) {
        setStatus("error");
        setCardError("No se pudo cargar Stripe. Verifica la publishable key.");
        return;
      }
      setStripe(stripeInstance);

      const els = stripeInstance.elements({
        appearance: {
          theme: "night",
          variables: {
            colorPrimary: "#17cc85",
            colorBackground: "#1E2835",
            colorText: "#dde4f0",
            colorDanger: "#f44336",
            fontFamily: "'Segoe UI', system-ui, sans-serif",
            borderRadius: "8px",
            fontSizeBase: "13px",
          },
        },
      });
      setElements(els);

      // Montar Card Element en el div
      setTimeout(() => {
        if (cardRef.current) {
          const card = els.create("card", {
            hidePostalCode: true,
            style: {
              base: {
                color: "#dde4f0",
                fontFamily: "'Segoe UI', sans-serif",
                fontSize: "14px",
                "::placeholder": { color: "#576880" },
              },
              invalid: { color: "#f44336" },
            },
          });
          card.mount(cardRef.current);
          card.on("ready", () => setCardReady(true));
          card.on("change", (e) => {
            setCardError(e.error ? e.error.message : null);
          });
          cardElementRef.current = card;
          setStatus("idle");
        }
      }, 100);
    });

    return () => {
      if (cardElementRef.current) {
        try { cardElementRef.current.unmount(); } catch {}
      }
    };
  }, [montoUSD, PUBLISHABLE_KEY]);

  const handlePago = async () => {
    if (!stripe || !cardElementRef.current || !cardReady) return;
    setLoading(true);
    setStatus("processing");
    setCardError(null);

    try {
      // 1. Crear PaymentIntent en el backend
      const intentRes = await fetch("/api/v1/pagos/stripe/intent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ monto_usd: montoUSD }),
      });
      const intentData = await intentRes.json();

      if (!intentRes.ok || intentData.error) {
        throw new Error(intentData.error || intentData.detail || "Error creando pago");
      }

      // 2. Confirmar pago con la tarjeta usando Stripe.js
      const { error, paymentIntent } = await stripe.confirmCardPayment(
        intentData.client_secret,
        { payment_method: { card: cardElementRef.current } }
      );

      if (error) {
        throw new Error(error.message);
      }

      if (paymentIntent.status === "succeeded") {
        // 3. Notificar al backend que el pago fue exitoso
        const confirmRes = await fetch("/api/v1/pagos/stripe/confirmar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ payment_intent_id: paymentIntent.id }),
        });
        const confirmData = await confirmRes.json();

        setStatus("success");
        onSuccess && onSuccess({
          paymentIntentId: paymentIntent.id,
          montoAcreditado: confirmData.monto_acreditado || montoUSD,
          saldoNuevo: confirmData.saldo_nuevo || 0,
        });
      } else {
        throw new Error(`Estado inesperado: ${paymentIntent.status}`);
      }
    } catch (e) {
      setCardError(e.message);
      setStatus("error");
      onError && onError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Estados visuales
  if (status === "success") {
    return (
      <div style={{ textAlign: "center", padding: "20px 0" }}>
        <div style={{ width: 56, height: 56, borderRadius: "50%", background: "rgba(23,204,133,.15)",
          border: "2px solid #17cc85", margin: "0 auto 12px",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <i className="fas fa-check" style={{ color: C.g, fontSize: 22 }} />
        </div>
        <div style={{ fontSize: 15, fontWeight: 600, color: C.g, marginBottom: 6 }}>
          Pago exitoso — ${montoUSD} USD
        </div>
        <div style={{ fontSize: 11, color: C.text2 }}>
          Fondos acreditados en tu cuenta InvestIQ
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Monto */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14,
        padding: "10px 14px", background: C.bg4, borderRadius: 8 }}>
        <span style={{ fontSize: 12, color: C.text2 }}>Total a pagar</span>
        <span style={{ fontSize: 16, fontWeight: 700, color: C.g }}>${montoUSD.toFixed(2)} USD</span>
      </div>

      {/* Card Element de Stripe */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 10, color: C.text3, textTransform: "uppercase",
          letterSpacing: ".06em", marginBottom: 6 }}>
          <i className="fas fa-lock" style={{ marginRight: 5, color: C.g }} />
          Datos de tarjeta — Encriptado por Stripe
        </div>
        <div ref={cardRef}
          style={{ background: C.bg4, border: `1px solid ${cardError ? C.r : C.border}`,
            borderRadius: 8, padding: "13px 14px", minHeight: 44,
            transition: "border-color .2s" }}>
          {status === "loading" && (
            <div style={{ color: C.text3, fontSize: 11 }}>
              <i className="fas fa-spinner fa-spin" style={{ marginRight: 6 }} />
              Cargando Stripe.js…
            </div>
          )}
        </div>
        {cardError && (
          <div style={{ marginTop: 6, fontSize: 10, color: C.r, display: "flex", alignItems: "center", gap: 5 }}>
            <i className="fas fa-exclamation-circle" />
            {cardError}
          </div>
        )}
      </div>

      {/* Tarjetas de prueba */}
      {PUBLISHABLE_KEY.startsWith("pk_test_") && (
        <div style={{ marginBottom: 12, padding: "8px 12px", background: "rgba(245,166,35,.08)",
          border: "1px solid rgba(245,166,35,.2)", borderRadius: 7, fontSize: 10, color: C.a }}>
          <b>Modo test:</b> Usa <code style={{ fontFamily: "monospace" }}>4242 4242 4242 4242</code> · exp: cualquier fecha futura · CVC: cualquier 3 dígitos
        </div>
      )}

      {/* Badges de seguridad */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {[
          ["fa-lock", "TLS 1.3"],
          ["fa-shield-alt", "PCI DSS"],
          ["fa-credit-card", "Visa · MC · AMEX"],
        ].map(([ico, label]) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 9,
            color: C.text3, padding: "3px 8px", background: C.bg4, borderRadius: 5, border: `1px solid ${C.border}` }}>
            <i className={`fas ${ico}`} style={{ color: C.g, fontSize: 10 }} />
            {label}
          </div>
        ))}
      </div>

      {/* Botón pagar */}
      <button
        onClick={handlePago}
        disabled={loading || !cardReady || !stripe || status === "processing"}
        style={{ width: "100%", background: cardReady ? C.g2 : "#2a3545",
          color: "#fff", border: "none", borderRadius: 9, padding: "12px",
          fontSize: 13, fontWeight: 700, cursor: cardReady ? "pointer" : "not-allowed",
          opacity: loading || !cardReady ? 0.7 : 1,
          boxShadow: cardReady ? "0 0 16px rgba(18,160,104,.3)" : "none",
          transition: "all .2s", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
        {loading || status === "processing"
          ? <><i className="fas fa-spinner fa-spin" /> Procesando…</>
          : <><i className="fas fa-lock" /> Pagar ${montoUSD.toFixed(2)} con Stripe</>}
      </button>

      <div style={{ textAlign: "center", marginTop: 10, fontSize: 9, color: C.text3 }}>
        Procesado de forma segura por{" "}
        <a href="https://stripe.com" target="_blank" rel="noreferrer"
          style={{ color: C.text2, textDecoration: "none" }}>Stripe</a>
        . InvestIQ nunca almacena datos de tarjeta.
      </div>
    </div>
  );
}
