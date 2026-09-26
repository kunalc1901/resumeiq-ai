from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from api.resume import router
from database.mongodb import init_mongodb, close_mongodb
from core.exceptions import NotFoundException, BadRequestException
from core.handlers import (
    validation_error_handler,
    not_found_handler,
    bad_request_handler,
    general_error_handler,
)
from middleware.cognito_auth import CognitoAuthMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_mongodb()
    yield
    close_mongodb()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CognitoAuthMiddleware)
app.include_router(router)

app.exception_handler(RequestValidationError)(validation_error_handler)
app.exception_handler(NotFoundException)(not_found_handler)
app.exception_handler(BadRequestException)(bad_request_handler)
app.exception_handler(Exception)(general_error_handler)