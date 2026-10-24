class SetupError(Exception):
    """Only stable reason codes and known non-secret metadata cross the CLI boundary."""

    def __init__(self, reason, **details):
        super().__init__(reason)
        self.reason = reason
        self.details = details
