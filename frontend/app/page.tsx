"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Dashboard from "../components/dashboard";
import { getAccessToken } from "../lib/api/client";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    if (!getAccessToken()) router.replace("/login");
  }, [router]);

  if (!getAccessToken()) return <main className="page-loading">Preparing your dashboard…</main>;
  return <Dashboard />;
}
