"""Stable application errors; adapters decide how to encode them."""


class BoxieError(Exception):
    """An application failure with an explicitly client-safe detail."""

    def __init__(self, status: int, public_detail: str) -> None:
        super().__init__(public_detail)
        self.status = status
        self.public_detail = public_detail


class TerminalWriteClosed(BoxieError):
    """The upstream closed normally; its final response may still be buffered."""

    def __init__(self) -> None:
        super().__init__(503, "terminal upstream closed")
