"use client";

import { useRouter } from "next/navigation";
import { clearAuth, getStoredUser, logout } from "../lib/api/client";

export default function Shell({
  children,
  activeTab = "dashboard",
  onTabChange,
}: Readonly<{
  children: React.ReactNode;
  activeTab?: "dashboard" | "explorer" | "anomalies" | "optimization";
  onTabChange?: (tab: "dashboard" | "explorer" | "anomalies" | "optimization") => void;
}>) {
  const router = useRouter();
  const user = getStoredUser();

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Local token removal still logs the user out when the API is unavailable.
    }
    clearAuth();
    router.replace("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark small">MC</span>
          <span>Cost Detector</span>
        </div>
        <nav aria-label="Primary navigation">
          <button
            type="button"
            className={`nav-link ${activeTab === "dashboard" ? "active" : ""}`}
            style={{ width: "100%", border: 0, textAlign: "left", cursor: "pointer" }}
            onClick={() => onTabChange?.("dashboard")}
          >
            <span aria-hidden="true">▦</span> Dashboard
          </button>
          <button type="button" className={`nav-link ${activeTab === "anomalies" ? "active" : ""}`} style={{ width: "100%", border: 0, textAlign: "left", cursor: "pointer", marginTop: "4px" }} onClick={() => onTabChange?.("anomalies")}>
            <span aria-hidden="true">!</span> Cost Anomalies
          </button>
          <button type="button" className={`nav-link ${activeTab === "optimization" ? "active" : ""}`} style={{ width: "100%", border: 0, textAlign: "left", cursor: "pointer", marginTop: "4px" }} onClick={() => onTabChange?.("optimization")}>
            <span aria-hidden="true">$</span> Cost Optimization
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === "explorer" ? "active" : ""}`}
            style={{ width: "100%", border: 0, textAlign: "left", cursor: "pointer", marginTop: "4px" }}
            onClick={() => onTabChange?.("explorer")}
          >
            <span aria-hidden="true">🔍</span> Cost Explorer
          </button>
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot" /> Live analytics
        </div>
      </aside>
      <div className="content-column">
        <header className="topbar">
          <div>
            <p className="eyebrow">Workspace overview</p>
            <h2>{activeTab === "explorer" ? "Cost Explorer" : activeTab === "anomalies" ? "Cost Anomalies" : activeTab === "optimization" ? "Cost Optimization" : "Dashboard"}</h2>
          </div>
          <div className="user-menu">
            <div className="avatar">{user?.full_name?.slice(0, 1).toUpperCase() || "U"}</div>
            <span className="user-name">{user?.full_name || "User"}</span>
            <button className="ghost-button" onClick={handleLogout}>
              Sign out
            </button>
          </div>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
