// store/store.js — Estado global InvestIQ con useReducer + Context
import React, { createContext, useContext, useReducer, useCallback } from "react";
import api from "../services/api";

const initialState = {
  // Auth
  usuario: null,
  token: localStorage.getItem("investiq_token"),
  // Mercado
  prices: {},
  activos: [],
  wsStatus: "disconnected",
  // Portafolio
  portafolio: { posiciones: [], total_valor_usd: 0, ganancia_perdida_total: 0, saldo_disponible: 0 },
  // Órdenes
  ordenes: [],
  // Métricas
  metricas: {},
  // Alertas
  alertas: [],
  unreadAlerts: 0,
  // Tareas checklist (local)
  tasks: [
    { id: 1, titulo: "Declaración IVA junio 2026", modulo: "fiscal", prioridad: 3, completada: false },
    { id: 2, titulo: "Verificación KYC biométrica", modulo: "compliance", prioridad: 3, completada: false },
    { id: 3, titulo: "Reporte fiscal anual", modulo: "fiscal", prioridad: 2, completada: false },
    { id: 4, titulo: "Reconciliación portafolio vs broker", modulo: "inversiones", prioridad: 2, completada: true },
    { id: 5, titulo: "Activar MFA 2FA", modulo: "seguridad", prioridad: 3, completada: false },
    { id: 6, titulo: "Backup base de datos", modulo: "sistema", prioridad: 1, completada: true },
    { id: 7, titulo: "Revisar concentración NVDA", modulo: "inversiones", prioridad: 2, completada: false },
    { id: 8, titulo: "Conectar Alpaca API real", modulo: "broker", prioridad: 2, completada: false },
  ],
  // Robo-Advisor
  roboResult: null,
  roboHistorial: [],
  // UI
  activeNav: "dashboard",
  panels: { robo: false, kyc: false, ordenes: false, fiscal: false, audit: false, deposito: false },
  ttsEnabled: true,
  loading: {},
  toast: null,
  // Candles
  candles: {},
  tickerChart: "AAPL",
  // Sliders
  params: { minOrden: 1, maxConcentracion: 35, umbralIA: 15, limiteRetiro: 500 },
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_USUARIO": return { ...state, usuario: action.payload };
    case "SET_TOKEN":
      if (action.payload) localStorage.setItem("investiq_token", action.payload);
      else localStorage.removeItem("investiq_token");
      return { ...state, token: action.payload };
    case "SET_PRICES": return { ...state, prices: { ...state.prices, ...action.payload } };
    case "SET_ACTIVOS": return { ...state, activos: action.payload };
    case "SET_WS_STATUS": return { ...state, wsStatus: action.payload };
    case "SET_PORTAFOLIO": return { ...state, portafolio: action.payload };
    case "SET_ORDENES": return { ...state, ordenes: action.payload };
    case "PREPEND_ORDEN": return { ...state, ordenes: [action.payload, ...state.ordenes.slice(0, 49)] };
    case "SET_METRICAS": return { ...state, metricas: action.payload };
    case "SET_ALERTAS":
      return { ...state, alertas: action.payload, unreadAlerts: action.payload.filter(a => !a.leida).length };
    case "PREPEND_ALERTA":
      return { ...state, alertas: [action.payload, ...state.alertas], unreadAlerts: state.unreadAlerts + 1 };
    case "LEER_ALERTA":
      return { ...state, alertas: state.alertas.map(a => a.id === action.id ? { ...a, leida: true } : a),
               unreadAlerts: Math.max(0, state.unreadAlerts - 1) };
    case "TOGGLE_TASK":
      return { ...state, tasks: state.tasks.map(t => t.id === action.id ? { ...t, completada: !t.completada } : t) };
    case "ADD_TASK":
      return { ...state, tasks: [...state.tasks, { id: Date.now(), titulo: action.titulo, modulo: "general", prioridad: 1, completada: false }] };
    case "SET_ROBO": return { ...state, roboResult: action.payload };
    case "SET_ROBO_HISTORIAL": return { ...state, roboHistorial: action.payload };
    case "SET_NAV": return { ...state, activeNav: action.payload };
    case "TOGGLE_PANEL":
      return { ...state, panels: { ...state.panels, [action.panel]: !state.panels[action.panel] } };
    case "CLOSE_PANEL":
      return { ...state, panels: { ...state.panels, [action.panel]: false } };
    case "OPEN_PANEL":
      return { ...state, panels: { ...state.panels, [action.panel]: true } };
    case "SET_TTS": return { ...state, ttsEnabled: action.payload };
    case "SET_LOADING":
      return { ...state, loading: { ...state.loading, [action.key]: action.value } };
    case "SET_TOAST": return { ...state, toast: action.payload };
    case "SET_CANDLES":
      return { ...state, candles: { ...state.candles, [action.ticker]: action.payload } };
    case "SET_TICKER_CHART": return { ...state, tickerChart: action.payload };
    case "SET_PARAM":
      return { ...state, params: { ...state.params, [action.key]: action.value } };
    default: return state;
  }
}

const StoreContext = createContext(null);

