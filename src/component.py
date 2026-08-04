"""
Template Component main class.

"""

import logging
import os
import time

import requests
import tableauserverclient as tsc
import xmltodict
from keboola.component import ComponentBase, UserException

# configuration variables
from tableau_custom.endpoints.tasks_endpoint import TaskCustom

# global constants

KEY_TAG = "tag"
KEY_NAME = "name"
KEY_LUID = "luid"
KEY_API_PASS = "#password"
KEY_TOKEN_NAME = "token_name"
KEY_TOKEN = "#token_secret"
KEY_USER_NAME = "user"
KEY_ENDPOINT = "endpoint"
KEY_POLL_MODE = "poll_mode"
KEY_DS_NAME = "name"
KEY_DS_TYPE = "type"
KEY_DATASOURCES = "datasources"
KEY_WORKBOOKS = "workbooks"
KEY_SITE_ID = "site_id"
KEY_CONTINUE_ON_ERROR = "continue_on_error"

KEY_AUTH_TYPE = "authentication_type"
AUTH_NAMES = [KEY_USER_NAME, KEY_TOKEN_NAME]
AUTH_SECRETS = [KEY_API_PASS, KEY_TOKEN]
MANDATORY_PARS = [AUTH_NAMES, AUTH_SECRETS, KEY_DATASOURCES, KEY_ENDPOINT]

KEY_LUID_REQUIRED = "luid_required"
KEY_POLL_MODE_DISABLED = "poll_mode_disabled"

APP_VERSION = "0.0.1"

# Bounded retry for the very first network call to the Tableau Server (see _connect_to_server).
CONNECT_MAX_ATTEMPTS = 3
CONNECT_RETRY_BACKOFF_SECONDS = 2

logger = logging.getLogger("tableau.endpoint.tasks")


