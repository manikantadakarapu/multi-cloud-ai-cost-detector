# Security Policy

This document describes how security vulnerabilities are handled in the
**Multi-Cloud AI Cost Detective** (MCAICD) project and the security practices
all contributors must follow.

---

## Supported Versions

MCAICD is in active development. Only the latest minor release receives
security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | ✅ Active support   |
| < 0.1   | ❌ Not supported     |

Once version 1.0.0 is released, the policy will be expanded to cover the two
most recent minor releases.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security vulnerability, please report it privately:

1. Email the maintainer at **manikantadakarapu@users.noreply.github.com**.
2. Include a clear description of the issue, the steps to reproduce it, and
   the potential impact.
3. If possible, suggest a fix or mitigation.

You will receive an acknowledgement within **72 hours** and a status update
within **7 days**. Please do not disclose the vulnerability publicly until a
fix has been released and you have been given the go-ahead.

---

## Responsible Disclosure

We follow a coordinated disclosure process:

1. The reporter submits the vulnerability privately.
2. The maintainer confirms the report and triages the severity.
3. A fix is developed on a private branch and reviewed.
4. A patched release is published.
5. Public disclosure follows after users have had a reasonable window to
   upgrade (typically 14 days).

We credit reporters in the release notes unless they prefer to remain
anonymous.

---

## Security Best Practices for Contributors

### Secrets management

- **Never commit secrets.** The `.gitignore` file excludes `.env` and
  `.env.*` (except `.env.example`). Double-check that you are not staging a
  real `.env` file.
- All configuration flows through `app/core/config.py` (Pydantic Settings).
  Read settings from the `settings` object — never call `os.getenv()` or
  `os.environ` directly in application code.
- The `.env.example` file documents the required variables with placeholder
  values only. Do not put real credentials in it.
- If you accidentally commit a secret, **do not just delete it in a new
  commit** — the secret must be considered compromised. Rotate it immediately
  and notify a maintainer so the history can be rewritten.

### Database

- Use parameterised queries or SQLAlchemy ORM constructs exclusively. Never
  build SQL by string concatenation.
- The async SQLAlchemy session factory is configured with `pool_pre_ping=True`
  so stale connections are detected before use.

### Input validation

- All request bodies are validated by Pydantic v2 response/request models.
  Do not accept untyped input.
- Use `Literal` types where a field has a fixed set of valid values.

### Dependencies

- Do not add a dependency without explicit maintainer approval.
- Prefer dependencies with an active maintenance record and a permissive
  license.

---

## Dependency Updates

Dependencies are tracked in `pyproject.toml`. The project pins lower bounds
and uses `>=` ranges to allow patch and minor upgrades.

- **Routine updates** (patch / minor): open a PR with the updated range,
  run the full test suite, and request review.
- **Major updates**: open an issue first to discuss the migration impact
  before opening a PR.
- Review transitive dependencies when a direct dependency is updated — a
  change in a sub-dependency can introduce vulnerabilities.

A dependency scanning workflow (e.g. Dependabot) is planned for a later
sprint and is not yet configured.
