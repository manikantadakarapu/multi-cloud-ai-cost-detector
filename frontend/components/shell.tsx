"use client";

import { useRouter } from "next/navigation";
import { clearAuth, getStoredUser, logout } from "../lib/api/client";

export default function Shell({ children }: Readonly<{ children: React.ReactNode }>) {
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
        <div className="sidebar-brand"><span className="brand-mark small">MC</span><span>Cost Detector</span></div>
        <nav aria-label="Primary navigation">
          <a className="nav-link active" href="#dashboard"><span aria-hidden="true">▦</span> Dashboard</a>
        </nav>
        <div className="sidebar-footer"><span className="status-dot" /> Live analytics</div>
      </aside>
      <div className="content-column">
        <header className="topbar">
          <div><p className="eyebrow">Workspace overview</p><h2>Dashboard</h2></div>
          <div className="user-menu"><div className="avatar">{user?.full_name?.slice(0, 1).toUpperCase() || "U"}</div><span className="user-name">{user?.full_name || "User"}</span><button className="ghost-button" onClick={handleLogout}>Sign out</button></div>
        </header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
