import json
import logging
import time

import boto3
import jwt
from fastapi import Request
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.config import settings

logger = logging.getLogger("cognito")

PUBLIC_PATHS = {"/docs", "/redoc", "/openapi.json", "/health"}

_user_cache = {}


def _get_user_attributes_from_cognito(token: str) -> dict:
    """Fetch the user's attributes from Cognito using the access token."""
    cognito = boto3.client(
        "cognito-idp",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        region_name=settings.AWS_REGION,
    )
    resp = cognito.get_user(AccessToken=token)
    return {a["Name"]: a["Value"] for a in resp.get("UserAttributes", [])}


def _build_user(claims: dict, attrs: dict) -> dict:
    groups = claims.get("cognito:groups", []) or []
    name = f"{attrs.get('given_name', '')} {attrs.get('family_name', '')}".strip()
    return {
        "sub": claims.get("sub"),
        "username": claims.get("username") or attrs.get("preferred_username"),
        "email": attrs.get("email"),
        "name": name or attrs.get("name"),
        "client_id": attrs.get("custom:client_id"),
        "groups": groups,
        "is_admin": "Admin" in groups,
        "is_super_admin": "SuperAdmin" in groups,
    }


async def _extract_token_from_body(request: Request):
    """Read the raw token from the JSON request body (no 'Bearer' prefix)."""
    raw = await request.body()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    token = payload.get("token")
    return token if isinstance(token, str) and token else None


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """Validate a Cognito access token sent in the request body and expose the
    authenticated user details via ``request.state.user``."""

    def __init__(self, app):
        super().__init__(app)
        self._jwks_client = None
        self._issuer = None

    def _get_jwks_client(self) -> PyJWKClient:
        if self._jwks_client is None:
            region = settings.COGNITO_REGION
            user_pool_id = settings.COGNITO_USER_POOL_ID
            self._issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
            self._jwks_client = PyJWKClient(f"{self._issuer}/.well-known/jwks.json")
        return self._jwks_client

    def _validate_token(self, token: str) -> dict:
        signing_key = self._get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=self._issuer,
        )
        if claims.get("token_use") != "access":
            raise ValueError("token_use is not 'access'")
        return claims

    def _get_user(self, token: str, claims: dict) -> dict:
        now = time.time()
        cached = _user_cache.get(token)
        if cached and cached.get("expires_at", 0) > now:
            return cached["user"]
        try:
            attrs = _get_user_attributes_from_cognito(token)
        except Exception as exc:
            logger.warning("Could not fetch user attributes from Cognito: %s", exc)
            attrs = {}
        user = _build_user(claims, attrs)
        _user_cache[token] = {"expires_at": claims.get("exp") or (now + 300), "user": user}
        return user

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        if not (settings.COGNITO_REGION and settings.COGNITO_USER_POOL_ID):
            logger.warning("Cognito not configured - skipping auth validation")
            return await call_next(request)

        token = await _extract_token_from_body(request)
        if not token:
            return JSONResponse({"detail": "Missing or invalid token"}, status_code=401)

        try:
            claims = self._validate_token(token)
            user = self._get_user(token, claims)
        except Exception:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)

        request.state.user = user
        return await call_next(request)