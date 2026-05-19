import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setAuthHeader, formatErr } from "../api";
import { Workflow, LogIn } from "lucide-react";

export default function Login({ onAuth }) {
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@delaybridge.io");
  const [password, setPassword] = useState("DelayBridge#2026");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      setAuthHeader(data.access_token);
      onAuth?.(data.user);
      nav("/", { replace: true });
    } catch (e) {
      setErr(formatErr(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6" data-testid="login-page">
      <div className="w-full max-w-md fade-in">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center"
               style={{ background: "rgba(0,170,255,0.1)", border: "1px solid rgba(0,170,255,0.4)" }}>
            <Workflow className="w-5 h-5" style={{ color: "#00aaff" }} />
          </div>
          <div>
            <div className="text-xl font-semibold tracking-tight">DelayBridge</div>
            <div className="text-xs mono" style={{ color: "var(--db-muted)" }}>
              project delay intelligence
            </div>
          </div>
        </div>

        <div className="db-card p-8">
          <h1 className="text-2xl font-semibold mb-1">Sign in</h1>
          <p className="text-sm mb-6" style={{ color: "var(--db-muted)" }}>
            Admin access — connect sheets and build export links.
          </p>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs mono uppercase tracking-wider"
                     style={{ color: "var(--db-muted)" }}>Email</label>
              <input
                data-testid="login-email-input"
                type="email"
                className="db-input mt-1"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-xs mono uppercase tracking-wider"
                     style={{ color: "var(--db-muted)" }}>Password</label>
              <input
                data-testid="login-password-input"
                type="password"
                className="db-input mt-1"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {err && (
              <div data-testid="login-error" className="text-sm db-danger mono">
                {err}
              </div>
            )}
            <button
              data-testid="login-submit-button"
              type="submit"
              disabled={loading}
              className="db-btn w-full justify-center"
            >
              <LogIn className="w-4 h-4" /> {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <div className="mt-6 text-xs mono" style={{ color: "var(--db-muted)" }}>
            Default credentials are pre-filled from <code>/app/memory/test_credentials.md</code>
          </div>
        </div>
      </div>
    </div>
  );
}
