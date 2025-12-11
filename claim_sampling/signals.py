import logging

from claim_sampling.services import ClaimSamplingService
from core.models import User
from core.service_signals import ServiceSignalBindType
from core.signals import bind_service_signal
from django.db import transaction

from tasks_management.apps import TasksManagementConfig
from tasks_management.models import Task

logger = logging.getLogger(__name__)


def _resolve_task_any(_task: Task, _user: User):
    claim_sampling_id = _task.data['data']['uuid']
    claim_sampling_service = ClaimSamplingService(user=_user)
    claim_sampling_service.extrapolate_results(claim_sampling_id)


def _resolve_task_all(_task, _user):
    # TODO for now hardcoded to any, to be updated
    _resolve_task_any(_task, _user)


def _resolve_task_n(_task, _user):
    # TODO for now hardcoded to any, to be updated
    _resolve_task_any(_task, _user)


def on_claim_sampling_resolve_task(**kwargs):
    try:
        result = kwargs.get('result', None)
        if result and result['success'] \
                and result['data']['task']['status'] == Task.Status.ACCEPTED \
                and result['data']['task']['executor_action_event'] == TasksManagementConfig.default_executor_event \
                and result['data']['task']['business_event'] == 'claim_sample_extrapolation':
            data = kwargs.get("result").get("data")
            task = Task.objects.select_related('task_group').prefetch_related('task_group__taskexecutor_set').get(
                id=data["task"]["id"])
            user = User.objects.get(id=data["user"]["id"])

            # Task only relevant for this specific source
            if task.source != 'claim_sampling':
                return

            resolvers = {
                'ALL': _resolve_task_all,
                'ANY': _resolve_task_any,
                'N': _resolve_task_n,
            }

            if task.task_group.completion_policy not in resolvers:
                logger.error("Resolving task with unknown completion_policy: %s", task.task_group.completion_policy)
                return ['Unknown completion_policy: %s' % task.task_group.completion_policy]
            with transaction.atomic():
                resolvers[task.task_group.completion_policy](task, user)
    except Exception as e:
        logger.error("Error while executing on_task_resolve", exc_info=e)
        return [str(e)]


def bind_service_signals():
    bind_service_signal(
        'task_service.resolve_task',
        on_claim_sampling_resolve_task,
        bind_type=ServiceSignalBindType.AFTER
    )
