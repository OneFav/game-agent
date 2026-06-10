class GameAgentError(Exception):
    """Base exception for user-facing Game Agent errors."""


class ContractError(GameAgentError):
    """Raised when a generated package violates an interface contract."""


class InputError(GameAgentError):
    """Raised when user input cannot be compiled safely."""
