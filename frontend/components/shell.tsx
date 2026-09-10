"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clearAuth, getStoredUser, logout } from "../lib/api/client";

export type AppTab = "dashboard" | "explorer" | "anomalies" | "optimization" | "alerts" | "budgets" | "copilot";
type NavItem = { id: AppTab; label: string; icon: string; section: string; description: string };

const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Overview", icon: "OV", section: "Workspace", description: "Executive spend overview" },
  { id: "explorer", label: "Spend", icon: "$", section: "Workspace", description: "Explore cloud spend" },
  { id: "anomalies", label: "Anomalies", icon: "!", section: "Workspace", description: "Investigate unusual spend" },
  { id: "optimization", label: "Optimization", icon: "OP", section: "Workspace", description: "Find savings opportunities" },
  { id: "budgets", label: "Budgets", icon: "BG", section: "Workspace", description: "Track budget health" },
  { id: "alerts", label: "Alerts", icon: "AL", section: "Workspace", description: "Manage cost alerts" },
  { id: "copilot", label: "FinOps Copilot", icon: "AI", section: "Intelligence", description: "Ask about verified FinOps data" },
];
const COMING_SOON = [{ label: "Forecasts", icon: "FC" }, { label: "Reports", icon: "RP" }, { label: "Policies", icon: "PL" }, { label: "Settings", icon: "ST" }];
const TITLES: Record<AppTab, { title: string; eyebrow: string }> = {
  dashboard: { title: "Overview", eyebrow: "Workspace / Overview" }, explorer: { title: "Spend", eyebrow: "Workspace / Spend" }, anomalies: { title: "Anomalies", eyebrow: "Workspace / Anomalies" }, optimization: { title: "Optimization", eyebrow: "Workspace / Optimization" }, alerts: { title: "Alerts", eyebrow: "Workspace / Alerts" }, budgets: { title: "Budgets", eyebrow: "Workspace / Budgets" }, copilot: { title: "FinOps Copilot", eyebrow: "Intelligence / Copilot" },
};

export default function Shell({ children, activeTab = "dashboard", onTabChange }: Readonly<{ children: React.ReactNode; activeTab?: AppTab; onTabChange?: (tab: AppTab) => void }>) {
  const router = useRouter();
  const user = getStoredUser();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const page = TITLES[activeTab];
  const initials = user?.full_name?.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "U";

  async function handleLogout() {
    try { await logout(); } catch { /* Local token removal still logs the user out. */ }
    clearAuth();
    router.replace("/login");
  }
  function selectTab(tab: AppTab) { onTabChange?.(tab); setMobileNavOpen(false); }

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={`sidebar ${mobileNavOpen ? "mobile-open" : ""}`}>
        <div className="sidebar-brand"><span className="brand-mark small">MC</span><span className="brand-name">Cost Detector</span><button type="button" className="sidebar-close" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation">×</button></div>
        <nav className="sidebar-nav" aria-label="Primary navigation">
          {["Workspace", "Intelligence"].map((section) => <div className="nav-section" key={section}><span className="nav-section-label">{section}</span>{NAV_ITEMS.filter((item) => item.section === section).map((item) => <button key={item.id} type="button" title={collapsed ? item.label : item.description} className={`nav-link ${activeTab === item.id ? "active" : ""}`} onClick={() => selectTab(item.id)}><span className="nav-icon" aria-hidden="true">{item.icon}</span><span className="nav-label">{item.label}</span></button>)}</div>)}
          <div className="nav-section"><span className="nav-section-label">Governance</span>{COMING_SOON.map((item) => <button key={item.label} type="button" className="nav-link disabled" title={`${item.label} is not available yet`} disabled><span className="nav-icon" aria-hidden="true">{item.icon}</span><span className="nav-label">{item.label}</span><span className="soon-label">Soon</span></button>)}</div>
        </nav>
        <div className="sidebar-bottom"><div className="workspace-status"><span className="status-dot" /><span className="nav-label">Live analytics</span></div><div className="workspace-user"><div className="avatar">{initials}</div><div className="nav-label"><strong>{user?.full_name || "Workspace user"}</strong><small>Personal workspace</small></div></div></div>
      </aside>
      <div className="content-column">
        <header className="topbar"><div className="topbar-left"><button type="button" className="mobile-menu-button" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation">☰</button><button type="button" className="collapse-button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} title={collapsed ? "Expand navigation" : "Collapse navigation"}>{collapsed ? "→" : "←"}</button><div className="topbar-title"><p className="breadcrumb">{page.eyebrow}</p><h2>{page.title}</h2></div></div><div className="topbar-actions"><label className="global-search"><span aria-hidden="true">⌕</span><input type="search" aria-label="Search workspace" placeholder="Search workspace" /><kbd>⌘ K</kbd></label><button type="button" className="icon-button" title="Open alerts" aria-label="Open alerts" onClick={() => selectTab("alerts")}>◌</button><div className="topbar-user"><div className="avatar">{initials}</div><span className="user-name">{user?.full_name || "User"}</span></div><button type="button" className="ghost-button signout-button" onClick={handleLogout}>Sign out</button></div></header>
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}
