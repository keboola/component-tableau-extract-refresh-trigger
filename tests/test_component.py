import os
import runpy
import unittest
from unittest import mock

import requests
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


class TestRefreshAlreadyQueuedWarning(unittest.TestCase):
    """With ``already_in_queue_as_warning`` on, an already-queued refresh warns and the run succeeds.

    Tableau answers ``tasks.run`` / ``workbooks.refresh`` with a 409 ``ServerResponseError``
    ("Resource Conflict" / "Job for '...' is already queued. Not queuing a duplicate.") when a
    refresh for the same target is still queued or running. Nothing is broken in that case — the
    extract is being refreshed by the run already in flight — so a configuration can opt into
    treating it as a warning (CFTL-371 / SUPPORT-12519) rather than reaching for
    ``continue_on_error``, which suppresses genuine errors too.

    Every case here enables the option; ``TestAlreadyQueuedWithoutOptIn`` covers the default.

    The classification stays narrow. Only *this* conflict is downgraded — recognised by error
    code, or by Tableau's own wording when a deployment reports it under a different code. Any
    other 409 still fails the job as the ``UserException`` merged in #21, a 403 is still a
    ``UserException`` (see ``TestRefreshRefusedConversion``), and everything else still propagates
    untouched. That boundary is what keeps a job from going green when nothing was refreshed.
    """

    @staticmethod
    def _already_queued(name="<name>"):
        # 409093 is the code the observed failure carried, with this exact summary/detail.
        return tsc.ServerResponseError(
            "409093", "Resource Conflict", f"Job for '{name}' is already queued. Not queuing a duplicate."
        )

    def _component(self, **cfg):
        comp = Component.__new__(Component)  # bypass __init__ (needs a live server + datadir)
        # The behaviour under test is opt-in, so it is switched on for every case in this class.
        comp.cfg_params = {"datasources": [], "workbooks": [], "already_in_queue_as_warning": True, **cfg}
        comp.auth = mock.Mock()
        comp.server = mock.MagicMock()  # MagicMock: sign_in() is used as a context manager
        comp._wait_for_finish = mock.Mock()
        return comp

    @staticmethod
    def _with_workbooks(comp, *names):
        workbooks = []
        for name in names:
            workbook = mock.Mock()
            workbook.name = name  # must be set post-construction: Mock(name=...) sets the repr
            workbooks.append(workbook)
        comp._get_all_ds_by_filter = mock.Mock(return_value=(workbooks, []))
        return workbooks

    @staticmethod
    def _with_one_datasource(comp, side_effect):
        task = mock.Mock()
        comp._get_all_ds_by_filter = mock.Mock(return_value=([mock.Mock()], []))
        comp.validate_dataset_names = mock.Mock(return_value={"ds1": "FullRefresh"})
        comp.get_all_datasource_refresh_tasks = mock.Mock(return_value=[task])
        comp.get_all_ds_for_tasks = mock.Mock(return_value={"ds1": {"fullrefresh": task}})
        comp.validate_dataset_types = mock.Mock()
        comp._run_task = mock.Mock(side_effect=side_effect)

    def test_datasource_already_queued_warns_instead_of_failing(self):
        # The fix under test, on the path the customer hit: tasks.run() rejected as a duplicate.
        comp = self._component(datasources=[{"name": "ds1", "type": "FullRefresh"}])
        self._with_one_datasource(comp, self._already_queued("ds1"))

        with self.assertLogs(level="WARNING") as logs:
            comp.run()  # must not raise

        warning = "\n".join(logs.output)
        self.assertIn('datasource "ds1"', warning)
        self.assertIn("already queued or running in Tableau", warning)
        # Tableau's own detail is passed through, so the log still states the actual cause.
        self.assertIn("Job for 'ds1' is already queued. Not queuing a duplicate.", warning)

    def test_workbook_already_queued_warns_instead_of_failing(self):
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = self._already_queued("wb1")

        with self.assertLogs(level="WARNING") as logs:
            comp.run()  # must not raise

        self.assertIn('workbook "wb1"', "\n".join(logs.output))

    def test_remaining_targets_are_still_refreshed(self):
        # "Continue execution" means the rest of the list is not skipped: the second workbook is
        # still triggered, and it is the only one recorded for polling.
        comp = self._component(workbooks=[{"name": "wb1"}, {"name": "wb2"}], poll_mode=1)
        self._with_workbooks(comp, "wb1", "wb2")
        comp.server.workbooks.refresh.side_effect = [self._already_queued("wb1"), mock.Mock(id="job-2")]

        with self.assertLogs(level="WARNING"):
            comp.run()

        self.assertEqual(comp.server.workbooks.refresh.call_count, 2)
        comp._wait_for_finish.assert_called_once_with({"wb2": "job-2"})

    def test_already_queued_refresh_is_not_polled(self):
        # A 409 carries no job id, so there is nothing to poll: the run must not invent one, and
        # must not wait for the refresh Tableau is already running.
        comp = self._component(workbooks=[{"name": "wb1"}], poll_mode=1)
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = self._already_queued("wb1")

        with self.assertLogs(level="WARNING") as logs:
            comp.run()

        comp._wait_for_finish.assert_called_once_with({})
        # In poll mode the warning says so, so the user is not left assuming the run waited for it.
        self.assertIn("does not wait", "\n".join(logs.output))

    def test_warning_omits_the_polling_note_when_not_polling(self):
        # Without poll mode the run never waits for anything, so the note would be noise.
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = self._already_queued("wb1")

        with self.assertLogs(level="WARNING") as logs:
            comp.run()

        self.assertNotIn("does not wait", "\n".join(logs.output))

    def test_continue_on_error_configurations_behave_the_same(self):
        # Configurations that switched continue_on_error on as a workaround keep working: the 409
        # is warned about and skipped, exactly as it now is without the flag.
        comp = self._component(workbooks=[{"name": "wb1"}], continue_on_error=True)
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = self._already_queued("wb1")

        with self.assertLogs(level="WARNING"):
            comp.run()  # must not raise

    def test_skipped_refreshes_are_summarised(self):
        # The aggregate line: N individual warnings followed by "Trigger finished successfully!"
        # otherwise reads the same as a run where everything refreshed.
        comp = self._component(workbooks=[{"name": "wb1"}, {"name": "wb2"}])
        self._with_workbooks(comp, "wb1", "wb2")
        comp.server.workbooks.refresh.side_effect = [self._already_queued("wb1"), mock.Mock(id="job-2")]

        with self.assertLogs(level="INFO") as logs:
            comp.run()

        self.assertIn("1 of 2 refreshes were already queued", "\n".join(logs.output))

    def test_no_summary_line_when_nothing_was_skipped(self):
        # A clean run's log is unchanged — the summary only appears when something was skipped.
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.return_value = mock.Mock(id="job-1")

        with self.assertLogs(level="INFO") as logs:
            comp.run()

        self.assertNotIn("were already queued or running", "\n".join(logs.output))

    def test_unrecognised_409_conflict_still_fails_the_job(self):
        # The point of matching narrowly: a conflict that is *not* "already queued" must keep
        # failing the job (as the UserException merged in #21), never be downgraded to a warning
        # that leaves the job green with nothing refreshed.
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = tsc.ServerResponseError(
            "409999", "Resource Conflict", "Some other conflict we have never seen."
        )

        with self.assertRaises(UserException) as ctx:
            comp.run()
        message = str(ctx.exception)
        self.assertIn('workbook "wb1"', message)
        self.assertIn("Some other conflict we have never seen.", message)

    def test_already_queued_under_another_code_is_still_recognised(self):
        # The wording fallback: the sub-code for this condition differs between Tableau versions
        # and deployments, so Tableau's own message is trusted when the code is unfamiliar.
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = tsc.ServerResponseError(
            "409042", "Resource Conflict", "Job for 'wb1' is already queued. Not queuing a duplicate."
        )

        with self.assertLogs(level="WARNING") as logs:
            comp.run()  # must not raise

        self.assertIn("already queued or running in Tableau", "\n".join(logs.output))

    def test_refresh_already_in_progress_wording_is_recognised(self):
        # The other wording Tableau uses for the same situation.
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = tsc.ServerResponseError(
            "409080", "Resource Conflict", "An extract refresh for this workbook is already in progress."
        )

        with self.assertLogs(level="WARNING") as logs:
            comp.run()  # must not raise

        self.assertIn("already queued or running in Tableau", "\n".join(logs.output))

    def test_other_4xx_conflict_family_still_fails_the_job(self):
        # Guards the outer boundary: outside the 409 family nothing is reclassified at all. A 4xx
        # from another family (e.g. 400 bad request) must still surface as its original exception
        # and exit 2, exactly as before.
        comp = self._component(workbooks=[{"name": "wb1"}])
        self._with_workbooks(comp, "wb1")
        comp.server.workbooks.refresh.side_effect = tsc.ServerResponseError("400006", "Bad Request", "nope")

        with self.assertRaises(tsc.ServerResponseError):
            comp.run()


