"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Dashboard from "../components/dashboard";
import { getAccessToken } from "../lib/api/client";

export default function HomePage() {
  const router = useRouter();
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const hasToken = Boolean(getAccessToken());
    setAuthenticated(hasToken);
    if (!hasToken) router.replace("/login");
  }, [router]);

  if (authenticated !== true) {
    return <main className="page-loading">{authenticated === false ? "Redirecting to sign in…" : "Preparing your dashboard…"}</main>;
  }
  return <Dashboard />;
}
