"use client";
import { useState } from "react";

export default function LocalAccess() {
  const [token, setToken] = useState("");
  return (
    <form aria-label="Local operator access"
      style={{ position: "fixed", right: 12, top: 8, zIndex: 1000, background: "white", padding: 8, border: "1px solid #dde3da", borderRadius: 6 }}
      onSubmit={(event) => {
        event.preventDefault();
        sessionStorage.setItem("intentos-access-token", token);
        window.location.reload();
      }}>
      <input type="password" aria-label="Operator-issued access token" placeholder="Operator-issued access token"
        autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} />
      <button type="submit" disabled={!token}>Use token</button>
      <button type="button" onClick={() => {
        sessionStorage.removeItem("intentos-access-token");
        window.location.reload();
      }}>Sign out</button>
    </form>
  );
}
