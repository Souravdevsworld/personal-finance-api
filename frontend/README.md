# Personal Finance Frontend (React + TypeScript + Vite + Tailwind)

    npm install
    cp .env.example .env     # set VITE_API_BASE_URL
    npm run dev              # http://localhost:5173

Backend (separate project, untouched): run it on port 8000 with uvicorn.

CORS: the FastAPI backend must allow http://localhost:5173 (CORSMiddleware).
This frontend does not change the backend; until CORS is configured you will see a network error.

Auth: the JWT from POST /api/auth/login (form-encoded) is kept in localStorage and sent as
Authorization: Bearer. Any 401 clears the session and redirects to Login.