class Component(ComponentBase):
    def __init__(self):
        super().__init__(required_parameters=MANDATORY_PARS)
        self.cfg_params = self.configuration.parameters
        self.image_params = self.configuration.image_parameters

        log_level = logging.DEBUG if self.cfg_params.get("debug") else logging.INFO
        # setup GELF if available
        if os.getenv("KBC_LOGGER_ADDR", None):
            self.set_gelf_logger(log_level)
        else:
            self.set_default_logger(log_level)
        logging.info("Running version %s", APP_VERSION)
        logging.info("Loading configuration...")

        if not self.cfg_params.get("debug"):
            # suppress info logging on the Tableau endpoints
            logging.getLogger("tableau.endpoint.jobs").setLevel(logging.ERROR)
            logging.getLogger("tableau.endpoint.datasources").setLevel(logging.ERROR)

        site_id = self.cfg_params.get(KEY_SITE_ID) or ""
        # intialize instance parameteres

        # If 'luid_required' is set to true, the component will validate that the LUID and Name
        # is present for all datasources and workbooks
        luid_required = self.image_params.get(KEY_LUID_REQUIRED, False)
        if luid_required:
            for ds in self.cfg_params[KEY_DATASOURCES]:
                self._validate_required(ds.get(KEY_NAME), "Name")
                self._validate_required(ds.get(KEY_LUID), "LUID")
            for wb in (self.cfg_params.get(KEY_WORKBOOKS) or []):
                self._validate_required(wb.get(KEY_NAME), "Name")
                self._validate_required(wb.get(KEY_LUID), "LUID")

        # If 'poll_mode_disabled' is set to true, the component will not poll the job statuses
        poll_mode_disabled = self.image_params.get(KEY_POLL_MODE_DISABLED, False)
        if poll_mode_disabled:
            if self.cfg_params.get(KEY_POLL_MODE):
                raise UserException("Poll must be set to false.")

        if self.cfg_params.get(KEY_AUTH_TYPE, "user/password") == "user/password":
            self.auth = tsc.TableauAuth(self.cfg_params[KEY_USER_NAME], self.cfg_params[KEY_API_PASS], site_id=site_id)
        elif self.cfg_params.get(KEY_AUTH_TYPE) == "Personal Access Token":
            self.auth = tsc.PersonalAccessTokenAuth(
                token_name=self.cfg_params[KEY_TOKEN_NAME],
                personal_access_token=self.cfg_params[KEY_TOKEN],
                site_id=site_id,
            )
        api_version = self.cfg_params.get("api_version", "use_server_version")
        if api_version == "use_server_version":
            user_server_version = True
        else:
            user_server_version = False
        logging.debug(f"use server:{user_server_version}, api: {api_version}")
        self.server, self.server_info = self._connect_to_server(
            self.cfg_params[KEY_ENDPOINT], user_server_version, api_version
        )
        logging.info(f"Using API version: {self.server.version}")

    @staticmethod
    def _connect_to_server(
        endpoint: str, use_server_version: bool, api_version: str
    ) -> tuple[tsc.Server, tsc.ServerInfoItem]:
        """Open the first connection to the Tableau Server, retrying a refused/dropped one.

        This is the component's first network call: both ``tsc.Server(..., use_server_version=True)``
        and ``server_info.get()`` hit the server's ``/serverInfo`` endpoint. When the server was
        unreachable, the resulting ``requests.exceptions.ConnectionError`` propagated uncaught to
        the entrypoint and exited 2 (opaque internal error, pages the team) with nothing the user
        could act on.

        It is now retried a few times so a server that is briefly restarting no longer fails the
        job, and a genuinely unreachable one is surfaced as a ``UserException`` (exit 1) — an
        endpoint that refuses connections is user-fixable (server down, wrong endpoint in the
        configuration, or Keboola not permitted through the firewall), not a component bug.

        The successful path is unchanged: the first attempt returns exactly what the previous
        inline code produced.
        """
        for attempt in range(1, CONNECT_MAX_ATTEMPTS + 1):
            try:
                server = tsc.Server(endpoint, use_server_version=use_server_version)
                if not use_server_version:
                    server.version = api_version
                return server, server.server_info.get()
            except requests.exceptions.ConnectionError as ex:
                if attempt == CONNECT_MAX_ATTEMPTS:
                    raise UserException(
                        f"Could not connect to the Tableau Server at '{endpoint}' after "
                        f"{CONNECT_MAX_ATTEMPTS} attempts: {ex}. Check that the server is running, "
                        f"that the endpoint in the configuration is correct, and that the server is "
                        f"reachable from Keboola (firewall / IP allowlist)."
                    ) from ex
                delay = CONNECT_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1)
                logging.warning(
                    f"Could not connect to the Tableau Server "
                    f"(attempt {attempt}/{CONNECT_MAX_ATTEMPTS}), retrying in {delay}s: {ex}"
                )
                time.sleep(delay)

    def run(self):
        """
        Main execution code
        """
        params = self.cfg_params  # noqa
        continue_on_error = params.get(KEY_CONTINUE_ON_ERROR, False)

        try:
            sign_in_ctx = self.server.auth.sign_in(self.auth)
        except tsc.FailedSignInError as ex:
            raise UserException(f"Tableau authentication failed: {ex}") from ex

        with sign_in_ctx:
            executed_jobs = dict()

            data_sources = params[KEY_DATASOURCES]
            if data_sources:
                # tasks
                # filter only datasource refresh tasks
                logging.info("Validating extract names...")

                all_ds, validation_errors = self._get_all_ds_by_filter("datasources", data_sources)
                logging.debug(f"Recognized datasets: {all_ds}")

                if validation_errors:
                    raise UserException("\n".join(validation_errors))
                ds_to_refresh = self.validate_dataset_names(all_ds, data_sources)

                tasks = self.get_all_datasource_refresh_tasks()
                # get all datasources for tasks
                logging.info("Retrieving extract tasks and validating extract types...")
                ds_tasks = self.get_all_ds_for_tasks(tasks, all_ds)
                logging.debug(f"Found datasource tasks: {ds_tasks}")
                self.validate_dataset_types(ds_tasks, ds_to_refresh)

                for ds in data_sources:
                    task = ds_tasks[ds[KEY_DS_NAME]][ds[KEY_DS_TYPE].lower()]
                    logging.info(f'Triggering extract for: "{ds[KEY_DS_NAME]}" with LUID: "{task.target.id}""')
                    try:
                        job_id = self._run_task(task)
                        executed_jobs[ds[KEY_DS_NAME]] = job_id
                    except Exception as ex:
                        if continue_on_error:
                            logging.warning(f"Failed to trigger extract for dataset: {ds[KEY_DS_NAME]}. {ex}")
                        else:
                            user_error = self._as_refresh_refused_user_exception(ex, "datasource", ds[KEY_DS_NAME])
                            if user_error:
                                raise user_error from ex
                            raise ex

            workbooks = params.get(KEY_WORKBOOKS, False)
            if workbooks:
                all_wb, validation_errors = self._get_all_ds_by_filter("workbooks", workbooks)
                for wb in all_wb:
                    logging.info(f'Triggering extract for: "{wb.name}" with LUID: "{wb.id}""')
                    try:
                        job = self.server.workbooks.refresh(wb)
                        executed_jobs[wb.name] = job.id
                    except Exception as ex:
                        if continue_on_error:
                            logging.warning(f"Failed to trigger extract for workbook: {wb.name}. {ex}")
                        else:
                            user_error = self._as_refresh_refused_user_exception(ex, "workbook", wb.name)
                            if user_error:
                                raise user_error from ex
                            raise ex

            # poll job statuses
            if params.get(KEY_POLL_MODE):
                logging.info("Polling extract refresh statuses.")
                self._wait_for_finish(executed_jobs)

        logging.info("Trigger finished successfully!")

    def _validate_required(self, value: str, field_name: str) -> None:
        if not value or value == "":
            raise UserException(f"{field_name} is required.")

    @staticmethod
    def _as_refresh_refused_user_exception(ex: Exception, kind_singular: str, name: str):
        """Return a ``UserException`` if ``ex`` is Tableau refusing the refresh, else ``None``.

        Tableau answers a refresh trigger with a ``ServerResponseError`` in two user-fixable
        situations:

        * **403** — the target itself does not permit the operation (e.g. "Full extract
          refresh operation for the workbook is not allowed.") or the configured account
          lacks the permission to refresh it.
        * **409** (observed as ``409093`` "Resource Conflict" / "Job for '...' is already
          queued. Not queuing a duplicate.") — a refresh for the same target is still queued
          or running, so the trigger fired again before the previous refresh finished.

        Both are fixed by the user, but they previously propagated uncaught to the
        entrypoint as an opaque internal error (exit 2). Converting only these families
        mirrors the 404 conversion in ``_get_all_ds_by_filter``; the caller re-raises
        everything else untouched.

        Note the 409 is *converted, not swallowed*: the job still fails, only now as a
        clear exit-1 user error instead of an exit-2 internal one. Treating an already
        queued refresh as a success would change what the component reports, which is
        explicitly not what this does.
        """
        if not isinstance(ex, tsc.ServerResponseError):
            return None
        # str(ServerResponseError) is a multi-line dump; detail is the actionable sentence.
        reason = ex.detail or ex.summary
        code = str(ex.code)
        if code.startswith("403"):
            return UserException(
                f'Tableau refused the extract refresh for {kind_singular} "{name}": {reason} '
                f"Check that the {kind_singular} allows this refresh type and that the configured "
                f"Tableau account has permission to refresh it."
            )
        if code.startswith("409"):
            # The lead sentence stays generic ("a conflict") because this matches the whole 409
            # family, not just the observed "already queued" code; Tableau's own detail, appended
            # last so it cannot run into a following sentence, carries the specific cause.
            return UserException(
                f'Tableau refused to queue the extract refresh for {kind_singular} "{name}" because '
                f"of a conflict — usually the previous refresh has not finished yet. Wait for the "
                f"running refresh to complete, or trigger this component less often. "
                f"Tableau reported: {reason}"
            )
        return None

    def _run_task(self, task):
        response = self.server.tasks.run(task)
        root = xmltodict.parse(response)

        job_id = root["tsResponse"]["job"]["@id"]
        return job_id

    def get_all_datasource_refresh_tasks(self):
        # filter only datasource refresh tasks
        tasks = list(tsc.Pager(TaskCustom(self.server)))
        logging.debug(f"Found tasks: {tasks}")
        return [task for task in tasks if task.target is not None and task.target.type == "datasource"]

    def validate_dataset_names(self, all_ds, datasources):
        conf_ds_names = dict()
        for ds in datasources:
            conf_ds_names[ds["name"]] = ds["type"]
        ds_names = [ds.name for ds in all_ds]
        inv_names = [nm for nm in conf_ds_names if nm not in ds_names]
        if inv_names:
            raise UserException(f"Some datasets do not exist: {inv_names}")
        return conf_ds_names

    def get_all_ds_for_tasks(self, tasks, all_ds):
        ds_tasks = dict()
        ds_ids = dict()
        for ds in all_ds:
            ds_ids[ds.id] = ds.name

        for t in tasks:
            if t.target.id not in ds_ids:
                continue

            ds = self.server.datasources.get_by_id(t.target.id)
            # normalize increment task
            ds_tasks[ds.name] = ds_tasks.get(ds.name, dict())
            ds_tasks[ds.name][t.task_type.lower()] = t

        return ds_tasks

    def validate_dataset_types(self, ds_tasks, param):

        inv_ds = [{ds: param[ds]} for ds in param if not ds_tasks.get(ds, {}).get(param[ds].lower())]

        if inv_ds:
            raise UserException(
                f"Some datasets do not have the required refresh type task: {inv_ds}. "
                f"Please create the extract refresh of that type first."
            )

    def _wait_for_finish(self, executed_jobs):
        remaining_jobs = executed_jobs.copy()
        failed_jobs = dict()
        while remaining_jobs:
            for ds_name in list(remaining_jobs):
                try:
                    job = self.server.jobs.get_by_id(executed_jobs[ds_name])
                except Exception as ex:
                    logging.warning(f"Failed to get job status for '{ds_name}': {ex}")
                    continue
                if int(job.finish_code) >= 0:
                    remaining_jobs.pop(ds_name, {})

                    if int(job.finish_code) > 0:  # job failed
                        failed_jobs[ds_name] = job
            time.sleep(60)  # preventing too many requests error

        if failed_jobs:
            failed_names = ", ".join(
                f"'{name}' (finish_code={job.finish_code})" for name, job in failed_jobs.items()
            )
            raise UserException(f"Some extract refresh jobs did not finish successfully: {failed_names}")

    def _get_all_ds_by_filter(self, kind, data_sources):
        all_ds = list()
        validation_errors = list()
        for ds_filter in data_sources:
            # if luid specified get the source
            if ds_filter.get(KEY_LUID):
                try:
                    res = getattr(self.server, kind).get_by_id(ds_filter[KEY_LUID])
                except tsc.ServerResponseError as ex:
                    # The Tableau REST API raises a 404xxx ServerResponseError (rather than
                    # returning an empty/None result) when the configured LUID does not exist
                    # on the server. That previously propagated uncaught all the way to the
                    # entrypoint as an opaque internal error. Surface it as a clear, user-facing
                    # message analogous to the not-found case _validate_ds_result already
                    # handles a few lines below, instead of a generic crash.
                    if str(ex.code).startswith("404"):
                        kind_singular = kind.rstrip("s")  # "datasources" -> "datasource", "workbooks" -> "workbook"
                        raise UserException(
                            f"There is no result for specified LUID, the {kind_singular} entry does not "
                            f"exist: {ds_filter[KEY_LUID]}"
                        ) from ex
                    raise
                ds = [res] if res else []

            else:
                ds = self._get_all_datasources_by_filter(kind, ds_filter[KEY_NAME], ds_filter.get(KEY_TAG))
            all_ds.extend(ds)
            err = self._validate_ds_result(ds_filter, ds)
            if err:
                validation_errors.append(err)

        return all_ds, validation_errors

    def _str_ds(self, ds_arr):
        str = "["
        for ds in ds_arr:
            str += f"(Name: {ds.name}, Project:{ds.project_name}, LUID: {ds.id}, tags: {ds.tags}), "
        str += "]"
        return str

    def _validate_ds_result(self, filter, ds):
        ds_error = None
        if not ds and not filter.get(KEY_LUID):
            ds_error = f"There is no result for combination of name & tag {filter}"
        if not ds and filter.get(KEY_LUID):
            ds_error = f"There is no result for specified LUID, the datasource does not exist {filter[KEY_LUID]}"

        # this happens when luid is set and name is not matching the dataset
        if len(ds) == 1 and filter[KEY_NAME] != ds[0].name:
            ds_error = (
                f"The dataset name retrieved by the specified LUID: '{ds[0].name}' "
                f"does not match the '{filter[KEY_NAME]}' specified in corresponding filter: {filter}"
            )

        if len(ds) > 1:
            ds_error = (
                f"There is more results for given filter: {filter}, "
                f"set more specific tag or use LUID. The results are: {self._str_ds(ds)}"
            )
        return ds_error

    def _get_all_datasources_by_filter(self, kind, name, tag):
        req_option = tsc.RequestOptions()
        req_option.filter.add(tsc.Filter(tsc.RequestOptions.Field.Name, tsc.RequestOptions.Operator.Equals, name))
        if tag:
            req_option.filter.add(tsc.Filter(tsc.RequestOptions.Field.Tags, tsc.RequestOptions.Operator.Equals, tag))

        datasource_items = list(tsc.Pager(getattr(self.server, kind), req_option))
        return datasource_items


"""
        Main entrypoint
"""
if __name__ == "__main__":
    try:
        comp = Component()
        # this triggers the run method by default and is controlled by the configuration.action parameter
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except tsc.FailedSignInError as exc:
        # The Tableau Server Client library raises this for ANY API call that gets a 401,
        # not only the initial sign-in (e.g. a session/token expiring mid-run during a long
        # poll_mode wait). Only the initial sign-in was previously converted to a
        # UserException (see run()); this is the same conversion for the rest of the
        # component's lifecycle so a mid-run auth failure surfaces as a clear user error
        # instead of an opaque internal error.
        logging.exception(f"Tableau authentication failed: {exc}")
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
