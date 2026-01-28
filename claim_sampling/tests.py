import uuid
from claim.services import processing_claim, ClaimSubmitService
from core.test_helpers import create_test_interactive_user, create_test_officer
from location.test_helpers import create_test_health_facility, create_test_village
from insuree.test_helpers import create_test_insuree
from claim.test_helpers import create_test_claim_admin
from claim.models import Claim, ClaimItem, ClaimService, ClaimDetail
from medical.models import Diagnosis
from medical.test_helpers import create_test_item, create_test_service
from django.conf import settings
from .models import (
    ClaimSamplingBatch,
    ClaimSamplingBatchAssignment,
    ClaimSamplingBatchAssignmentStatus
)
import random
from .services import ClaimSamplingService
import core
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from django.db.models import (
    Q, Sum, ExpressionWrapper, DecimalField
)
from claim.subqueries import (
    total_srv_adjusted_exp,
    total_itm_adjusted_exp,
    total_srv_approved_exp,
    total_itm_approved_exp
)

from graphene import Schema
from claim_sampling import schema as claim_schema
from graphene.test import Client
from policy.test_helpers import create_test_policy2
from product.test_helpers import create_test_product, create_test_product_service, create_test_product_item
from medical_pricelist.test_helpers import add_service_to_hf_pricelist, add_item_to_hf_pricelist
from product.models import ProductItemOrService
from datetime import date, timedelta, datetime


