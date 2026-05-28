"""Sample module exercising the mutates_state detector."""

_CACHE = {}


def store(key, value):
    global _CACHE
    _CACHE[key] = value


# Module-state mutation after the first def — the canonical signal.
SECRET = "loaded-at-import"
