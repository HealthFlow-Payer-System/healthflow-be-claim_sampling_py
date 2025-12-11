
from core.schema import OrderedDjangoFilterConnectionField
from django.conf import settings
from claim_sampling.gql_queries import ClaimSamplingSummaryGQLType, ClaimSamplingBatchGQLType, ClaimSamplingBatchAssignmentGQLType
from django.utils.translation import gettext as _
from claim_sampling.gql_mutations import CreateClaimSamplingBatchMutation, UpdateClaimSamplingBatchMutation, ApproveClaimSamplingBatchMutation
import graphene
from claim_sampling.models import ClaimSamplingBatch, ClaimSamplingBatchAssignment
from claim.models import Claim
from .apps import ClaimSamplingConfig
from tasks_management.models import Task
from rest_framework.exceptions import PermissionDenied
from claim.gql_queries import ClaimGQLType
from .services import ClaimSamplingService


class Query(graphene.ObjectType):
    claim_sampling_batch = OrderedDjangoFilterConnectionField(
        ClaimSamplingBatchGQLType,
        id=graphene.Int(required=True)
    )

    claim_sampling_batch_assignment = graphene.Field(
        ClaimSamplingBatchAssignmentGQLType,
        id=graphene.Int(required=True)
    )

    sampling_batch_claims = OrderedDjangoFilterConnectionField(
        ClaimGQLType,
        claim_sampling_id=graphene.UUID(required=True),
        assignment_status=graphene.String()
    )

    sampling_summary = graphene.Field(
        ClaimSamplingSummaryGQLType,
        task_id=graphene.String(required=True),
        description="Provide details regarding claim sampling assigned to specific task."
    )

    def resolve_claim_sampling_batch(self, info, **kwargs):
        if (
            not info.context.user.has_perms(ClaimSamplingConfig.gql_query_claim_batch_samplings_perms)
            and settings.ROW_SECURITY
        ):
            raise PermissionDenied(_("unauthorized"))

        claim_sampling_batch_id = kwargs.get("id", None)

        return ClaimSamplingBatch.objects.get(id=claim_sampling_batch_id, validity_to__isnull=True)

    def resolve_claim_sampling_batch_assignment(self, info, **kwargs):
        if (
            not info.context.user.has_perms(ClaimSamplingConfig.gql_query_claim_batch_samplings_perms)
            and settings.ROW_SECURITY
        ):
            raise PermissionDenied(_("unauthorized"))

        claim_sampling_batch_assignment_id = kwargs.get("id", None)

        return ClaimSamplingBatchAssignment.objects.get(id=claim_sampling_batch_assignment_id, validity_to__isnull=True)

    def resolve_sampling_batch_claims(self, info, **kwargs):
        if (
            not info.context.user.has_perms(ClaimSamplingConfig.gql_query_claim_batch_samplings_perms)
            and settings.ROW_SECURITY
        ):
            raise PermissionDenied(_("unauthorized"))

        sampling = ClaimSamplingBatch.objects.get(uuid=kwargs['claim_sampling_id'])
        relevant_claims = ClaimSamplingBatchAssignment.objects.filter(claim_batch=sampling)

        claim_assignment_status = kwargs.get('assignment_status')

        if claim_assignment_status:
            relevant_claims = relevant_claims.filter(status=claim_assignment_status)

        # All claims are displayed but
        query = Claim.objects.filter(
            id__in=relevant_claims.values_list('claim_id', flat=True),
            validity_to__isnull=True  # Ensuring that only valid (non-expired) claims are returned
        ).order_by('status')

        return query

    def resolve_sampling_summary(self, info, **kwargs):
        if not info.context.user.has_perms(ClaimSamplingConfig.gql_query_claim_batch_samplings_perms):
            raise PermissionDenied(_("unauthorized"))

        try:
            task_id = kwargs['task_id']
            task = Task.objects.get(id=task_id)
            claim_sampling_id = task.data['data']['uuid']

            claim_sampling_service = ClaimSamplingService(user=info.context.user)
            rejected_from_review, reviewed_delivered, total = claim_sampling_service.prepare_sampling_summary(
                claim_sampling_id)

            review_delivered = round(reviewed_delivered.count() / total, 2) * 100
            percentage = round(rejected_from_review.count() / total, 2) * 100

            return ClaimSamplingSummaryGQLType(
                deductible_percentage=percentage,
                reviewed_percentage=review_delivered,
                total_claims_in_batch=total
            )
        except Exception as e:
            if settings.DEBUG:
                import traceback
                traceback.print_exc()
            raise e


class Mutation(graphene.ObjectType):
    create_claim_sampling_batch = CreateClaimSamplingBatchMutation.Field()
    update_claim_sampling_batch = UpdateClaimSamplingBatchMutation.Field()
    approve_claim_sampling_batch = ApproveClaimSamplingBatchMutation.Field()
