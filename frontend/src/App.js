import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import "./App.css";
import { api, setAuthHeader } from "./api";
import Login from "./pages/Login";
import Builder from "./pages/Builder";
import Studio from "./pages/Studio";

function App() {
  const [user, setUser] = useState(undefined); // undefined = checking, null = unauthed
  const [booted, setBooted] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/auth/me");
        setUser(data);
      } catch {
        setAuthHeader(null);
        setUser(null);
      } finally {
        setBooted(true);
      }
    })();
  }, []);

  if (!booted) {
    return (
      <div className="min-h-screen flex items-center justify-center"
           style={{ background: "#07070e" }}>
        <div className="text-sm mono" style={{ color: "#8a8aa3" }}>booting…</div>
      </div>
    );
  }

  return (
    <div className="App">
      <Toaster position="top-right" theme="dark"
               toastOptions={{ style: { background: "#0e0e1a", border: "1px solid #1f1f3a", color: "#e7e8ee", fontFamily: "IBM Plex Mono, monospace", fontSize: 12 } }} />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={
            user ? <Navigate to="/" replace /> : <Login onAuth={setUser} />
          } />
          <Route path="/" element={
            user ? <Builder user={user} setUser={setUser} /> : <Navigate to="/login" replace />
          } />
          <Route path="/studio" element={
            user ? <Studio /> : <Navigate to="/login" replace />
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
