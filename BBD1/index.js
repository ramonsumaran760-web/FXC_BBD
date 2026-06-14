// hooks/useWebSocket.js
import { useEffect, useRef } from "react";
const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000/ws";

export function useWebSocket(onMessage) {
  const ws = useRef(null);
  const retries = useRef(0);
  useEffect(() => {
    const connect = () => {
      ws.current = new WebSocket(WS_URL);
      ws.current.onopen = () => { retries.current = 0; };
      ws.current.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch {} };
      ws.current.onclose = () => {
        const delay = Math.min(1000 * 2 ** retries.current, 30000);
        retries.current++;
        setTimeout(connect, delay);
      };
      ws.current.onerror = () => ws.current?.close();
    };
    connect();
    const ping = setInterval(() => {
      if (ws.current?.readyState === 1) ws.current.send(JSON.stringify({ type: "ping" }));
    }, 25000);
    return () => { clearInterval(ping); ws.current?.close(); };
  }, []);
  return ws;
}

// hooks/useLiveClock.js
import { useState, useEffect as useEff } from "react";
export function useLiveClock() {
  const [now, setNow] = useState(new Date());
  useEff(() => { const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id); }, []);
  return now;
}

// hooks/useTTS.js
export function useTTS(enabled = true) {
  const synth = window.speechSynthesis;
  const speak = (text) => {
    if (!enabled || !synth || !text) return;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "es-ES"; u.rate = 1.0; u.pitch = 0.85;
    const voices = synth.getVoices();
    const male = voices.find(v => v.lang.startsWith("es") &&
      ["Pablo","Jorge","Carlos","Juan","Miguel"].some(n => v.name.includes(n)));
    const spanish = voices.find(v => v.lang.startsWith("es"));
    u.voice = male || spanish || null;
    synth.speak(u);
  };
  const stop = () => synth?.cancel();
  return { speak, stop };
}

// hooks/usePrices.js
import { useEffect as useE2, useRef as useR2 } from "react";
export function usePriceUpdater(prices, portafolio) {
  // Calcula valor del portafolio con precios en vivo
  const calcValorPortafolio = (posiciones, liveprices) => {
    return posiciones.reduce((sum, p) => {
      const price = liveprices[p.ticker]?.price || p.precio_actual;
      return sum + price * p.acciones;
    }, 0);
  };
  return { calcValorPortafolio };
}

// hooks/usePortfolio.js
export function usePortfolioMetrics(posiciones = [], prices = {}) {
  const totalValor = posiciones.reduce((sum, p) => {
    const price = prices[p.ticker]?.price || p.precio_actual || 0;
    return sum + price * (p.acciones || 0);
  }, 0);
  const totalCosto = posiciones.reduce((sum, p) =>
    sum + (p.precio_promedio_compra || 0) * (p.acciones || 0), 0);
  const gananciaTotal = totalValor - totalCosto;
  const gananciaPct = totalCosto > 0 ? (gananciaTotal / totalCosto * 100) : 0;
  const distribucion = posiciones.map(p => ({
    ticker: p.ticker,
    valor: (prices[p.ticker]?.price || p.precio_actual || 0) * (p.acciones || 0),
    pct: totalValor > 0 ? ((prices[p.ticker]?.price || p.precio_actual || 0) * (p.acciones || 0)) / totalValor * 100 : 0,
  }));
  return { totalValor, totalCosto, gananciaTotal, gananciaPct, distribucion };
}
