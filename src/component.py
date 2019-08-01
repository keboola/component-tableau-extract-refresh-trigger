'''
Template Component main class.

'''

import logging
import sys

import tableauserverclient as tsc
import xmltodict
from kbc.env_handler import KBCEnvHandler

# global constants


# configuration variables
KEY_API_PASS = '#password'
KEY_USER_NAME = 'user'
KEY_ENDPOINT = 'endpoint'
KEY_POLL_MODE = 'poll_mode'
KEY_DS_NAME = 'name'
KEY_DS_TYPE = 'type'
KEY_DATASOURCES = 'datasources'

MANDATORY_PARS = [KEY_API_PASS, KEY_USER_NAME, KEY_DATASOURCES]
MANDATORY_IMAGE_PARS = []

APP_VERSION = '0.0.1'


class Component(KBCEnvHandler):

    def __init__(self, debug=False):
        KBCEnvHandler.__init__(self, MANDATORY_PARS)
        # override debug from config
        if self.cfg_params.get('debug'):
            debug = True

        self.set_default_logger('DEBUG' if debug else 'INFO')
        logging.info('Running version %s', APP_VERSION)
        logging.info('Loading configuration...')

        try:
            self.validate_config()
            self.validate_image_parameters(MANDATORY_IMAGE_PARS)
        except ValueError as e:
            logging.error(e)
            exit(1)

        # intialize instance parameteres
        self.auth = tsc.TableauAuth(self.cfg_params[KEY_USER_NAME], self.cfg_params[KEY_API_PASS])
        self.server = tsc.Server(self.cfg_params[KEY_ENDPOINT], use_server_version=True)
        self.server_info = self.server.server_info.get()
        logging.info(F"Using server API version: {self.server_info.rest_api_version}")

    def run(self):
        '''
        Main execution code
        '''
        params = self.cfg_params  # noqa

        with self.server.auth.sign_in(self.auth):
            executed_jobs = dict()

            data_sources = params[KEY_DATASOURCES]
            # tasks
            # filter only datasource refresh tasks
            logging.info('Validating extract names...')
            all_ds = self.server.datasources.get()
            ds_to_refresh = self.validate_dataset_names(all_ds, data_sources)

            tasks = self.get_datasource_refresh_tasks()
            # get all datasources for tasks
            logging.info('Retrieving extract tasks and validating extract types...')
            ds_tasks = self.get_all_ds_for_tasks(tasks)
            self.validate_dataset_types(ds_tasks, ds_to_refresh)

            for ds in data_sources:
                logging.info(F'Triggering extract: {ds}')
                task = ds_tasks[ds[KEY_DS_NAME]][ds[KEY_DS_TYPE].lower()]
                job_id = self._run_task(task)
                executed_jobs[ds[KEY_DS_NAME]] = job_id

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

    def get_datasource_refresh_tasks(self):
        # filter only datasource refresh tasks
        tasks, pitem = self.server.tasks.get()

        return [task for task in tasks if task.target.type == 'datasource']

    def validate_dataset_names(self, all_ds, datasources):
        conf_ds_names = dict()
        for ds in datasources:
            conf_ds_names[ds['name']] = ds['type']
        ds_names = [ds.name for ds in all_ds[0]]
        inv_names = [nm for nm in conf_ds_names if nm not in ds_names]
        if inv_names:
            raise ValueError(F'Some datasets do not exist! {inv_names}')
        return conf_ds_names

    def get_all_ds_for_tasks(self, tasks):
        ds_tasks = dict()
        for t in tasks:
            ds = self.server.datasources.get_by_id(t.target.id)
            ds_tasks[ds.name] = {t.task_type.lower(): t}

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

        if failed_jobs:
            raise RuntimeError(F'Some jobs did not finish properly: {failed_jobs}')


"""
        Main entrypoint
"""
if __name__ == "__main__":
    if len(sys.argv) > 1:
        debug = sys.argv[1]
    else:
        debug = True
    comp = Component(debug)
    comp.run()
