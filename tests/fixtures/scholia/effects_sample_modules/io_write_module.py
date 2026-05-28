"""Sample module exercising the io_write detector."""
from pathlib import Path


def dump(path, payload):
    with open(path, "w") as fh:
        fh.write(payload)


def dump_via_path(p):
    Path(p).write_text("hello")
