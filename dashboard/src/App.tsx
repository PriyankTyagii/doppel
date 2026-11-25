import { useEffect } from "react";
import { Brand } from "./components/Brand";
import { AuthProvider, useAuth } from "./lib/auth";
import { missingConfig } from "./lib/firebase";
import { navigate, usePath } from "./lib/router";
import { Dashboard } from "./pages/Dashboard";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Present } from "./pages/Present";

const PROTECTED = new Set(["/app", "/present"]);

function Routes() {
  const path = usePath();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (PROTECTED.has(path) && !user) navigate(`/login?next=${encodeURIComponent(path)}`, true);
    if (path === "/login" && user) {
      const next = new URLSearchParams(location.search).get("next");
      navigate(next && PROTECTED.has(next) ? next : "/app", true);
    }
  }, [path, user, loading]);

  // Public pages render at once; only sign-in and protected pages wait for the auth state.
  if (path === "/") return <Landing />;
  if (loading) return <div className="boot" aria-busy="true" />;
  if (path === "/login") return user ? null : <Login />;
  if (PROTECTED.has(path)) {
    if (!user) return null;
    return path === "/present" ? <Present /> : <Dashboard />;
  }
  return <NotFound />;
}

function NotFound() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <Brand />
        <h1>Page not found</h1>
        <a className="btn btn-primary btn-block" href="/">
          Go home
        </a>
      </div>
    </div>
  );
}

function SetupNeeded() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <Brand />
        <h1>Firebase is not configured</h1>
        <p>
          Copy <code>dashboard/.env.example</code> to <code>dashboard/.env.local</code>, fill in these values from the Firebase
          console, and restart the dev server:
        </p>
        <ul>
          {missingConfig.map((k) => (
            <li key={k}>
              <code>{k}</code>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function App() {
  if (missingConfig.length) return <SetupNeeded />;
  return (
    <AuthProvider>
      <Routes />
    </AuthProvider>
  );
}