export function StoreProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const actions = {
    // Auth
    login: async (email, password, mfa_token) => {
      dispatch({ type: "SET_LOADING", key: "login", value: true });
      try {
        const r = await api.login(email, password, mfa_token);
        dispatch({ type: "SET_TOKEN", payload: r.access_token });
        dispatch({ type: "SET_USUARIO", payload: r.usuario });
        return r;
      } finally { dispatch({ type: "SET_LOADING", key: "login", value: false }); }
    },
    logout: () => {
      dispatch({ type: "SET_TOKEN", payload: null });
      dispatch({ type: "SET_USUARIO", payload: null });
    },

    // Market
    loadPrecios: async (tickers) => {
      try { const p = await api.getPrecios(tickers); dispatch({ type: "SET_PRICES", payload: p }); return p; } catch {}
    },
    loadCandles: async (ticker = "AAPL", period = "1mo") => {
      try {
        const d = await api.getCandles(ticker, period);
        dispatch({ type: "SET_CANDLES", ticker, payload: d.candles || [] });
        return d.candles;
      } catch {}
    },
    loadActivos: async () => {
      try { const a = await api.getActivos(); dispatch({ type: "SET_ACTIVOS", payload: a }); } catch {}
    },

    // Portfolio
    loadPortafolio: async () => {
      try { const p = await api.getPortafolio(); dispatch({ type: "SET_PORTAFOLIO", payload: p }); return p; } catch {}
    },

    // Orders
    crearOrden: async (data) => {
      dispatch({ type: "SET_LOADING", key: "orden", value: true });
      try {
        const r = await api.crearOrden(data);
        dispatch({ type: "PREPEND_ORDEN", payload: r });
        await actions.loadPortafolio();
        await actions.loadMetricas();
        actions.toast(`Orden ejecutada: ${r.tipo?.toUpperCase()} ${r.ticker} · $${r.monto_usd}`, "success");
        return r;
      } finally { dispatch({ type: "SET_LOADING", key: "orden", value: false }); }
    },
    loadOrdenes: async () => {
      try { const o = await api.getOrdenes(); dispatch({ type: "SET_ORDENES", payload: o }); } catch {}
    },

    // Métricas
    loadMetricas: async () => {
      try { const m = await api.getMetricas(); dispatch({ type: "SET_METRICAS", payload: m }); } catch {}
    },

    // Alertas
    loadAlertas: async () => {
      try { const a = await api.getAlertas(); dispatch({ type: "SET_ALERTAS", payload: a }); } catch {}
    },
    leerAlerta: async (id) => {
      dispatch({ type: "LEER_ALERTA", id });
      try { await api.leerAlertas([id]); } catch {}
    },
    prependAlerta: (a) => dispatch({ type: "PREPEND_ALERTA", payload: a }),

    // Tasks
    toggleTask: (id) => dispatch({ type: "TOGGLE_TASK", id }),
    addTask: (titulo) => dispatch({ type: "ADD_TASK", titulo }),

    // Robo
    ejecutarRobo: async (form) => {
      dispatch({ type: "SET_LOADING", key: "robo", value: true });
      try {
        const r = await api.roboAdvisor(form);
        dispatch({ type: "SET_ROBO", payload: r });
        return r;
      } finally { dispatch({ type: "SET_LOADING", key: "robo", value: false }); }
    },

    // Depósito
    depositar: async (monto_usd) => {
      const r = await api.depositar(monto_usd);
      await actions.loadMetricas();
      actions.toast(`Depósito exitoso: $${monto_usd.toLocaleString()}`, "success");
      return r;
    },

    // UI
    setNav: (nav) => dispatch({ type: "SET_NAV", payload: nav }),
    openPanel: (p) => dispatch({ type: "OPEN_PANEL", panel: p }),
    closePanel: (p) => dispatch({ type: "CLOSE_PANEL", panel: p }),
    togglePanel: (p) => dispatch({ type: "TOGGLE_PANEL", panel: p }),
    setTTS: (v) => dispatch({ type: "SET_TTS", payload: v }),
    setTickerChart: (t) => dispatch({ type: "SET_TICKER_CHART", payload: t }),
    setParam: (key, value) => dispatch({ type: "SET_PARAM", key, value }),
    toast: (msg, type = "success") => {
      dispatch({ type: "SET_TOAST", payload: { msg, type } });
      setTimeout(() => dispatch({ type: "SET_TOAST", payload: null }), 3500);
    },

    // WebSocket handlers
    handleWsMessage: (msg, dispatch) => {
      if (msg.type === "prices" || msg.type === "init") dispatch({ type: "SET_PRICES", payload: msg.data || msg.prices || {} });
      if (msg.type === "orden") { dispatch({ type: "PREPEND_ORDEN", payload: msg.data }); }
    },

    // Load all
    loadAll: async () => {
      await Promise.all([
        actions.loadMetricas(),
        actions.loadPortafolio(),
        actions.loadOrdenes(),
        actions.loadAlertas(),
        actions.loadCandles("AAPL"),
        actions.loadActivos(),
      ]);
    },
  };

  return <StoreContext.Provider value={{ state, dispatch, actions }}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be inside StoreProvider");
  return ctx;
}