class TestAlreadyQueuedWithoutOptIn(unittest.TestCase):
    """Without ``already_in_queue_as_warning``, an already-queued refresh still fails the job.

    The warning behaviour is opt-in and off by default, so a configuration that does not ask for it
    behaves exactly as it did before the option existed: the 409 becomes the ``UserException``
    merged in #21 — a clear exit 1, never an opaque exit 2 — no job is recorded for polling, and
    the run stops. This is the backward-compatibility half of ``TestRefreshAlreadyQueuedWarning``.
    """

    @staticmethod
    def _already_queued(name="<name>"):
        return tsc.ServerResponseError(
            "409093", "Resource Conflict", f"Job for '{name}' is already queued. Not queuing a duplicate."
        )

    def _component(self, **cfg):
        comp = Component.__new__(Component)  # bypass __init__ (needs a live server + datadir)
        comp.cfg_params = {"datasources": [], "workbooks": [], **cfg}  # option absent -> default off
        comp.auth = mock.Mock()
        comp.server = mock.MagicMock()  # MagicMock: sign_in() is used as a context manager
        comp._wait_for_finish = mock.Mock()
        return comp

    def _with_one_workbook(self, comp):
        workbook = mock.Mock()
        workbook.name = "wb1"  # must be set post-construction: Mock(name=...) sets the repr
        comp._get_all_ds_by_filter = mock.Mock(return_value=([workbook], []))
        return workbook

    def test_workbook_already_queued_fails_the_job_by_default(self):
        comp = self._component(workbooks=[{"name": "wb1"}], poll_mode=1)
        self._with_one_workbook(comp)
        comp.server.workbooks.refresh.side_effect = self._already_queued("wb1")

        with self.assertRaises(UserException) as ctx:
            comp.run()
        message = str(ctx.exception)
        self.assertIn('workbook "wb1"', message)
        self.assertIn("refused to queue the extract refresh", message)
        comp._wait_for_finish.assert_not_called()  # nothing queued, so nothing to poll

    def test_datasource_already_queued_fails_the_job_by_default(self):
        comp = self._component(datasources=[{"name": "ds1", "type": "FullRefresh"}])
        task = mock.Mock()
        comp._get_all_ds_by_filter = mock.Mock(return_value=([mock.Mock()], []))
        comp.validate_dataset_names = mock.Mock(return_value={"ds1": "FullRefresh"})
        comp.get_all_datasource_refresh_tasks = mock.Mock(return_value=[task])
        comp.get_all_ds_for_tasks = mock.Mock(return_value={"ds1": {"fullrefresh": task}})
        comp.validate_dataset_types = mock.Mock()
        comp._run_task = mock.Mock(side_effect=self._already_queued("ds1"))

        with self.assertRaises(UserException) as ctx:
            comp.run()
        message = str(ctx.exception)
        self.assertIn('datasource "ds1"', message)
        # #21's message shape: Tableau's own detail is appended verbatim, and last.
        self.assertTrue(message.endswith("is already queued. Not queuing a duplicate."), message)

    def test_option_explicitly_false_behaves_the_same(self):
        comp = self._component(workbooks=[{"name": "wb1"}], already_in_queue_as_warning=False)
        self._with_one_workbook(comp)
        comp.server.workbooks.refresh.side_effect = self._already_queued("wb1")

        with self.assertRaises(UserException):
            comp.run()

    def test_continue_on_error_still_skips_it(self):
        # continue_on_error is untouched by the new option: it swallows this like any other error.
        comp = self._component(workbooks=[{"name": "wb1"}], continue_on_error=True)
        self._with_one_workbook(comp)
        comp.server.workbooks.refresh.side_effect = self._already_queued("wb1")

        with self.assertLogs(level="WARNING"):
            comp.run()  # must not raise


