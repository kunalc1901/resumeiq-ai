import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make the app's own modules importable regardless of the working directory,
# so both `uvicorn app.main:app` (repo root) and `uvicorn main:app` (app/)
# work. Must run before the first-party imports below.
_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from api.health import router as health_router
from api.resume import router
from core.exceptions import BadRequestException, NotFoundException
from core.handlers import (
    bad_request_handler,
    general_error_handler,
    not_found_handler,
    validation_error_handler,
)
from database.mongodb import close_mongodb, init_mongodb
from middleware.cognito_auth import CognitoAuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_mongodb()
    yield
    close_mongodb()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CognitoAuthMiddleware)
app.include_router(router)
app.include_router(health_router)

app.exception_handler(RequestValidationError)(validation_error_handler)
app.exception_handler(NotFoundException)(not_found_handler)
app.exception_handler(BadRequestException)(bad_request_handler)
app.exception_handler(Exception)(general_error_handler)
