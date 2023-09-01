import xml.etree.ElementTree as ET
from datetime import datetime

from tableauserverclient import Target
from tableauserverclient.datetime_helpers import parse_datetime
from tableauserverclient.models.property_decorators import property_is_enum, property_is_valid_time, \
    property_not_nullable


class IntervalItem(object):
    class Frequency:
        Hourly = "Hourly"
        Daily = "Daily"
        Weekly = "Weekly"
        Monthly = "Monthly"

    class Occurrence:
        Minutes = "minutes"
        Hours = "hours"
        WeekDay = "weekDay"
        MonthDay = "monthDay"

    class Day:
        Sunday = "Sunday"
        Monday = "Monday"
        Tuesday = "Tuesday"
        Wednesday = "Wednesday"
        Thursday = "Thursday"
        Friday = "Friday"
        Saturday = "Saturday"
        LastDay = "LastDay"


class HourlyInterval(object):
    def __init__(self, start_time, end_time, interval_value):

        self.start_time = start_time
        self.end_time = end_time
        self.interval = interval_value

    @property
    def _frequency(self):
        return IntervalItem.Frequency.Hourly

    @property
    def start_time(self):
        return self._start_time

    @start_time.setter
    @property_is_valid_time
    @property_not_nullable
    def start_time(self, value):
        self._start_time = value

    @property
    def end_time(self):
        return self._end_time

    @end_time.setter
    @property_is_valid_time
    @property_not_nullable
    def end_time(self, value):
        self._end_time = value

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, interval):
        print(f"Received interval: {interval}")

        VALID_INTERVALS = {.25, .5, 1, 2, 4, 6, 8, 12}
        if float(interval) not in VALID_INTERVALS:
            error = "Invalid interval {} not in {}".format(interval, str(VALID_INTERVALS))
            raise ValueError(error)

        self._interval = interval

    def _interval_type_pairs(self):

        # We use fractional hours for the two minute-based intervals.
        # Need to convert to minutes from hours here
        if self.interval in {.25, .5}:
            calculated_interval = int(self.interval * 60)
            interval_type = IntervalItem.Occurrence.Minutes
        else:
            calculated_interval = self.interval
            interval_type = IntervalItem.Occurrence.Hours

        return [(interval_type, str(calculated_interval))]


class DailyInterval(object):
    def __init__(self, start_time):
        self.start_time = start_time

    @property
    def _frequency(self):
        return IntervalItem.Frequency.Daily

    @property
    def start_time(self):
        return self._start_time

    @start_time.setter
    @property_is_valid_time
    @property_not_nullable
    def start_time(self, value):
        self._start_time = value


class WeeklyInterval(object):
    def __init__(self, start_time, *interval_values):
        self.start_time = start_time
        self.interval = interval_values

    @property
    def _frequency(self):
        return IntervalItem.Frequency.Weekly

    @property
    def start_time(self):
        return self._start_time

    @start_time.setter
    @property_is_valid_time
    @property_not_nullable
    def start_time(self, value):
        self._start_time = value

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, interval_values):
        if not all(hasattr(IntervalItem.Day, day) for day in interval_values):
            raise ValueError("Invalid week day defined " + str(interval_values))

        self._interval = interval_values

    def _interval_type_pairs(self):
        return [(IntervalItem.Occurrence.WeekDay, day) for day in self.interval]


class MonthlyInterval(object):
    def __init__(self, start_time, interval_value):
        self.start_time = start_time
        self.interval = str(interval_value)

    @property
    def _frequency(self):
        return IntervalItem.Frequency.Monthly

    @property
    def start_time(self):
        return self._start_time

    @start_time.setter
    @property_is_valid_time
    @property_not_nullable
    def start_time(self, value):
        self._start_time = value

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, interval_value):
        error = "Invalid interval value for a monthly frequency: {}.".format(interval_value)

        # This is weird because the value could be a str or an int
        # The only valid str is 'LastDay' so we check that first. If that's not it
        # try to convert it to an int, if that fails because it's an incorrect string
        # like 'badstring' we catch and re-raise. Otherwise we convert to int and check
        # that it's in range 1-31

        # changed in 3.20
        if interval_value not in ["LastDay", "Last", "First"]:
            try:
                if not (1 <= int(interval_value) <= 31):
                    raise ValueError(error)
            except ValueError:
                if interval_value not in ["LastDay", "Last", "First"]:
                    raise ValueError(error)

        self._interval = str(interval_value)

    def _interval_type_pairs(self):
        return [(IntervalItem.Occurrence.MonthDay, self.interval)]


