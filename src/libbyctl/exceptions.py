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


class ConfigurationError(LibbyCtlError):
    pass
