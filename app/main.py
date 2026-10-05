from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.transactions import router as transaction_router
from app.api.routes.budgets import router as budget_router
from app.api.routes.analytics import router as analytics_router

app = FastAPI(
    title="Personal Finance API",
    description="A production-oriented personal finance REST API",
    version="1.0.0",
)

app.include_router(auth_router)
app.include_router(transaction_router)
app.include_router(budget_router)
app.include_router(analytics_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Personal Finance API is running"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}




