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

## Quality checks

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

The dashboard uses live API responses; it does not include hardcoded cost
values or an AI/LLM integration.
