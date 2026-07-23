import os
import runpy
import unittest
from unittest import mock

import tableauserverclient as tsc
from freezegun import freeze_time
from keboola.component import ComponentBase, UserException

import component
from component import Component

COMPONENT_FILE = component.__file__


def _failed_sign_in_error(detail="Login failed"):
    """Build a realistic ``FailedSignInError`` as tableauserverclient raises it on an HTTP 401."""
    return tsc.FailedSignInError("401002", "Unauthorized Access", detail)


class TestComponent(unittest.TestCase):
    # set global time to 2010-10-10 - affects functions like datetime.now()
    @freeze_time("2010-10-10")
    # set KBC_DATADIR env to non-existing dir
    @mock.patch.dict(os.environ, {"KBC_DATADIR": "./non-existing-dir"})
    def test_run_no_cfg_fails(self):
        with self.assertRaises(ValueError):
            comp = Component()
            comp.run()


class TestEntrypointExitCodes(unittest.TestCase):
    """
    Exit-code contract of the ``if __name__ == "__main__":`` block.

    The component maps the failure type to a Keboola exit code:
      * ``UserException``          -> 1 (clear, user-facing failure)
      * ``tsc.FailedSignInError``  -> 1 (auth failure, surfaced as a user error)
      * anything else              -> 2 (opaque internal error)

    The ``FailedSignInError`` clause is the behaviour added in this PR: the
    Tableau library raises it for *any* API call that gets a 401 (not only the
    initial ``sign_in()``), e.g. a session expiring mid-run during the poll loop.
    Without the clause such a mid-run auth failure fell through to the generic
    handler and exited 2 (internal error) instead of 1 (user error).

    The mapping lives in the module-level ``__main__`` guard, so the block is
    exercised by re-executing the module with ``runpy`` under ``run_name``
    ``"__main__"``. The failure is injected by patching the base class ``__init__``
    so ``Component()`` raises the exception under test; the entrypoint wraps both
    ``Component()`` and ``comp.execute_action()`` in the same ``try``, so the
    origin of the exception does not change which clause catches it.
    """

    @staticmethod
    def _run_entrypoint_raising(exc):
        """Re-run the module entrypoint with ``Component()`` raising ``exc``; return the exit code."""
        with mock.patch.object(ComponentBase, "__init__", side_effect=exc):
            try:
                runpy.run_path(COMPONENT_FILE, run_name="__main__")
            except SystemExit as system_exit:
                return system_exit.code
        return None

    def test_failed_sign_in_error_exits_1(self):
        # The fix under test: FailedSignInError from anywhere -> user error (exit 1), not internal error (exit 2).
        exit_code = self._run_entrypoint_raising(_failed_sign_in_error("session token expired mid-run"))
        self.assertEqual(exit_code, 1)

    def test_user_exception_exits_1(self):
        exit_code = self._run_entrypoint_raising(UserException("bad configuration"))
        self.assertEqual(exit_code, 1)

    def test_generic_exception_exits_2(self):
        # Guards the clause ordering: a non-auth error must still fall through to the generic exit-2 handler.
        exit_code = self._run_entrypoint_raising(ValueError("unexpected internal error"))
        self.assertEqual(exit_code, 2)


class TestSignInErrorConversion(unittest.TestCase):
    """``run()`` converts an initial sign-in ``FailedSignInError`` into a ``UserException``.

    This is the precedent the entrypoint clause mirrors (referenced in its comment):
    the initial ``sign_in()`` failure is turned into a clear auth ``UserException``.
    """

    def test_run_converts_failed_sign_in_to_user_exception(self):
        comp = Component.__new__(Component)  # bypass __init__ (needs a live server + datadir)
        comp.cfg_params = {}
        comp.auth = mock.Mock()
        comp.server = mock.Mock()
        comp.server.auth.sign_in.side_effect = _failed_sign_in_error("invalid credentials")

        with self.assertRaises(UserException) as ctx:
            comp.run()
        self.assertIn("Tableau authentication failed", str(ctx.exception))


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
