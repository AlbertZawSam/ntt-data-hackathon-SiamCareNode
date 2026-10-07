"""Expected application failures that transports can present without tracebacks."""


class ApplicationError(Exception):
    """An expected failure; programming errors should still propagate."""


class NotFoundError(ApplicationError, LookupError):
    pass


class InvalidInputError(ApplicationError, ValueError):
    pass


class TransitionError(ApplicationError):
    pass


class ActorPermissionError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    """A concurrent operation changed the referral; reload before retrying."""


class PersistenceError(ApplicationError):
    pass
