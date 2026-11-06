import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

// The access token lives only in memory. The refresh token is an HttpOnly cookie that scripts cannot read.
let accessToken = null;
let onSessionLost = () => {};
let refreshInFlight = null;

export function setAccessToken(token) {
  accessToken = token;
}

export function setSessionLostHandler(handler) {
  onSessionLost = handler;
}

export class ApiError extends Error {
  constructor(status, code, message, fields = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

export function toApiError(error) {
  if (error instanceof ApiError) return error;
  const body = error.response?.data?.error;
  if (body) return new ApiError(error.response.status, body.code, body.message, body.fields ?? []);
  if (error.response) return new ApiError(error.response.status, "http_error", "The server returned an unexpected response.");
  return new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
}

export const http = axios.create({
  baseURL: BASE_URL,
  withCredentials: true,
  headers: { "X-Requested-With": "XMLHttpRequest" },
});

http.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

// One shared refresh at a time. Refresh tokens are single use, and the server treats a second use as theft.
export function refreshSession() {
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post(`${BASE_URL}/auth/refresh`, null, { withCredentials: true, headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((response) => {
        accessToken = response.data.access_token;
        return response.data;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

const NO_RETRY = ["/auth/login", "/auth/demo-login", "/auth/register", "/auth/refresh", "/auth/logout"];

http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const skip = !original || original._retried || NO_RETRY.some((path) => original.url?.includes(path));
    if (error.response?.status === 401 && !skip && accessToken) {
      original._retried = true;
      try {
        await refreshSession();
        original.headers.Authorization = `Bearer ${accessToken}`;
        return http(original);
      } catch {
        accessToken = null;
        onSessionLost();
      }
    }
    throw toApiError(error);
  },
);

const data = (promise) => promise.then((response) => response.data);

export const api = {
  auth: {
    register: (body) => data(http.post("/auth/register", body)),
    login: (body) => data(http.post("/auth/login", body)),
    demoAccounts: () => data(http.get("/auth/demo-accounts")),
    demoLogin: (email) => data(http.post("/auth/demo-login", { email })),
    logout: () => data(http.post("/auth/logout")),
    logoutAll: () => data(http.post("/auth/logout-all")),
    requestReset: (email) => data(http.post("/auth/password-reset/request", { email })),
    confirmReset: (body) => data(http.post("/auth/password-reset/confirm", body)),
    requestEmailVerification: () => data(http.post("/auth/email-verification/request")),
    confirmEmail: (token) => data(http.post("/auth/email-verification/confirm", { token })),
  },
  users: {
    update: (body) => data(http.patch("/users/me", body)),
    changePassword: (body) => data(http.post("/users/me/password", body)),
    walletChallenge: (address) => data(http.post("/users/me/wallet/challenge", { address })),
    linkWallet: (body) => data(http.post("/users/me/wallet", body)),
  },
  properties: {
    search: (params) => data(http.get("/properties", { params })),
    mine: (params) => data(http.get("/properties/mine", { params })),
    portfolio: () => data(http.get("/properties/mine/portfolio")),
    insights: (id) => data(http.get(`/properties/${id}/insights`)),
    compare: (ids) => {
      const query = new URLSearchParams();
      ids.forEach((id) => query.append("ids", id));
      return data(http.get(`/properties/compare?${query}`));
    },
    get: (id) => data(http.get(`/properties/${id}`)),
    create: (body) => data(http.post("/properties", body)),
    update: (id, body) => data(http.patch(`/properties/${id}`, body)),
    archive: (id) => data(http.delete(`/properties/${id}`)),
    uploadImage: (id, file) => {
      const form = new FormData();
      form.append("file", file);
      return data(http.post(`/properties/${id}/images`, form));
    },
    imageBlob: (id, imageId) => data(http.get(`/properties/${id}/images/${imageId}`, { responseType: "blob" })),
    documents: (id) => data(http.get(`/properties/${id}/documents`)),
    uploadDocument: (id, file, documentType) => {
      const form = new FormData();
      form.append("file", file);
      form.append("document_type", documentType);
      return data(http.post(`/properties/${id}/documents`, form));
    },
    documentBlob: (id, documentId) => data(http.get(`/properties/${id}/documents/${documentId}`, { responseType: "blob" })),
    addRenovation: (id, body) => data(http.post(`/properties/${id}/renovations`, body)),
    report: (id, reason) => data(http.post(`/properties/${id}/report`, { reason })),
    requestVerification: (id, notes) => data(http.post(`/properties/${id}/verification-requests`, { notes })),
    verificationHistory: (id) => data(http.get(`/properties/${id}/verification-requests`)),
    valuations: (id, params) => data(http.get(`/properties/${id}/valuations`, { params })),
  },
  favorites: {
    list: () => data(http.get("/saved-properties")),
    add: (id) => data(http.put(`/saved-properties/${id}`)),
    remove: (id) => data(http.delete(`/saved-properties/${id}`)),
  },
  valuations: {
    predict: (body) => data(http.post("/valuations/predict", body)),
    get: (id) => data(http.get(`/valuations/${id}`)),
  },
  twins: {
    create: (propertyId) => data(http.post(`/properties/${propertyId}/twin`)),
    forProperty: (propertyId) => data(http.get(`/properties/${propertyId}/twin`)),
    update: (id, body) => data(http.patch(`/twins/${id}`, body)),
    simulate: (id, body) => data(http.post(`/twins/${id}/simulate`, body)),
    history: (id, params) => data(http.get(`/twins/${id}/history`, { params })),
    simulations: (id, params) => data(http.get(`/twins/${id}/simulations`, { params })),
    market: (id) => data(http.get(`/twins/${id}/market`)),
  },
  chain: {
    network: () => data(http.get("/blockchain/network")),
    register: (id) => data(http.post(`/blockchain/properties/${id}/register`)),
    assignController: (id) => data(http.post(`/blockchain/properties/${id}/assign-controller`)),
    verify: (id) => data(http.post(`/blockchain/properties/${id}/verify`)),
    history: (id) => data(http.get(`/blockchain/properties/${id}/history`)),
    record: (id) => data(http.get(`/blockchain/properties/${id}/record`)),
    transaction: (id) => data(http.get(`/blockchain/transactions/${id}`)),
    submit: (id, txHash) => data(http.post(`/blockchain/transactions/${id}/submit`, { tx_hash: txHash })),
    abandon: (id) => data(http.post(`/blockchain/transactions/${id}/abandon`)),
    transfers: () => data(http.get("/blockchain/ownership-transfer")),
    createTransfer: (body) => data(http.post("/blockchain/ownership-transfer", body)),
    proposeTransfer: (id) => data(http.post(`/blockchain/ownership-transfer/${id}/propose`)),
    acceptTransfer: (id) => data(http.post(`/blockchain/ownership-transfer/${id}/accept`)),
    cancelTransfer: (id) => data(http.post(`/blockchain/ownership-transfer/${id}/cancel`)),
    commitValuation: (valuationId) => data(http.post(`/blockchain/valuations/${valuationId}/commit`)),
  },
  verification: {
    queue: (params) => data(http.get("/verification/queue", { params })),
    decide: (id, body) => data(http.post(`/verification/${id}/decision`, body)),
  },
  market: {
    localities: () => data(http.get("/market/localities")),
    trend: (locality) => data(http.get(`/market/localities/${encodeURIComponent(locality)}/trend`)),
  },
  dashboard: () => data(http.get("/dashboard")),
  notifications: {
    list: (params) => data(http.get("/notifications", { params })),
    markRead: (id) => data(http.post(`/notifications/${id}/read`)),
  },
  admin: {
    users: (params) => data(http.get("/admin/users", { params })),
    updateUser: (id, body) => data(http.patch(`/admin/users/${id}`, body)),
    auditLogs: (params) => data(http.get("/admin/audit-logs", { params })),
    reports: (params) => data(http.get("/admin/reports", { params })),
    resolveReport: (id, body) => data(http.patch(`/admin/reports/${id}`, body)),
    transactions: (params) => data(http.get("/admin/transactions", { params })),
    monitoring: () => data(http.get("/admin/monitoring")),
    models: () => data(http.get("/admin/models")),
    modelMetrics: (version) => data(http.get(`/admin/models/${version}/metrics`)),
    promoteModel: (version, target) => data(http.post(`/admin/models/${version}/promote`, { target })),
  },
};
