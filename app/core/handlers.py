from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.exceptions import BadRequestException, NotFoundException


async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "detail": "Invalid request data",
            "errors": exc.errors(),
        },
    )


async def not_found_handler(request: Request, exc: NotFoundException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "detail": exc.detail},
    )


async def bad_request_handler(request: Request, exc: BadRequestException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "detail": exc.detail},
    )


async def general_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "Internal server error"},
    )
