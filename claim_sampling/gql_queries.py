import graphene
from core import ExtendedConnection
from graphene_django import DjangoObjectType
from .apps import ClaimSamplingConfig
from .models import Claim
from django.utils.translation import gettext as _
from django.core.exceptions import PermissionDenied


class ClaimSamplingBatchGQLType(DjangoObjectType):
    attachments_count = graphene.Int()
    client_mutation_id = graphene.String()

    class Meta:
        model = Claim
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "uuid": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "status": ["exact", "gt"],
            "date_claimed": ["exact", "lt", "lte", "gt", "gte"],
            "date_from": ["exact", "lt", "lte", "gt", "gte"],
            "date_to": ["exact", "lt", "lte", "gt", "gte"],
            "date_processed": ["exact", "lt", "lte", "gt", "gte"],
            "feedback_status": ["exact"],
            "review_status": ["exact"],
            "claimed": ["exact", "lt", "lte", "gt", "gte"],
            "approved": ["exact", "lt", "lte", "gt", "gte"],
            "visit_type": ["exact"],
            "attachments_count__value": ["exact", "lt", "lte", "gt", "gte"],
        }
        connection_class = ExtendedConnection

    def resolve_client_mutation_id(self, info):
        if not info.context.user.has_perms(ClaimSamplingConfig.gql_query_claim_batch_samplings_perms):
            raise PermissionDenied(_("unauthorized"))
        claim_mutation = self.mutations.select_related(
            'mutation').filter(mutation__status=0).first()
        return claim_mutation.mutation.client_mutation_id if claim_mutation else None

    @classmethod
    def get_queryset(cls, queryset, info):
        claim_ids = Claim.get_queryset(queryset, info).values('uuid').all()
        return Claim.objects.filter(uuid__in=claim_ids)


class ClaimSamplingBatchAssignmentGQLType(DjangoObjectType):
    """
    Main element for a Claim. It can contain items and/or services.
    The filters are possible on BatchRun, Insuree, HealthFacility, Admin and ICD in addition to the Claim fields
    themselves.
    """

    class Meta:
        model = Claim
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "uuid": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "status": ["exact", "gt"],
            "date_claimed": ["exact", "lt", "lte", "gt", "gte"],
            "date_from": ["exact", "lt", "lte", "gt", "gte"],
            "date_to": ["exact", "lt", "lte", "gt", "gte"],
            "date_processed": ["exact", "lt", "lte", "gt", "gte"],
            "feedback_status": ["exact"],
            "review_status": ["exact"],
            "claimed": ["exact", "lt", "lte", "gt", "gte"],
            "approved": ["exact", "lt", "lte", "gt", "gte"],
            "visit_type": ["exact"],
            "attachments_count__value": ["exact", "lt", "lte", "gt", "gte"],
        }
        connection_class = ExtendedConnection


class ClaimSamplingSummaryGQLType(graphene.ObjectType):
    deductible_percentage = graphene.Float(description="Percentage of claims rejected during review - deductibles.")
    reviewed_percentage = graphene.Float(description="Percentage of reviewed claims in batch.")
    total_claims_in_batch = graphene.Int(description="Total number of claims selected for review in sampling batch")
