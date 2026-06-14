// services/api.js — Cliente HTTP centralizado para InvestIQ API
const BASE = process.env.REACT_APP_API_URL || "http://localhost:8000/api/v1";

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, opts = {}) {
  const token = localStorage.getItem("investiq_token");
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(err.detail || res.statusText, res.status, err);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (email, password, mfa_token) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password, mfa_token }) }),
  getMe: () => request("/auth/me"),
  mfaSetup: () => request("/auth/mfa/setup"),

  // Mercado
  getPrecios: (tickers) => request(`/mercado/precios${tickers ? "?tickers=" + tickers : ""}`),
  getCandles: (ticker, period = "1mo", interval = "1d") =>
    request(`/mercado/candles/${ticker}?period=${period}&interval=${interval}`),
  getActivos: () => request("/mercado/activos"),

  // Portafolio
  getPortafolio: () => request("/portafolio"),

  // Órdenes
  crearOrden: (data) => request("/ordenes", { method: "POST", body: JSON.stringify(data) }),
  getOrdenes: (limit = 50) => request(`/ordenes?limit=${limit}`),
  cancelarOrden: (id) => request(`/ordenes/${id}`, { method: "DELETE" }),

  // KYC / AML
  submitKYC: (data) => request("/kyc/submit", { method: "POST", body: JSON.stringify(data) }),
  amlCheck: (entidad, nit) => request("/aml/check", { method: "POST", body: JSON.stringify({ entidad, nit }) }),

  // Robo-Advisor
  roboAdvisor: (data) => request("/robo-advisor", { method: "POST", body: JSON.stringify(data) }),
  roboHistorial: () => request("/robo-advisor/historial"),

  // Transacciones
  depositar: (monto_usd, metodo = "bank_transfer") =>
    request("/transacciones/deposito", { method: "POST", body: JSON.stringify({ monto_usd, metodo }) }),
  getTransacciones: () => request("/transacciones"),
  getDividendos: () => request("/dividendos"),

  // Alertas
  getAlertas: () => request("/alertas"),
  leerAlertas: (ids) => request("/alertas/leer", { method: "PUT", body: JSON.stringify({ ids }) }),

  // Métricas
  getMetricas: () => request("/metricas"),

  // Exportes
  exportarExcel: () => { window.open(`${BASE}/exportar/excel`); },
  exportarPDF: () => { window.open(`${BASE}/exportar/pdf`); },

  // Auditoría
  getAuditoria: () => request("/auditoria"),

  // Health
  health: () => request("/health"),
};

export default api;
