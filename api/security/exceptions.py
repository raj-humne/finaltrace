class AuthError(Exception):
    """Base class for authentication/authorization failures."""


class InvalidCredentials(AuthError):
    pass


class AccountLocked(AuthError):
    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"account locked, retry after {retry_after_seconds:.0f}s")


class AccountInactive(AuthError):
    pass


class SessionInvalid(AuthError):
    pass


class InsufficientRole(AuthError):
    def __init__(self, required: str) -> None:
        self.required = required
        super().__init__(f"requires role {required}")
