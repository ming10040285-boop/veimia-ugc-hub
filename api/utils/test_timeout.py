"""Unit tests for the timeout utility module."""

import sys
import os
import time
import unittest

# Ensure imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.timeout import function_timeout, FunctionTimeoutError, with_timeout


class TestFunctionTimeoutError(unittest.TestCase):
    """Tests for FunctionTimeoutError exception class."""

    def test_error_message_with_seconds(self):
        err = FunctionTimeoutError(seconds=9)
        assert "9s" in str(err)
        assert err.seconds == 9

    def test_error_message_without_seconds(self):
        err = FunctionTimeoutError()
        assert "timed out" in str(err)
        assert err.seconds is None


class TestFunctionTimeoutContextManager(unittest.TestCase):
    """Tests for function_timeout context manager."""

    def test_fast_code_completes_normally(self):
        """Code that finishes before timeout should work normally."""
        result = None
        with function_timeout(seconds=2):
            result = 42
        assert result == 42

    def test_timeout_raises_error(self):
        """Code that exceeds timeout should raise FunctionTimeoutError."""
        with self.assertRaises(FunctionTimeoutError):
            with function_timeout(seconds=1):
                time.sleep(3)

    def test_timer_cancelled_on_normal_exit(self):
        """Timer should be cancelled when code completes normally."""
        ctx = function_timeout(seconds=5)
        with ctx:
            pass
        # Timer should have been cancelled
        assert ctx._timer is not None
        assert not ctx._timer.is_alive()


class TestWithTimeoutDecorator(unittest.TestCase):
    """Tests for with_timeout decorator."""

    def test_decorated_function_completes_normally(self):
        """Decorated function that finishes in time should return normally."""
        @with_timeout(seconds=2)
        def fast_func():
            return "done"

        assert fast_func() == "done"

    def test_decorated_function_timeout(self):
        """Decorated function that exceeds timeout should raise."""
        @with_timeout(seconds=1)
        def slow_func():
            time.sleep(3)
            return "never"

        with self.assertRaises(FunctionTimeoutError):
            slow_func()


if __name__ == "__main__":
    unittest.main()
