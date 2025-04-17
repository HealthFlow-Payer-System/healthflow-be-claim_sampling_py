import logging
import uuid
import pathlib
import base64
from typing import Callable, Dict
import random
import graphene

from claim.gql_queries import ClaimGQLType
from core.gql.gql_mutations import mutation_on_uuids_from_filter
from tasks_management.models import TaskGroup
from .apps import ClaimSamplingConfig
from core.schema import TinyInt, OpenIMISMutation
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext as _

from claim.gql_mutations import ClaimCodeInputType, ClaimGuaranteeIdInputType, FeedbackInputType
from core.models.user import ClaimAdmin
from claim.models import Claim

from django.db import transaction

from .models import ClaimSamplingBatch, ClaimSamplingBatchAssignment
from .services import ClaimSamplingService

logger = logging.getLogger(__name__)


class ClaimSamplingBatchInputType(OpenIMISMutation.Input):
    percentage = graphene.Int(required=True)
    t = graphene.Int(required=True)

    status = TinyInt(required=False)
    id = graphene.Int(required=False, read_only=True)
    uuid = graphene.String(required=False)
    autogenerate = graphene.Boolean(required=False)
    insuree_id = graphene.Int(required=False)
    date_from = graphene.Date(required=False)
    date_to = graphene.Date(required=False)
    icd_id = graphene.Int(required=False)
    icd_1_id = graphene.Int(required=False)
    icd_2_id = graphene.Int(required=False)
    icd_3_id = graphene.Int(required=False)
    icd_4_id = graphene.Int(required=False)
    review_status = TinyInt(required=False)
    date_claimed = graphene.Date(required=False)
    date_processed = graphene.Date(required=False)
    health_facility_id = graphene.Int(required=False)
    refer_from_id = graphene.Int(required=False)
    refer_to_id = graphene.Int(required=False)
    batch_run_id = graphene.Int(required=False)
    category = graphene.String(max_length=1, required=False)
    visit_type = graphene.String(max_length=1, required=False)
    admin_id = graphene.Int(required=False)
    explanation = graphene.String(required=False)
    adjustment = graphene.String(required=False)
    json_ext = graphene.types.json.JSONString(required=False)
    restore = graphene.UUID(required=False)
    feedback_available = graphene.Boolean(default=False)
    feedback_status = TinyInt(required=False)
    care_type = graphene.String(required=False)

    # code = graphene.Field(ClaimCodeInputType, required=True)
    # feedback = graphene.Field(FeedbackInputType, required=False)
    # guarantee_id = ClaimGuaranteeIdInputType(required=False)


@transaction.atomic
def update_or_create_claim_sampling_batch(data, user, task_group=None):

    service = ClaimSamplingService(user)

    if data.get('uuid', None) is not None:
        return service.update(data)
    else:
        claim_sampling_batch = service.create(data, task_group)
        return claim_sampling_batch


class CreateClaimSamplingBatchMutation(OpenIMISMutation):
    """
    Create a new claim sampling batch.
    """
    __filter_handlers = {
        'services': 'services__service__code__in',
        'items': 'items__item__code__in'
    }

    _mutation_module = "claim_sampling"
    _mutation_class = "CreateClaimSamplingBatchMutation"

    class Input(OpenIMISMutation.Input):
        filters = graphene.String()
        percentage = graphene.Int(required=True)
        taskGroupUuid = graphene.String(required=False)

    @classmethod
    @mutation_on_uuids_from_filter(Claim, ClaimGQLType, 'filters', __filter_handlers)
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError(_("mutation.authentication_required"))
            # if not user.has_perms(ClaimSamplingConfig.gql_mutation_create_claim_batch_samplings_perms):
            #     raise PermissionDenied(_("unauthorized"))
            if "client_mutation_id" in data:
                data.pop('client_mutation_id')
            if "client_mutation_label" in data:
                data.pop('client_mutation_label')
            # data['audit_user_id'] = user.id_for_audit
            from core.utils import TimeUtils
            # data['validity_from'] = TimeUtils.now()
            group_id = data.get('taskGroupUuid')

            task_group = TaskGroup.objects.get(id=group_id) if group_id else None
            claim_sampling_batch = update_or_create_claim_sampling_batch(data, user, task_group)
            return None
        except Exception as exc:
            from django.conf import settings
            if settings.DEBUG:
                import traceback
                logging.debug("Error in claim sampling mutation: ", exc)
                traceback.print_exc()
            return [{
                'message': _("claim.mutation.failed_to_create_claim_sampling_batch") % {'code': data['code']},
                'detail': str(exc)}]


class UpdateClaimSamplingBatchMutation(OpenIMISMutation):
    """
    Update a claim. The claim items and services can all be updated with this call
    """
    _mutation_module = "claim_sampling"
    _mutation_class = "UpdateClaimSamplingBatchMutation"

    class Input(ClaimSamplingBatchInputType):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError(
                    _("mutation.authentication_required"))
            if not user.has_perms(ClaimSamplingConfig.gql_mutation_update_claim_batch_samplings_perms):
                raise PermissionDenied(_("unauthorized"))
            data['audit_user_id'] = user.id_for_audit
            update_or_create_claim_sampling_batch(data, user)
            return None
        except Exception as exc:
            return [{
                'message': _("claim.mutation.failed_to_update_claim_sampling_batch") % {'code': data['code']},
                'detail': str(exc)}]


class ApproveClaimSamplingBatchMutation(OpenIMISMutation):
    """
    Approve given claim batch and apply deduction rate or other parameters across all claims in given batch.
    """
    _mutation_module = "claim_sampling"
    _mutation_class = "ApproveClaimSamplingBatchMutation"

    class Input(ClaimSamplingBatchInputType):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        if not user.has_perms(ClaimSamplingConfig.gql_mutation_approve_claim_batch_samplings_perms):
            raise PermissionDenied(_("unauthorized"))
        errors = []

        return errors
