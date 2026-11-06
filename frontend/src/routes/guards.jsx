import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Spinner } from "../components/ui";
import { useAuth } from "../hooks/useAuth";

export function RequireAuth({ roles }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Checking your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !user.roles.some((role) => roles.includes(role))) return <Forbidden />;
  return <Outlet />;
}

export function GuestOnly() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Checking your session" />;
  return user ? <Navigate to="/dashboard" replace /> : <Outlet />;
}

function Forbidden() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-semibold text-navy-900">You do not have access to this page</h1>
      <p className="mt-2 text-sm text-slate-600">Your account does not have the role this page requires.</p>
    </div>
  );
}
