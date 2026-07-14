"""Function timeout utility for Vercel serverless functions.

Provides a cross-platform timeout mechanism using threading.
signal.alarm is not available on Windows or Lambda-like environments,
so we use a threading.Timer approach instead.

Usage:
    from api.utils.timeout import function_timeout, FunctionTimeoutError

    # As a context manager:
    try:
        with function_timeout(seconds=9):
            # ... long-running logic ...
    except FunctionTimeoutError:
        # Return HTTP 504 timeout error
        pass

    # As a decorator:
    @with_timeout(seconds=9)
    def my_handler(request):
        # ... logic ...
        pass

Note: Vercel enforces a hard 10s timeout via vercel.json maxDuration.
      The application-level timeout (default 9s) fires slightly before
      to allow a graceful JSON error response instead of an abrupt kill.
"""

import threading
import ctypes
from functools import wraps


# Default timeout: 9 seconds (1s buffer before Vercel's 10s hard limit)
DEFAULT_TIMEOUT_SECONDS = 9


class FunctionTimeoutError(Exception):
    """Raised when a serverless function exceeds its allowed execution time."""

    def __init__(self, seconds=None):
        self.seconds = seconds
        msg = "Function execution timed out"
        if seconds is not None:
            msg = f"Function execution timed out after {seconds}s"
        super().__init__(msg)


def _raise_in_thread(thread_id, exception_type):
    """Raise an exception in a target thread using ctypes.

    This is a best-effort mechanism. It works by injecting an async exception
    into the target thread. Some blocking operations (C extensions, I/O waits)
    may not be interrupted immediately.
    """
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exception_type)
    )
    if res == 0:
        # Thread ID not found (thread may have finished)
        pass
    elif res > 1:
        # Multiple threads affected — revert
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(thread_id),
            None
        )


class function_timeout:
    """Context manager that raises FunctionTimeoutError if the block exceeds the time limit.

    Uses a background timer thread that injects an exception into the calling
    thread when the timeout expires.

    Args:
        seconds: Maximum execution time in seconds. Defaults to 9.

    Example:
        try:
            with function_timeout(9):
                result = do_expensive_work()
        except FunctionTimeoutError:
            return {"status": "error", "code": "TIMEOUT", ...}
    """

    def __init__(self, seconds=DEFAULT_TIMEOUT_SECONDS):
        self.seconds = seconds
        self._timer = None
        self._target_thread_id = None
        self._timed_out = False

    def _on_timeout(self):
        """Timer callback — inject FunctionTimeoutError into the target thread."""
        self._timed_out = True
        if self._target_thread_id is not None:
            _raise_in_thread(self._target_thread_id, FunctionTimeoutError)

    def __enter__(self):
        self._target_thread_id = threading.current_thread().ident
        self._timer = threading.Timer(self.seconds, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._timer is not None:
            self._timer.cancel()

        # If the raised exception is our timeout, let it propagate
        if exc_type is FunctionTimeoutError:
            return False

        return False


def with_timeout(seconds=DEFAULT_TIMEOUT_SECONDS):
    """Decorator that wraps a function with a timeout guard.

    If the function exceeds the specified time limit, FunctionTimeoutError is raised.

    Args:
        seconds: Maximum execution time in seconds. Defaults to 9.

    Example:
        @with_timeout(9)
        def handle_request(body):
            # ... logic ...
            return result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with function_timeout(seconds):
                return func(*args, **kwargs)
        return wrapper
    return decorator
