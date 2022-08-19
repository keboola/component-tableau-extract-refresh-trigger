from dataclasses import dataclass, field
from enum import Enum
from math import sqrt
from typing import List, Optional
import logging

from retry import retry

from keboola.component.exceptions import UserException

import tableauserverclient as tsc

from tableauserverclient.models import (
    TaskItem,
    DatasourceItem,
    ServerInfoItem,
    JobItem,
    Target,
)
from tableauserverclient.server import RequestOptions
from tableauserverclient.server.endpoint import ServerResponseError

KEY_NAME = "name"
KEY_TYPE = "type"
KEY_TAG = "tag"
KEY_LUID = "luid"

REQUEST_MAX_RETRIES = 42
REQUEST_RETRIES_INITIAL_DELAY = 0.5
REQUEST_RETRIES_BACKOFF_FACTOR = sqrt(2)
REQUEST_RETRIES_MAX_DELAY = 60
REQUEST_RETRIES_JITTER = (0, 0.5)


class DatasourceRefreshTaskType(Enum):
    Full = TaskItem.Type.ExtractRefresh
    Incremental = "IncrementExtractTask"

    @classmethod
    def from_string(cls, value: str) -> Optional["DatasourceRefreshTaskType"]:
        for item in cls:
            if item.value == value:
                return item
        if value == "RefreshExtractTask":
            return cls.Full
        raise ValueError(f"{value} is not a valid DatasourceRefreshTaskType")


@dataclass(slots=True, frozen=True)
class DatasourceRefreshSpec:
    name: str
    tag: str
    type: DatasourceRefreshTaskType
    luid: str

    @classmethod
    def from_dict(cls, d: dict) -> "DatasourceRefreshSpec":
        return cls(
            name=d[KEY_NAME],
            tag=d[KEY_TAG],
            type=DatasourceRefreshTaskType.from_string(d[KEY_TYPE]),
            luid=d[KEY_LUID],
        )

    def to_dict(self) -> dict:
        return {
            KEY_NAME: self.name,
            KEY_TAG: self.tag,
            KEY_TYPE: self.type.value,
            KEY_LUID: self.luid,
        }

    def __str__(self) -> str:
        return str(self.to_dict())


def datasource_to_string(datasource: DatasourceItem) -> str:
    return (
        f"(Name: {datasource.name}, Project:{datasource.project_name},"
        f" LUID: {datasource.id}, Tags: {datasource.tags})"
    )


def datasource_list_to_string(datasources: List[DatasourceItem]) -> str:
    str = "["
    for ds in datasources:
        str += f"{datasource_to_string(ds)}, "
    str += "]"
    return str


def task_list_to_string(tasks: List[TaskItem]) -> str:
    str = "["
    for task in tasks:
        str += f"(ID: {task.id}, Task type:{task.task_type}, Target: {task.target}), "
    str += "]"
    return str


def generate_datasource_search_error_message(
    spec: DatasourceRefreshSpec, datasources: List[DatasourceItem]
) -> str:
    error_message = None
    if not datasources:
        if not spec.luid:
            error_message = f"There is no data source for the combination of name {spec.name} and tag {spec.tag}."
        if spec.luid:
            error_message = (
                f"There is no data source with the specified LUID {spec.luid}."
            )

    if len(datasources) > 1:
        error_message = (
            f"There is more results for given filter: {spec}, "
            f"set more specific tag or use LUID. The results are: {datasource_list_to_string(datasources)}"
        )
    return error_message


