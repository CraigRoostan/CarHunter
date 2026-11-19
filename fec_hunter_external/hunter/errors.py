"""Errors shared by sources, the browser layer and the scheduler.

`SourceUnavailable` means this cycle cannot use the source (missing credentials, an
upstream hiccup). `SourceBlocked` means the site refused automated access: the source is
put on cooldown and must not be retried in a loop.
"""


class SourceUnavailable(Exception):
    """The source cannot be used right now. The message is shown to the operator."""


class SourceBlocked(Exception):
    """The site refused automated access. Retrying would be circumvention."""