class TestConnectToServer(unittest.TestCase):
    """``_connect_to_server`` retries a refused connection and then raises a ``UserException``.

    The first thing the component does is call the Tableau Server's ``/serverInfo`` endpoint
    (from ``tsc.Server(..., use_server_version=True)`` and from ``server_info.get()``). When the
    server refused the connection, the ``requests.exceptions.ConnectionError`` propagated
    uncaught to the entrypoint and exited 2 (opaque internal error). It is now retried a few
    times and then surfaced as a ``UserException`` (exit 1), which is what an unreachable
    endpoint actually is: user-fixable.

    Only the failing path changed — the first-attempt-succeeds case must behave exactly as the
    previous inline code did.
    """

    def setUp(self):
        self.comp = Component.__new__(Component)  # bypass __init__ (needs a live server + datadir)
        # Keep the suite fast: the retry backoff is real time we do not need to spend.
        patcher = mock.patch.object(component.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _server_mock():
        server = mock.Mock()
        server.server_info.get.return_value = mock.Mock()
        return server

    def test_first_attempt_success_is_unchanged(self):
        # Happy path: one construction, one server_info.get(), no sleeping, values returned as before.
        server = self._server_mock()
        with mock.patch.object(component.tsc, "Server", return_value=server) as server_cls:
            returned_server, returned_info = self.comp._connect_to_server("https://tableau.example", True, "3.20")

        self.assertIs(returned_server, server)
        self.assertIs(returned_info, server.server_info.get.return_value)
        server_cls.assert_called_once_with("https://tableau.example", use_server_version=True)
        self.sleep.assert_not_called()

    def test_explicit_api_version_is_still_applied(self):
        # Guards the behaviour moved out of __init__: an explicit api_version is set on the server.
        server = self._server_mock()
        with mock.patch.object(component.tsc, "Server", return_value=server):
            self.comp._connect_to_server("https://tableau.example", False, "3.20")

        self.assertEqual(server.version, "3.20")

    def test_connection_error_is_retried_then_succeeds(self):
        # A server that is briefly unreachable no longer fails the job.
        server = self._server_mock()
        side_effects = [requests.exceptions.ConnectionError("Connection refused"), server]
        with mock.patch.object(component.tsc, "Server", side_effect=side_effects) as server_cls:
            returned_server, _ = self.comp._connect_to_server("https://tableau.example", True, "3.20")

        self.assertIs(returned_server, server)
        self.assertEqual(server_cls.call_count, 2)
        self.sleep.assert_called_once()

    def test_persistent_connection_error_raises_user_exception(self):
        # The fix under test: a genuinely unreachable server is a user error (exit 1), not exit 2.
        refused = requests.exceptions.ConnectionError("[Errno 111] Connection refused")
        with mock.patch.object(component.tsc, "Server", side_effect=refused) as server_cls:
            with self.assertRaises(UserException) as ctx:
                self.comp._connect_to_server("https://tableau.example", True, "3.20")

        self.assertEqual(server_cls.call_count, component.CONNECT_MAX_ATTEMPTS)
        message = str(ctx.exception)
        self.assertIn("Could not connect to the Tableau Server", message)
        self.assertIn("https://tableau.example", message)

    def test_connection_error_from_server_info_is_also_handled(self):
        # The /serverInfo call is reached from two places; both must be covered.
        server = self._server_mock()
        server.server_info.get.side_effect = requests.exceptions.ConnectionError("Connection refused")
        with mock.patch.object(component.tsc, "Server", return_value=server):
            with self.assertRaises(UserException):
                self.comp._connect_to_server("https://tableau.example", True, "3.20")

    def test_non_connection_error_still_propagates_unchanged(self):
        # Guards the classification: only connection failures are converted. Anything else
        # (e.g. an auth or protocol error) must surface as before and still exit 2.
        with mock.patch.object(component.tsc, "Server", side_effect=ValueError("bad endpoint")) as server_cls:
            with self.assertRaises(ValueError):
                self.comp._connect_to_server("https://tableau.example", True, "3.20")

        server_cls.assert_called_once()  # not retried
        self.sleep.assert_not_called()


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
