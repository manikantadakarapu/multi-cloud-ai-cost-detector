# Frontend

The frontend is a small Next.js dashboard MVP for the existing FastAPI
analytics and dashboard contracts.

## Local development

Start the backend and its PostgreSQL/Redis dependencies first. Then run:

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open <http://localhost:3000>. Set `NEXT_PUBLIC_API_BASE_URL` when the backend
is not running at `http://localhost:8000`. The backend `CORS_ORIGINS` must
include the frontend origin.

To preview the dashboard with deterministic sample data while provider
credentials are being configured, set `NEXT_PUBLIC_DEMO_MODE=true` in
`.env.local` and restart Next.js. Demo mode is disabled by default and is
clearly labeled in the dashboard.

## Quality checks

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

The dashboard uses live API responses by default. Demo mode is an explicit
local preview and does not change backend responses or add an AI/LLM integration.