class ScheduleItem(object):
    class Type:
        Extract = "Extract"
        Flow = "Flow"
        Subscription = "Subscription"
        DataAcceleration = "DataAcceleration"

    class ExecutionOrder:
        Parallel = "Parallel"
        Serial = "Serial"

    class State:
        Active = "Active"
        Suspended = "Suspended"

    def __init__(self, name, priority, schedule_type, execution_order, interval_item):
        self._created_at = None
        self._end_schedule_at = None
        self._id = None
        self._next_run_at = None
        self._state = None
        self._updated_at = None
        self.interval_item = interval_item
        self.execution_order = execution_order
        self.name = name
        self.priority = priority
        self.schedule_type = schedule_type

    def __repr__(self):
        return "<Schedule#{_id} \"{_name}\" {interval_item}>".format(**self.__dict__)

    @property
    def created_at(self):
        return self._created_at

    @property
    def end_schedule_at(self):
        return self._end_schedule_at

    @property
    def execution_order(self):
        return self._execution_order

    @execution_order.setter
    @property_is_enum(ExecutionOrder)
    def execution_order(self, value):
        self._execution_order = value

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def next_run_at(self):
        return self._next_run_at

    @property
    def priority(self):
        return self._priority

    @priority.setter
    def priority(self, value):
        self._priority = value

    @property
    def schedule_type(self):
        return self._schedule_type

    @schedule_type.setter
    def schedule_type(self, value):
        self._schedule_type = value

    @property
    def state(self):
        return self._state

    @state.setter
    @property_is_enum(State)
    def state(self, value):
        self._state = value

    @property
    def updated_at(self):
        return self._updated_at

    @property
    def warnings(self):
        return self._warnings

    def _parse_common_tags(self, schedule_xml, ns):
        if not isinstance(schedule_xml, ET.Element):
            schedule_xml = ET.fromstring(schedule_xml).find('.//t:schedule', namespaces=ns)
        if schedule_xml is not None:
            (_, name, _, _, updated_at, _, next_run_at, end_schedule_at, execution_order,
             priority, interval_item) = self._parse_element(schedule_xml, ns)

            self._set_values(id_=None,
                             name=name,
                             state=None,
                             created_at=None,
                             updated_at=updated_at,
                             schedule_type=None,
                             next_run_at=next_run_at,
                             end_schedule_at=end_schedule_at,
                             execution_order=execution_order,
                             priority=priority,
                             interval_item=interval_item)

        return self

    def _set_values(self, id_, name, state, created_at, updated_at, schedule_type,
                    next_run_at, end_schedule_at, execution_order, priority, interval_item, warnings=None):
        if id_ is not None:
            self._id = id_
        if name:
            self._name = name
        if state:
            self._state = state
        if created_at:
            self._created_at = created_at
        if updated_at:
            self._updated_at = updated_at
        if schedule_type:
            self._schedule_type = schedule_type
        if next_run_at:
            self._next_run_at = next_run_at
        if end_schedule_at:
            self._end_schedule_at = end_schedule_at
        if execution_order:
            self._execution_order = execution_order
        if priority:
            self._priority = priority
        if interval_item:
            self._interval_item = interval_item
        if warnings:
            self._warnings = warnings

    @classmethod
    def from_response(cls, resp, ns):
        parsed_response = ET.fromstring(resp)
        return cls.from_element(parsed_response, ns)

    @classmethod
    def from_element(cls, parsed_response, ns):
        warnings = cls._read_warnings(parsed_response, ns)

        all_schedule_items = []
        all_schedule_xml = parsed_response.findall('.//t:schedule', namespaces=ns)
        for schedule_xml in all_schedule_xml:
            (id_, name, state, created_at, updated_at, schedule_type, next_run_at,
             end_schedule_at, execution_order, priority, interval_item) = cls._parse_element(schedule_xml, ns)

            schedule_item = cls(name, priority, schedule_type, execution_order, interval_item)

            schedule_item._set_values(id_=id_,
                                      name=None,
                                      state=state,
                                      created_at=created_at,
                                      updated_at=updated_at,
                                      schedule_type=None,
                                      next_run_at=next_run_at,
                                      end_schedule_at=end_schedule_at,
                                      execution_order=None,
                                      priority=None,
                                      interval_item=None,
                                      warnings=warnings)

            all_schedule_items.append(schedule_item)
        return all_schedule_items

    @staticmethod
    def _parse_interval_item(parsed_response, frequency, ns):
        start_time = parsed_response.get("start", None)
        start_time = datetime.strptime(start_time, "%H:%M:%S").time()
        end_time = parsed_response.get("end", None)
        if end_time is not None:
            end_time = datetime.strptime(end_time, "%H:%M:%S").time()
        interval_elems = parsed_response.findall(".//t:intervals/t:interval", namespaces=ns)
        interval = []
        for interval_elem in interval_elems:
            interval.extend(interval_elem.attrib.items())

        if frequency == IntervalItem.Frequency.Daily:
            return DailyInterval(start_time)

        if frequency == IntervalItem.Frequency.Hourly:
            print(f"interval: {interval}")
            interval_occurrence, interval_value = interval.pop(0)

            # We use fractional hours for the two minute-based intervals.
            # Need to convert to hours from minutes here
            if interval_occurrence == IntervalItem.Occurrence.Minutes:
                interval_value = float(interval_value) / 60

            print(start_time)
            print(end_time)
            print(interval_value)
            return HourlyInterval(start_time, end_time, interval_value)

        if frequency == IntervalItem.Frequency.Weekly:
            interval_values = [i[1] for i in interval]
            return WeeklyInterval(start_time, *interval_values)

        if frequency == IntervalItem.Frequency.Monthly:
            interval_occurrence, interval_value = interval.pop()
            return MonthlyInterval(start_time, interval_value)

    @staticmethod
    def _parse_element(schedule_xml, ns):
        id = schedule_xml.get('id', None)
        name = schedule_xml.get('name', None)
        state = schedule_xml.get('state', None)
        created_at = parse_datetime(schedule_xml.get('createdAt', None))
        updated_at = parse_datetime(schedule_xml.get('updatedAt', None))
        schedule_type = schedule_xml.get('type', None)
        frequency = schedule_xml.get('frequency', None)
        next_run_at = parse_datetime(schedule_xml.get('nextRunAt', None))
        end_schedule_at = parse_datetime(schedule_xml.get('endScheduleAt', None))
        execution_order = schedule_xml.get('executionOrder', None)

        priority = schedule_xml.get('priority', None)
        if priority:
            priority = int(priority)

        interval_item = None
        frequency_detail_elem = schedule_xml.find('.//t:frequencyDetails', namespaces=ns)

        if frequency_detail_elem is not None:
            # print(f"frequency_detail_elem: {ET.tostring(frequency_detail_elem, encoding='utf-8').decode('utf-8')}")
            # print(f"frequency: {frequency}")
            # print(f"ns: {ns}")
            interval_item = ScheduleItem._parse_interval_item(frequency_detail_elem, frequency, ns)

        return id, name, state, created_at, updated_at, schedule_type, \
               next_run_at, end_schedule_at, execution_order, priority, interval_item  # noqa

    @staticmethod
    def parse_add_to_schedule_response(response, ns):
        parsed_response = ET.fromstring(response.content)
        warnings = ScheduleItem._read_warnings(parsed_response, ns)
        all_task_xml = parsed_response.findall('.//t:task', namespaces=ns)

        error = "Status {}: {}".format(response.status_code, response.reason) \
            if response.status_code < 200 or response.status_code >= 300 else None
        task_created = len(all_task_xml) > 0
        return error, warnings, task_created

    @staticmethod
    def _read_warnings(parsed_response, ns):
        all_warning_xml = parsed_response.findall('.//t:warning', namespaces=ns)
        warnings = list() if len(all_warning_xml) > 0 else None
        for warning_xml in all_warning_xml:
            warnings.append(warning_xml.get('message', None))
        return warnings


