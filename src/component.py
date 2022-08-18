"""
Template Component main class.

"""

import logging
from typing import List, Optional

# import xmltodict

from keboola.component import ComponentBase, UserException

from client import TableauServerClient, DatasourceRefreshSpec

# global constants


# configuration variables
# KEY_API_PASS = "#password"
# KEY_USER_NAME = "user"
KEY_ENDPOINT = "endpoint"
KEY_POLL_MODE = "poll_mode"

KEY_DATASOURCES = "datasources"
KEY_SITE_ID = "site_id"
KEY_TOKEN_NAME = "token_name"
KEY_TOKEN_SECRET = "#token_secret"

KEY_AUTH_TYPE = "authentication_type"
MANDATORY_PARS = [
    KEY_AUTH_TYPE,
    KEY_TOKEN_NAME,
    KEY_TOKEN_SECRET,
    KEY_DATASOURCES,
    KEY_ENDPOINT,
]


class TableauExtractRefreshTrigger(ComponentBase):
    def run(self):
        """
        Main execution code
        """

        params: dict = self.configuration.parameters  # noqa

        authentication_type: str = params.get(KEY_AUTH_TYPE, "user/password")
        if authentication_type != "Personal Access Token":
            raise UserException("Personal Access Token must be used.")

        # self.validate_configuration_parameters(MANDATORY_PARS)
        # override debug from config
        debug: Optional[bool] = params.get("debug")

        if not debug:
            # suppress info logging on the Tableau endpoints
            logging.getLogger("tableau.endpoint.jobs").setLevel(logging.ERROR)
            logging.getLogger("tableau.endpoint.datasources").setLevel(logging.ERROR)

        token_name: str = params[KEY_TOKEN_NAME]
        token_secret: str = params[KEY_TOKEN_SECRET]
        endpoint: str = params[KEY_ENDPOINT]
        datasource_refresh_specs: List[dict] = params[KEY_DATASOURCES]

        site_id: str = params.get(KEY_SITE_ID)
        wait_for_jobs: bool = bool(params.get(KEY_POLL_MODE, False))

        client = TableauServerClient(
            token_name=token_name,
            token_secret=token_secret,
            site_id=site_id,
            endpoint=endpoint,
        )

        # all_datasources = client.get_datasources()
        # print(all_datasources)
        # all_tasks = client.get_tasks()
        # print(all_tasks)

        refresh_specs = [
            DatasourceRefreshSpec.from_dict(ds_refresh_spec)
            for ds_refresh_spec in datasource_refresh_specs
        ]

        client.refresh_datasources(refresh_specs, wait_for_jobs=wait_for_jobs)


"""
        Main entrypoint
"""
if __name__ == "__main__":
    try:
        comp = TableauExtractRefreshTrigger()
        # this triggers the run method by default and is controlled by the configuration.action parameter
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
