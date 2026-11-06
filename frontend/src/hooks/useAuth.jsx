import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, refreshSession, setAccessToken, setSessionLostHandler } from "../services/api";

const AuthContext = createContext(null);
// Not a credential: it only saves signed-out visitors a pointless refresh request on page load.
const SESSION_HINT = "proptwin_has_session";
const RETRY_DELAYS_MS = [500, 1500];

function readHint() {
  try {
    return localStorage.getItem(SESSION_HINT) === "1";
  } catch {
    return false;
  }
}

function writeHint(present) {
  try {
    if (present) localStorage.setItem(SESSION_HINT, "1");
    else localStorage.removeItem(SESSION_HINT);
  } catch {
    // Storage can be blocked. The session still works until the page reloads.
  }
}

async function restoreSession() {
  for (const delay of RETRY_DELAYS_MS) {
    try {
      return await refreshSession();
    } catch (error) {
      if (error.response?.status === 401) throw error;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  return refreshSession();
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(readHint);

  const clear = useCallback(() => {
    setAccessToken(null);
    writeHint(false);
    setUser(null);
  }, []);

  useEffect(() => {
    setSessionLostHandler(clear);
    if (!readHint()) return;
    restoreSession()
      .then((session) => setUser(session.user))
      .catch((error) => {
        // Only the server saying the session is dead ends it. A rate limit or network failure leaves it to try again later.
        if (error.response?.status === 401) clear();
      })
      .finally(() => setLoading(false));
  }, [clear]);

  const establish = useCallback((session) => {
    setAccessToken(session.access_token);
    writeHint(true);
    setUser(session.user);
    return session.user;
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      setUser,
      login: async (body) => establish(await api.auth.login(body)),
      demoLogin: async (email) => establish(await api.auth.demoLogin(email)),
      register: async (body) => establish(await api.auth.register(body)),
      logout: async () => {
        try {
          await api.auth.logout();
        } finally {
          clear();
        }
      },
      hasRole: (...roles) => Boolean(user?.roles.some((role) => roles.includes(role))),
    }),
    [user, loading, establish, clear],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
