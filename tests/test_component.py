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


class TestGetAllDsByFilterLuidNotFound(unittest.TestCase):
    """``_get_all_ds_by_filter`` converts a 404 ``ServerResponseError`` on a LUID lookup
    into a clear ``UserException`` instead of letting it crash as an opaque internal error.

    The Tableau REST API raises ``ServerResponseError`` (code ``404006``) rather than
    returning ``None``/empty when a configured LUID does not exist on the server. Before
    this fix, ``get_by_id`` raising propagated all the way to the entrypoint and exited 2;
    the ``_validate_ds_result`` "no result for specified LUID" message a few lines below
    was effectively dead code for this exact case since the exception never let control
    reach it.
    """

    def _component(self):
        comp = Component.__new__(Component)  # bypass __init__ (needs a live server + datadir)
        comp.server = mock.Mock()
        return comp

    def test_luid_not_found_raises_user_exception(self):
        comp = self._component()
        not_found = tsc.ServerResponseError("404006", "Resource Not Found", "Workbook could not be found.")
        comp.server.workbooks.get_by_id.side_effect = not_found

        with self.assertRaises(UserException) as ctx:
            comp._get_all_ds_by_filter("workbooks", [{"name": "wb1", "luid": "does-not-exist"}])
        self.assertIn("does-not-exist", str(ctx.exception))
        # kind ("workbooks") is singularized in the message rather than interpolated verbatim.
        self.assertIn("workbook entry", str(ctx.exception))
        self.assertNotIn("workbooks entry", str(ctx.exception))

    def test_non_404_server_response_error_still_propagates(self):
        # Guards the classification: only the "not found" family is converted; any other
        # ServerResponseError (e.g. a real server-side failure) must still surface as-is
        # rather than being masked as a configuration problem.
        comp = self._component()
        server_error = tsc.ServerResponseError("500000", "Internal Server Error", "boom")
        comp.server.datasources.get_by_id.side_effect = server_error

        with self.assertRaises(tsc.ServerResponseError):
            comp._get_all_ds_by_filter("datasources", [{"name": "ds1", "luid": "some-luid"}])

    def test_luid_found_returns_result_unchanged(self):
        # Happy path: an existing LUID is resolved exactly as before, no exception involved.
        comp = self._component()
        found = mock.Mock()
        found.name = "wb1"  # must be set post-construction: Mock(name=...) sets the repr, not the attribute
        comp.server.workbooks.get_by_id.return_value = found

        all_ds, validation_errors = comp._get_all_ds_by_filter("workbooks", [{"name": "wb1", "luid": "some-luid"}])
        self.assertEqual(all_ds, [found])
        self.assertEqual(validation_errors, [])


class TestRefreshRefusedConversion(unittest.TestCase):
    """A Tableau 403 on the refresh trigger becomes a ``UserException`` instead of an internal error.

    Tableau answers ``workbooks.refresh`` / ``tasks.run`` with a 403 ``ServerResponseError``
    when the target does not permit the operation ("Full extract refresh operation for the
    workbook is not allowed.") or the account lacks permission to refresh it. Both are
    user-fixable, but the error previously propagated uncaught to the entrypoint and exited 2
    (opaque internal error, pages the team) instead of 1 (clear user error).

    The conversion happens only in the branch that was already about to fail — the
    ``continue_on_error`` path and every non-403 error are re-raised exactly as before.
    """

    @staticmethod
    def _refresh_refused(kind="workbook"):
        return tsc.ServerResponseError(
            "403069", "Forbidden", f"Full extract refresh operation for the {kind} is not allowed."
        )

    def _component(self, **cfg):
        comp = Component.__new__(Component)  # bypass __init__ (needs a live server + datadir)
        comp.cfg_params = {"datasources": [], "workbooks": [], **cfg}
        comp.auth = mock.Mock()
        comp.server = mock.MagicMock()  # MagicMock: sign_in() is used as a context manager
        return comp

    def _with_one_workbook(self, comp):
        workbook = mock.Mock()
        workbook.name = "wb1"  # must be set post-construction: Mock(name=...) sets the repr
        comp._get_all_ds_by_filter = mock.Mock(return_value=([workbook], []))
        return workbook

    def test_workbook_refresh_refused_raises_user_exception(self):
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_one_workbook(comp)
        comp.server.workbooks.refresh.side_effect = self._refresh_refused("workbook")

        with self.assertRaises(UserException) as ctx:
            comp.run()
        message = str(ctx.exception)
        self.assertIn('workbook "wb1"', message)
        self.assertIn("Full extract refresh operation for the workbook is not allowed.", message)

    def test_datasource_refresh_refused_raises_user_exception(self):
        comp = self._component(datasources=[{"name": "ds1", "type": "FullRefresh"}])
        task = mock.Mock()
        comp._get_all_ds_by_filter = mock.Mock(return_value=([mock.Mock()], []))
        comp.validate_dataset_names = mock.Mock(return_value={"ds1": "FullRefresh"})
        comp.get_all_datasource_refresh_tasks = mock.Mock(return_value=[task])
        comp.get_all_ds_for_tasks = mock.Mock(return_value={"ds1": {"fullrefresh": task}})
        comp.validate_dataset_types = mock.Mock()
        comp._run_task = mock.Mock(side_effect=self._refresh_refused("datasource"))

        with self.assertRaises(UserException) as ctx:
            comp.run()
        self.assertIn('datasource "ds1"', str(ctx.exception))

    def test_non_403_error_still_propagates_unchanged(self):
        # Guards the classification: only the 403 family is converted. Anything else must
        # still surface as its original exception (exit 2), exactly as before the fix.
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_one_workbook(comp)
        comp.server.workbooks.refresh.side_effect = tsc.ServerResponseError("500000", "Internal Server Error", "boom")

        with self.assertRaises(tsc.ServerResponseError):
            comp.run()

    def test_continue_on_error_still_swallows_the_403(self):
        # The continue_on_error branch is untouched: a 403 is still logged and skipped,
        # never converted, so configurations relying on it behave identically.
        comp = self._component(workbooks=[{"name": "wb1"}], continue_on_error=True)
        self._with_one_workbook(comp)
        comp.server.workbooks.refresh.side_effect = self._refresh_refused("workbook")

        comp.run()  # must not raise

    def test_successful_refresh_is_unaffected(self):
        # Happy path: a workbook that refreshes fine is still recorded and polled as before.
        comp = self._component(workbooks=[{"name": "wb1"}], poll_mode=True)
        self._with_one_workbook(comp)
        comp.server.workbooks.refresh.return_value = mock.Mock(id="job-1")
        comp._wait_for_finish = mock.Mock()

        comp.run()
        comp._wait_for_finish.assert_called_once_with({"wb1": "job-1"})


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
