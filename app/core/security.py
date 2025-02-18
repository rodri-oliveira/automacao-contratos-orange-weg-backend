from typing import Optional
from fastapi import HTTPException, status

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import SecurityScopes, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

class TokenData():
    def __init__(self, name: str, email: str, roles: list[str]) -> None:
        self.name = name
        self.email = email
        self.roles = roles


class ForbidenException(HTTPException):
    def __init__(self, detail: str, **kwargs):
        super().__init__(status.HTTP_403_FORBIDDEN, detail=detail)

class UnauthorizedException(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=detail
        )

class VerifyToken:
    def __init__(self):
        jwks_url = f"{settings.jwt_issuer}/protocol/openid-connect/certs"
        self.jwks_client = jwt.PyJWKClient(jwks_url)

    async def verify(self, security_scopes: SecurityScopes, token: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> TokenData:
        if token is None:
            raise UnauthorizedException("Missing Bearer token")

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token.credentials).key
        except jwt.exceptions.DecodeError as error:
            raise UnauthorizedException(str(error))
        except Exception as error:
            print(str(error))
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to check token")

        try:
            payload = jwt.decode(
                token.credentials,
                signing_key,
                algorithms=["RS256"],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )
        except Exception as error:
            raise UnauthorizedException(str(error))

        user_roles: list[str] = []
        resource_access = payload.get("resource_access")
        token_name = payload.get("name")
        token_email = payload.get("email")

        if resource_access is not None:
            audience_acess = resource_access.get(settings.jwt_audience)
            if audience_acess is not None:
                token_roles = audience_acess.get("roles")
                if token_roles is not None:
                    user_roles = token_roles

        if set(security_scopes.scopes).issubset(set(user_roles)):
            return TokenData(name=token_name, roles=user_roles, email=token_email)

        raise ForbidenException("Role missing from token")

auth = VerifyToken()