class TaskItem(object):
    class Type:
        ExtractRefresh = "extractRefresh"
        DataAcceleration = "dataAcceleration"

    def __init__(self, id_, task_type, priority, consecutive_failed_count=0, schedule_id=None,
                 schedule_item=None, last_run_at=None, target=None):
        self.id = id_
        self.task_type = task_type
        self.priority = priority
        self.consecutive_failed_count = consecutive_failed_count
        self.schedule_id = schedule_id
        self.schedule_item = schedule_item
        self.last_run_at = last_run_at
        self.target = target

    def __repr__(self):
        return "<Task#{id} {task_type} pri({priority}) failed({consecutive_failed_count}) schedule_id({" \
               "schedule_id}) target({target})>".format(**self.__dict__)

    @classmethod
    def from_response(cls, xml, ns, task_type=Type.ExtractRefresh):
        parsed_response = ET.fromstring(xml)
        all_tasks_xml = parsed_response.findall(
            './/t:task/t:{}'.format(task_type), namespaces=ns)

        all_tasks = (TaskItem._parse_element(x, ns) for x in all_tasks_xml)

        return list(all_tasks)

    @classmethod
    def _parse_element(cls, element, ns):
        schedule_item = None
        target = None
        last_run_at = None
        workbook_element = element.find('.//t:workbook', namespaces=ns)
        datasource_element = element.find('.//t:datasource', namespaces=ns)
        last_run_at_element = element.find('.//t:lastRunAt', namespaces=ns)

        schedule_item_list = ScheduleItem.from_element(element, ns)
        if len(schedule_item_list) >= 1:
            schedule_item = schedule_item_list[0]

        # according to the Tableau Server REST API documentation,
        # there should be only one of workbook or datasource
        if workbook_element is not None:
            workbook_id = workbook_element.get('id', None)
            target = Target(workbook_id, "workbook")
        if datasource_element is not None:
            datasource_id = datasource_element.get('id', None)
            target = Target(datasource_id, "datasource")
        if last_run_at_element is not None:
            last_run_at = parse_datetime(last_run_at_element.text)

        task_type = element.get('type', None)
        priority = int(element.get('priority', -1))
        consecutive_failed_count = int(element.get('consecutiveFailedCount', 0))
        id_ = element.get('id', None)
        return cls(id_, task_type, priority, consecutive_failed_count, schedule_item.id,
                   schedule_item, last_run_at, target)
