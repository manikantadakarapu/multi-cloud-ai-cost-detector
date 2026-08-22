"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getAccessToken, register, storeAuth } from "../../lib/api/client";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (getAccessToken()) router.replace("/");
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
      setError("Password must be at least 8 characters and include an uppercase letter, lowercase letter, and number.");
      return;
    }

    setLoading(true);
    try {
      const auth = await register(fullName, email, password);
      storeAuth(auth);
      router.replace("/");
    } catch (exception) {
      setError(exception instanceof ApiError ? exception.message : "Unable to create your account. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="register-title">
        <div className="brand-mark">MC</div>
        <p className="eyebrow">Multi-cloud FinOps</p>
        <h1 id="register-title">Start tracking cloud spend.</h1>
        <p className="muted">Create an account to review your AWS, Azure, and GCP cost data.</p>
        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            Full name
            <input type="text" value={fullName} onChange={(event) => setFullName(event.target.value)} required maxLength={255} autoComplete="name" />
          </label>
          <label>
            Email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete="new-password" aria-describedby="password-requirements" />
          </label>
          <p id="password-requirements" className="field-help">Use at least 8 characters with an uppercase letter, lowercase letter, and number.</p>
          <label>
            Confirm password
            <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength={8} autoComplete="new-password" />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p className="auth-note">
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
