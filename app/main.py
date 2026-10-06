from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.transactions import router as transaction_router
from app.api.routes.budgets import router as budget_router
from app.api.routes.analytics import router as analytics_router


app = FastAPI(
    title="Personal Finance API",
    description="A production-oriented personal finance REST API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request,
    exc: IntegrityError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Database constraint violation",
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
        },
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




