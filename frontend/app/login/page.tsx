"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, getAccessToken, login, storeAuth } from "../../lib/api/client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (getAccessToken()) router.replace("/");
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const auth = await login(email, password);
      storeAuth(auth);
      router.replace("/");
    } catch (exception) {
      setError(exception instanceof ApiError ? exception.message : "Unable to sign in. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <div className="brand-mark">MC</div>
        <p className="eyebrow">Multi-cloud FinOps</p>
        <h1 id="login-title">See where your cloud spend goes.</h1>
        <p className="muted">Sign in to review real AWS, Azure, and GCP cost data.</p>
        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="current-password" />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="auth-note">
          Don&apos;t have an account? <Link href="/register">Create one</Link>
        </p>
      </section>
    </main>
  );
}
