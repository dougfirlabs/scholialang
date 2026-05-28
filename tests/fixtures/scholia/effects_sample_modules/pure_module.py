"""Sample module — pure helper with no side effects."""


def add(a, b):
    return a + b


def multiply(a, b):
    return a * b


class Pair:
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def swap(self):
        # Local mutation only — not module state.
        self.left, self.right = self.right, self.left
        return self
