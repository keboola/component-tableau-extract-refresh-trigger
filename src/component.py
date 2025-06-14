'''
Template Component main class.

'''
import logging
import os
import time

import tableauserverclient as tsc
import xmltodict
from keboola.component import ComponentBase, UserException

# configuration variables
from tableau_custom.endpoints.tasks_endpoint import TaskCustom

# global constants

KEY_TAG = 'tag'
KEY_NAME = 'name'
KEY_LUID = 'luid'
KEY_API_PASS = '#password'
KEY_TOKEN_NAME = 'token_name'
KEY_TOKEN = '#token_secret'
KEY_USER_NAME = 'user'
KEY_ENDPOINT = 'endpoint'
KEY_POLL_MODE = 'poll_mode'
KEY_DS_NAME = 'name'
KEY_DS_TYPE = 'type'
KEY_DATASOURCES = 'datasources'
KEY_WORKBOOKS = 'workbooks'
KEY_SITE_ID = 'site_id'
KEY_CONTINUE_ON_ERROR = 'continue_on_error'

KEY_AUTH_TYPE = 'authentication_type'
AUTH_NAMES = [KEY_USER_NAME, KEY_TOKEN_NAME]
AUTH_SECRETS = [KEY_API_PASS, KEY_TOKEN]
MANDATORY_PARS = [AUTH_NAMES, AUTH_SECRETS, KEY_DATASOURCES, KEY_ENDPOINT]

APP_VERSION = '0.0.1'

logger = logging.getLogger('tableau.endpoint.tasks')