@dataclass(slots=True)
class TableauServerClient:
    token_name: str
    token_secret: str
    site_id: Optional[str]
    endpoint: str
    __auth: tsc.PersonalAccessTokenAuth = field(init=False)
    __server: tsc.Server = field(init=False)
    __server_info: ServerInfoItem = field(init=False)
    __request_retry_decorator = retry(
        exceptions=ServerResponseError,
        tries=REQUEST_MAX_RETRIES,
        delay=REQUEST_RETRIES_INITIAL_DELAY,
        backoff=REQUEST_RETRIES_BACKOFF_FACTOR,
        max_delay=REQUEST_RETRIES_MAX_DELAY,
        jitter=REQUEST_RETRIES_JITTER,
        logger=logging.getLogger(),
    )
    __all_tasks: Optional[List[TaskItem]] = field(init=False, default=None)

    def __post_init__(self):
        # if authentication_type == "user/password":
        # self.auth = tsc.TableauAuth(
        #     self.cfg_params[KEY_USER_NAME],
        #     self.cfg_params[KEY_API_PASS],
        #     site_id=site_id,
        # )
        self.__auth = tsc.PersonalAccessTokenAuth(
            token_name=self.token_name,
            personal_access_token=self.token_secret,
            site_id=self.site_id,
        )
        self.__server = tsc.Server(self.endpoint, use_server_version=True)
        self.__server_info = self.__server.server_info.get()
        logging.info(f"Using server API version: {self.__server_info.rest_api_version}")

    @__request_retry_decorator
    def get_datasources(
        self, req_options: Optional[RequestOptions] = None
    ) -> List[DatasourceItem]:
        with self.__server.auth.sign_in(self.__auth):
            return list(tsc.Pager(self.__server.datasources, request_opts=req_options))

    @__request_retry_decorator
    def get_tasks(self, req_options: Optional[RequestOptions] = None) -> List[TaskItem]:
        with self.__server.auth.sign_in(self.__auth):
            return list(tsc.Pager(self.__server.tasks, request_opts=req_options))

    @__request_retry_decorator
    def get_datasource_by_id(self, datasource_id: str) -> DatasourceItem:
        with self.__server.auth.sign_in(self.__auth):
            return self.__server.datasources.get_by_id(datasource_id)

    @__request_retry_decorator
    def wait_for_job(self, job_id: str | JobItem) -> JobItem:
        with self.__server.auth.sign_in(self.__auth):
            return self.__server.jobs.wait_for_job(job_id)

    @__request_retry_decorator
    def run_task(self, task_item: TaskItem) -> JobItem:
        with self.__server.auth.sign_in(self.__auth):
            response_content = self.__server.tasks.run(
                task_item
            )  # This library function is unfinished so I have to explicitly parse the response:
        job_items = JobItem.from_response(response_content, self.__server.namespace)
        assert len(job_items) == 1
        return job_items[0]

    def get_datasource_by_name_and_tag(
        self, name: str, tag: Optional[str]
    ) -> List[DatasourceItem]:
        req_options = tsc.RequestOptions()
        req_options.filter.add(
            tsc.Filter(
                tsc.RequestOptions.Field.Name, tsc.RequestOptions.Operator.Equals, name
            )
        )
        if tag:
            req_options.filter.add(
                tsc.Filter(
                    tsc.RequestOptions.Field.Tags,
                    tsc.RequestOptions.Operator.Equals,
                    tag,
                )
            )
        return self.get_datasources(req_options=req_options)

    def get_task_by_datasource_refresh_spec(
        self, spec: DatasourceRefreshSpec
    ) -> TaskItem:
        if self.__all_tasks is None:
            self.__all_tasks = self.get_tasks()
        # Find the datasource by LUID or name and tag:
        if spec.luid:
            ds = self.get_datasource_by_id(spec.luid)
            if spec.name and spec.name != ds.name:
                raise UserException(
                    f"The datasource retrieved by the LUID '{spec.luid}' has name '{ds.name}'"
                    f" which does not match the name specified in the configuration: '{spec.name}'."
                )
        else:
            candidate_ds_list = self.get_datasource_by_name_and_tag(spec.name, spec.tag)
            if len(candidate_ds_list) != 1:
                raise UserException(
                    generate_datasource_search_error_message(spec, candidate_ds_list)
                )
            ds = candidate_ds_list[0]
        # Find the task by type and target datasource:
        tasks_found: List[TaskItem] = list()
        for task in self.__all_tasks:
            if task.task_type != spec.type.value:
                continue
            target: Target = task.target
            if target.type != "datasource":
                continue
            if target.id != ds.id:
                continue
            tasks_found.append(task)
        if len(tasks_found) > 1:
            raise UserException(
                f"Found {len(tasks_found)} tasks matching spec {spec}."
                f" The results are: {task_list_to_string(tasks_found)}"
            )
        elif len(tasks_found) == 0:
            UserException(
                f"No refresh task found for datasource: {datasource_to_string(ds)}."
                f" Please create the extract refresh of type {spec.type} first."
            )
        return tasks_found[0]

    def refresh_datasources(
        self, ds_list: List[DatasourceRefreshSpec], wait_for_jobs: bool = False
    ) -> List[JobItem]:
        logging.info(
            "Finding refresh tasks for specfied datasources and refresh types."
        )
        tasks_to_run = [
            self.get_task_by_datasource_refresh_spec(spec) for spec in ds_list
        ]
        logging.info(
            "Found task to run for every datasource. Attempting to run these tasks as jobs."
        )
        jobs = [self.run_task(task) for task in tasks_to_run]
        logging.info("Successfully started all the jobs.")
        if wait_for_jobs:
            logging.info("Waiting for all jobs to complete.")
            finished_jobs = [self.wait_for_job(job) for job in jobs]
            logging.info("All jobs completed.")
            return finished_jobs
        else:
            return jobs