class ClaimSubmitServiceTestCase(openIMISGraphQLTestCase):
    GRAPHQL_URL = f'/{settings.SITE_ROOT()}graphql'
    # This is required by some version of graphene but is never used. It should be set to the schema but the import
    # is shown as an error in the IDE, so leaving it as True.
    GRAPHQL_SCHEMA = True

    test_hf = None

    test_insuree = None
    test_claim_admin = None
    test_icd = None
    test_claim = None
    test_claim_item = None
    test_claim_service = None
    test_region = None
    test_district = None
    test_village = None
    test_ward = None

    admin_user = None
    admin_token = None
    schema = None

    test_claims = []

    def tearDown(self):
        # atomic rollback issue is teardown is called
        pass

    @classmethod
    def tearDownClass(cls):
        # atomic rollback issue is teardown is called
        pass

    @classmethod
    def setUpClass(cls):
        
        cls.dateclaimed = date.today() - timedelta(days=5)
        cls.datetimeclaimed = datetime.now() - timedelta(days=5)
        cls.datestart = date.today() - timedelta(days=55)
        cls.schema = Schema(
            query=claim_schema.Query,
            mutation=claim_schema.Mutation
        )
        cls.graph_client = Client(cls.schema)
        cls.admin_user = create_test_interactive_user(username="testLocationAdmin")
        cls.admin_context = BaseTestContext(user=cls.admin_user)
        cls.admin_token = BaseTestContext(user=cls.admin_user).get_jwt()
        cls.officer = create_test_officer(custom_props={"code": "TSTSIMP1"})

        if cls.test_region is None:
            cls.test_village = create_test_village()
            cls.test_ward = cls.test_village.parent
            cls.test_region = cls.test_village.parent.parent.parent
            cls.test_district = cls.test_village.parent.parent

        cls.test_hf = create_test_health_facility("1", cls.test_district.id, valid=True)
        props = dict(
            last_name="name",
            other_names="surname",
            dob=core.datetime.date(2000, 1, 13),
            chf_id="884930485",
        )
        family_props = dict(
            location=cls.test_village,
        )
        cls.test_insuree = create_test_insuree(is_head=True, custom_props=props, family_custom_props=family_props)
        product = create_test_product("TEST_CLM")
        cls.test_policy, ip = create_test_policy2(
            product,
            cls.test_insuree,
            custom_props={
                "enroll_date": cls.datestart,
                "start_date": cls.datestart,
                "validity_from": cls.datestart,
                "effective_date": cls.datestart,
            })
        cls.test_claim_admin = create_test_claim_admin()
        cls.test_icd = Diagnosis(code='ICD00I', name='diag test', audit_user_id=-1)
        cls.test_icd.save()


    def _create_test_claims(self, product, nbr_claims=10):
        test_item = create_test_item(
            'D',
            custom_props={"code": "TI-001", "price": 1000}
        )
        test_service = create_test_service(
            'D',
            custom_props={"code": "TS-001", "price": 1000}
        )
        create_test_product_service(
            product,
            test_service,
            custom_props={"price_origin": ProductItemOrService.ORIGIN_RELATIVE},
        )
        create_test_product_item(
            product,
            test_item,
            custom_props={"price_origin": ProductItemOrService.ORIGIN_RELATIVE},
        )
        add_service_to_hf_pricelist(test_service, hf_id=self.test_hf.id)
        add_item_to_hf_pricelist(test_item, hf_id=self.test_hf.id)

        for i in range(nbr_claims):
            claim = Claim.objects.create(
                date_claimed=self.dateclaimed,
                code=F"code_ABV{i}",
                icd=self.test_icd,
                claimed=2000,
                date_from=self.dateclaimed,
                date_to=None,
                admin=self.test_claim_admin,
                insuree=self.test_insuree,
                health_facility=self.test_hf,
                status=Claim.STATUS_ENTERED,
                audit_user_id=-1,
                validity_from=self.datetimeclaimed
            )
            ClaimItem.objects.create(
                claim=claim,
                item=test_item,
                price_asked=1000,
                qty_provided=1,
                audit_user_id=-1,
                status=ClaimDetail.STATUS_PASSED,
                availability=True,
                validity_from=self.datetimeclaimed
            )
            ClaimService.objects.create(
                claim=claim,
                service=test_service,
                price_asked=1000,
                qty_provided=1,
                audit_user_id=-1,
                status=ClaimDetail.STATUS_PASSED,
                validity_from=self.datetimeclaimed
            )
            ClaimSubmitService(self.admin_user).submit_claim(claim)
            processing_claim(claim, self.admin_user, False)
            claim.refresh_from_db()
            self.test_claims.append(claim)

    @classmethod
    def _set_claim_as_valuated(cls, claim, user, is_process=False):
        # Mock of dedrem
        claim.status = Claim.STATUS_PROCESSED
        claim.save()
        return []

    def test_mutation_create_claim(self):
        self._create_test_claims(self.test_policy.product, nbr_claims=10)
        percentage_for_sample = 30
        mutation = f'''
mutation {{
  createClaimSamplingBatch(
    input: {{
      clientMutationId: "{str(uuid.uuid4())}"
      clientMutationLabel: "Create Claim Sampling Batch"
      percentage: {percentage_for_sample}
      filters: "{{\\"status\\":4, \\"dateClaimed\\": \\"{self.dateclaimed}\\"}}"
    }}
  ) {{
    clientMutationId
    internalId
  }}
}}'''
        self.send_mutation_raw(mutation, self.admin_token)

        claim_sampling = ClaimSamplingBatch.objects.first()
        self.assertIsNotNone(claim_sampling)

        attachments = ClaimSamplingBatchAssignment.objects.filter(claim_batch=claim_sampling)
        # Ten claims, 2 should be assigned for sample idle and 8 for skip;
        idle = list(attachments.filter(status=ClaimSamplingBatchAssignmentStatus.IDLE))
        skip = list(attachments.filter(status=ClaimSamplingBatchAssignmentStatus.SKIPPED))

        # Creation
        percentage_expected = round(percentage_for_sample * len(attachments) / 100)
        self.assertEqual(len(idle), percentage_expected)
        self.assertEqual(len(skip), len(attachments) - percentage_expected)
        self.assertEqual(idle[0].claim.review_status, Claim.REVIEW_SELECTED)
        self.assertEqual(idle[1].claim.review_status, Claim.REVIEW_SELECTED)
        self.assertEqual(idle[2].claim.review_status, Claim.REVIEW_SELECTED)
        status = [Claim.STATUS_PROCESSED, Claim.STATUS_REJECTED]
        rejected = 0
        # Summary
        for sclaim in idle:
            claim, = sclaim.claim,
            claim.review_status = Claim.REVIEW_DELIVERED
            claim.status = random.choices(status)[0]
            if claim.status == Claim.STATUS_REJECTED:
                rejected += 1
            claim.save()

        service = ClaimSamplingService(self.admin_user)
        rejected_from_review, reviewed_delivered, total = service.prepare_sampling_summary(claim_sampling.id)
        self.assertEqual(rejected_from_review.count(), rejected)
        self.assertEqual(reviewed_delivered.count(), len(idle))
        self.assertEqual(total, len(idle))
        qs = Claim.objects.filter(assignments__claim_batch=claim_sampling, *Claim.filter_validity())

        ratio_before = qs.filter(review_status=Claim.REVIEW_DELIVERED)\
            .filter(Q(services__rejection_reason__lte=0) | Q(services__rejection_reason__isnull=True))\
            .annotate(total_srv_adjusted=total_srv_adjusted_exp)\
            .annotate(total_itm_adjusted=total_itm_adjusted_exp)\
            .annotate(total_srv_approved=total_srv_approved_exp)\
            .annotate(total_itm_approved=total_itm_approved_exp)\
            .aggregate(value=ExpressionWrapper(
                (Sum("total_srv_approved") + Sum("total_itm_approved")) /
                (Sum("total_srv_adjusted") + Sum("total_itm_adjusted")),
                output_field=DecimalField()
            ))["value"]

        # Extrapolation
        service.extrapolate_results(claim_sampling.id)
        attachments = ClaimSamplingBatchAssignment.objects.filter(claim_batch=claim_sampling)
        # 50% of remaining claims should be rejected and 50% should be valuated
        skip = [x.claim for x in attachments.filter(status=ClaimSamplingBatchAssignmentStatus.SKIPPED)]
        accepted = [x for x in skip if x.status in [Claim.STATUS_PROCESSED, Claim.STATUS_VALUATED]]
        rejected = [x for x in skip if x.status in [Claim.STATUS_REJECTED]]
        self.assertEqual(len(accepted), len(skip))
        self.assertEqual(len(rejected), 0)

        qs = Claim.objects.filter(assignments__claim_batch=claim_sampling, *Claim.filter_validity())

        ratio_after = qs.filter(review_status=Claim.REVIEW_DELIVERED)\
            .filter(Q(services__rejection_reason__lte=0) | Q(services__rejection_reason__isnull=True))\
            .annotate(total_srv_adjusted=total_srv_adjusted_exp)\
            .annotate(total_itm_adjusted=total_itm_adjusted_exp)\
            .annotate(total_srv_approved=total_srv_approved_exp)\
            .annotate(total_itm_approved=total_itm_approved_exp)\
            .aggregate(value=ExpressionWrapper(
                (Sum("total_srv_approved") + Sum("total_itm_approved")) /
                (Sum("total_srv_adjusted") + Sum("total_itm_adjusted")),
                output_field=DecimalField()
            ))["value"]
        self.assertEqual(ratio_before, ratio_after)

    def _get_test_dict(self, code=None):
        return {
            "health_facility_id": self.test_claim.health_facility_id,
            "icd_id": self.test_icd.id,
            "date_from": self.test_claim.date_from,
            "code": self.test_claim.code if code is None else code,
            "date_claimed": self.test_claim.date_claimed,
            "date_to": self.test_claim.date_to,
            "audit_user_id": self.test_claim.audit_user_id,
            "insuree_id": self.test_claim.insuree_id,
            "status": self.test_claim.status,
            "validity_from": self.test_claim.validity_from,
            "items": [{
                "qty_provided": self.test_claim_item.qty_provided,
                "price_asked": self.test_claim_item.price_asked,
                "item_id": self.test_claim_item.item_id,
                "status": self.test_claim_item.status,
                "availability": self.test_claim_item.availability,
                "validity_from": self.test_claim_item.validity_from,
                "validity_to": self.test_claim_item.validity_to,
                "audit_user_id": self.test_claim_item.audit_user_id
            }],
            "services": [{
                "qty_provided": self.test_claim_service.qty_provided,
                "price_asked": self.test_claim_service.price_asked,
                "service_id": self.test_claim_service.service_id,
                "status": self.test_claim_service.status,
                "validity_from": self.test_claim_service.validity_from,
                "validity_to": self.test_claim_service.validity_to,
                "audit_user_id": self.test_claim_service.audit_user_id
            }]
        }