class Component(ComponentBase):

    def __init__(self):
        super().__init__(required_parameters=MANDATORY_PARS)
        self.cfg_params = self.configuration.parameters

        log_level = logging.DEBUG if self.cfg_params.get('debug') else logging.INFO
        # setup GELF if available
        if os.getenv('KBC_LOGGER_ADDR', None):
            self.set_gelf_logger(log_level)
        else:
            self.set_default_logger(log_level)
        logging.info('Running version %s', APP_VERSION)
        logging.info('Loading configuration...')

        if not self.cfg_params.get('debug'):
            # suppress info logging on the Tableau endpoints
            logging.getLogger('tableau.endpoint.jobs').setLevel(logging.ERROR)
            logging.getLogger('tableau.endpoint.datasources').setLevel(logging.ERROR)

        site_id = self.cfg_params.get(KEY_SITE_ID) or ''
        # intialize instance parameteres

        if self.cfg_params.get(KEY_AUTH_TYPE, 'user/password') == 'user/password':
            self.auth = tsc.TableauAuth(self.cfg_params[KEY_USER_NAME], self.cfg_params[KEY_API_PASS],
                                        site_id=site_id)
        elif self.cfg_params.get(KEY_AUTH_TYPE) == "Personal Access Token":
            self.auth = tsc.PersonalAccessTokenAuth(token_name=self.cfg_params[KEY_TOKEN_NAME],
                                                    personal_access_token=self.cfg_params[KEY_TOKEN],
                                                    site_id=site_id)
        api_version = self.cfg_params.get('api_version', 'use_server_version')
        if api_version == 'use_server_version':
            user_server_version = True
        else:
            user_server_version = False
        logging.debug(f"use server:{user_server_version}, api: {api_version}")
        self.server = tsc.Server(self.cfg_params[KEY_ENDPOINT], use_server_version=user_server_version)

        if not user_server_version:
            self.server.version = api_version
        self.server_info = self.server.server_info.get()
        logging.info(F"Using API version: {self.server.version}")

    def run(self):
        '''
        Main execution code
        '''
        params = self.cfg_params  # noqa
        continue_on_error = params.get(KEY_CONTINUE_ON_ERROR, False)

        with self.server.auth.sign_in(self.auth):
            executed_jobs = dict()

            data_sources = params[KEY_DATASOURCES]
            if data_sources:
                # tasks
                # filter only datasource refresh tasks
                logging.info('Validating extract names...')

                all_ds, validation_errors = self._get_all_ds_by_filter("datasources", data_sources)
                logging.debug(F'Recognized datasets: {all_ds}')

                if validation_errors:
                    for err in validation_errors:
                        logging.exception(err)
                    exit(1)
                ds_to_refresh = self.validate_dataset_names(all_ds, data_sources)

                tasks = self.get_all_datasource_refresh_tasks()
                # get all datasources for tasks
                logging.info('Retrieving extract tasks and validating extract types...')
                ds_tasks = self.get_all_ds_for_tasks(tasks, all_ds)
                logging.debug(F"Found datasource tasks: {ds_tasks}")
                self.validate_dataset_types(ds_tasks, ds_to_refresh)

                for ds in data_sources:
                    task = ds_tasks[ds[KEY_DS_NAME]][ds[KEY_DS_TYPE].lower()]
                    logging.info(F'Triggering extract for: "{ds[KEY_DS_NAME]}" with LUID: "{task.target.id}""')
                    try:
                        job_id = self._run_task(task)
                        executed_jobs[ds[KEY_DS_NAME]] = job_id
                    except Exception as ex:
                        if continue_on_error:
                            logging.warning(F'Failed to trigger extract for dataset: {ds[KEY_DS_NAME]}. {ex}')
                        else:
                            raise ex

            workbooks = params.get(KEY_WORKBOOKS, False)
            if workbooks:
                all_wb, validation_errors = self._get_all_ds_by_filter("workbooks", workbooks)
                for wb in all_wb:
                    logging.info(F'Triggering extract for: "{wb.name}" with LUID: "{wb.id}""')
                    try:
                        job = self.server.workbooks.refresh(wb)
                        executed_jobs[wb.name] = job.id
                    except Exception as ex:
                        if continue_on_error:
                            logging.warning(F'Failed to trigger extract for workbook: {wb.name}. {ex}')
                        else:
                            raise ex

            # poll job statuses
            if params.get(KEY_POLL_MODE):
                logging.info('Polling extract refresh statuses.')
                self._wait_for_finish(executed_jobs)

        logging.info('Trigger finished successfully!')

    def _run_task(self, task):
        response = self.server.tasks.run(task)
        root = xmltodict.parse(response)

        job_id = root['tsResponse']['job']['@id']
        return job_id

    def get_all_datasource_refresh_tasks(self):
        # filter only datasource refresh tasks
        tasks = list(tsc.Pager(TaskCustom(self.server)))
        logging.debug(F'Found tasks: {tasks}')
        return [task for task in tasks if task.target is not None and task.target.type == 'datasource']

    def validate_dataset_names(self, all_ds, datasources):
        conf_ds_names = dict()
        for ds in datasources:
            conf_ds_names[ds['name']] = ds['type']
        ds_names = [ds.name for ds in all_ds]
        inv_names = [nm for nm in conf_ds_names if nm not in ds_names]
        if inv_names:
            raise ValueError(F'Some datasets do not exist! {inv_names}')
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
            raise ValueError(F'Some datasets do not have the required refresh type task: {inv_ds}. '
                             F'Please create the extract refresh of that type first.')

    def _wait_for_finish(self, executed_jobs):
        remaining_jobs = executed_jobs.copy()
        failed_jobs = dict()
        while remaining_jobs:
            for ds_name in executed_jobs:
                job = self.server.jobs.get_by_id(executed_jobs[ds_name])
                if int(job.finish_code) >= 0:
                    remaining_jobs.pop(ds_name, {})

                    if int(job.finish_code) > 0:  # job failed
                        failed_jobs[ds_name] = job
            time.sleep(60)   # preventing too many requests error

        if failed_jobs:
            raise RuntimeError(F'Some jobs did not finish properly: {failed_jobs}')

    def _get_all_ds_by_filter(self, kind, data_sources):
        all_ds = list()
        validation_errors = list()
        for ds_filter in data_sources:
            # if luid specified get the source
            if ds_filter.get(KEY_LUID):
                res = getattr(self.server, kind).get_by_id(ds_filter[KEY_LUID])
                ds = [res] if res else []

            else:
                ds = self._get_all_datasources_by_filter(kind, ds_filter[KEY_NAME], ds_filter.get(KEY_TAG))
            all_ds.extend(ds)
            err = self._validate_ds_result(ds_filter, ds)
            if err:
                validation_errors.append(err)

        return all_ds, validation_errors

    def _str_ds(self, ds_arr):
        str = '['
        for ds in ds_arr:
            str += F'(Name: {ds.name}, Project:{ds.project_name}, LUID: {ds.id}, tags: {ds.tags}), '
        str += ']'
        return str

    def _validate_ds_result(self, filter, ds):
        ds_error = None
        if not ds and not filter.get(KEY_LUID):
            ds_error = F'There is no result for combination of name & tag {filter}'
        if not ds and filter.get(KEY_LUID):
            ds_error = F'There is no result for specified LUID, the datasource does not exist {filter[KEY_LUID]}'

        # this happens when luid is set and name is not matching the dataset
        if len(ds) == 1 and filter[KEY_NAME] != ds[0].name:
            ds_error = F"The dataset name retrieved by the specified LUID: '{ds[0].name}' " \
                       F"does not match the '{filter[KEY_NAME]}' specified in corresponding filter: {filter}"

        if len(ds) > 1:
            ds_error = F"There is more results for given filter: {filter}, " \
                       F"set more specific tag or use LUID. The results are: {self._str_ds(ds)}"
        return ds_error

    def _get_all_datasources_by_filter(self, kind, name, tag):
        req_option = tsc.RequestOptions()
        req_option.filter.add(tsc.Filter(tsc.RequestOptions.Field.Name,
                                         tsc.RequestOptions.Operator.Equals,

                                         name))
        if tag:
            req_option.filter.add(tsc.Filter(tsc.RequestOptions.Field.Tags,
                                             tsc.RequestOptions.Operator.Equals,
                                             tag))

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
    except Exception as exc:
        logging.exception(exc)
        exit(2)
