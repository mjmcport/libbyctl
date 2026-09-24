class LibbyCtlError(Exception):
    """Base error for user-facing failures."""


class AuthenticationError(LibbyCtlError):
    pass


class CredentialStoreError(LibbyCtlError):
    pass


class ProviderError(LibbyCtlError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class CirculationRejectedError(ProviderError):
    """A structured provider refusal that confirms the requested write was rejected."""


class ConfigurationError(LibbyCtlError):
    pass
