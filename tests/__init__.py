"""Test support shared by all supported Python versions."""

from contextlib import ExitStack
import unittest


class TestCase(unittest.TestCase):
    def enterContext(self, context):
        """Match unittest's Python 3.11 helper on Python 3.10 too."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        return stack.enter_context(context)
