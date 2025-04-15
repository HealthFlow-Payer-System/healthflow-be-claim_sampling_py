from graphql_jwt.shortcuts import get_token
from django.test import TestCase
from unittest import mock

from claim.services import ClaimSubmitService
from core.test_helpers import create_test_interactive_user, create_test_officer
from location.test_helpers import create_test_location, create_test_health_facility, create_test_village
from insuree.test_helpers import create_test_insuree
from claim.test_helpers import create_test_claim_admin, create_test_claim, mark_test_claim_as_processed
from claim.models import Claim, ClaimItem, ClaimService, ClaimDetail
from medical.models import Diagnosis, Item, Service
from medical.test_helpers import create_test_item, create_test_service
from django.conf import settings
from .models import (
    ClaimSamplingBatch,
    ClaimSamplingBatchAssignment,
    ClaimSamplingBatchAssignmentStatus
)

from .services import ClaimSamplingService
import core
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext as DummyContext

from graphene import Schema
from graphene_django.utils.testing import GraphQLTestCase
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
    schema = None

    test_claims = []


    @classmethod
    def setUpTestData(cls):
        cls.admin_user = create_test_interactive_user(username="testLocationAdmin")
        cls.admin_token = get_token(cls.admin_user, DummyContext(user=cls.admin_user))
        cls.schema = Schema(
            query=claim_schema.Query,
            mutation=claim_schema.Mutation
        )
        cls.graph_client = Client(cls.schema)

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
        cls.test_policy , ip = create_test_policy2(product, cls.test_insuree)
        cls.test_claim_admin = create_test_claim_admin()
        cls.test_icd = Diagnosis(code='ICD00I', name='diag test', audit_user_id=-1)
        cls.test_icd.save()

        cls._create_test_claims(cls.test_policy.product)
        

    @classmethod
    def _create_test_claims(cls, product):
        configdate = datetime.now() - timedelta(days=265)

        test_item = create_test_item(
            'D',
            custom_props={"code": "csamCo", "price": 1000 }
        )
        test_service = create_test_service(
            'D',
            custom_props={"code": "ssamCo", "price": 1000}
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
        add_service_to_hf_pricelist(test_service, hf_id=cls.test_hf.id)
        add_item_to_hf_pricelist(test_item, hf_id=cls.test_hf.id)
        
        dateclaim = date.today() - timedelta(days=5)
        datetimeclaim = datetime.now() - timedelta(days=5)
        for i in range(10):
            claim = Claim.objects.create(
                date_claimed=dateclaim,
                code=F"code_ABV{i}",
                icd=cls.test_icd,
                claimed=2000,
                date_from=dateclaim,
                date_to=None,
                admin=cls.test_claim_admin,
                insuree=cls.test_insuree,
                health_facility=cls.test_hf,
                status=Claim.STATUS_ENTERED,
                audit_user_id=-1,
                validity_from=datetimeclaim
            )
            claim_item = ClaimItem.objects.create(
                claim=claim,
                item=test_item,
                price_asked=1000,
                qty_provided=1,
                audit_user_id=-1,
                status=ClaimDetail.STATUS_PASSED,
                availability=True,
                validity_from=datetimeclaim
            )
            claim_service = ClaimService.objects.create(
                claim=claim,
                service=test_service,
                price_asked=1000,
                qty_provided=1,
                audit_user_id=-1,
                status=ClaimDetail.STATUS_PASSED,
                validity_from=datetimeclaim
            )
            claim.refresh_from_db()
            ClaimSubmitService(cls.admin_user).submit_claim(claim)
            cls.test_claims.append(claim)
        
    @classmethod
    def _set_claim_as_valuated(cls, claim, user, is_process=False):
        # Mock of dedrem
        claim.status = Claim.STATUS_PROCESSED
        claim.save()
        return []

    def test_mutation_create_claim( self):
        
        percentage_for_sample = 20
        mutation = f'''
mutation {{
  createClaimSamplingBatch(
    input: {{
      clientMutationId: "fdcc211f-7225-4f0e-8a66-11223344667d"
      clientMutationLabel: "Create Claim Sampling Batch" 
      percentage: 30
      filters: "{{\\"status\\":4, \\"dateFrom\\": \\"{date.today() - timedelta(days=5)}\\"}}"        
    }}      
  ) {{
    clientMutationId
    internalId
  }}    
}}
            '''
        response = self.send_mutation_raw(mutation,self.admin_token )
        

        claim_sampling = ClaimSamplingBatch.objects.first()
        self.assertIsNotNone(claim_sampling)

        attachments = ClaimSamplingBatchAssignment.objects.filter(claim_batch=claim_sampling)
        # Ten claims, 2 should be assigned for sample idle and 8 for skip;
        idle = list(attachments.filter(status=ClaimSamplingBatchAssignmentStatus.IDLE))
        skip = list(attachments.filter(status=ClaimSamplingBatchAssignmentStatus.SKIPPED))

        # Creation
        self.assertEqual(len(idle), 3)
        self.assertEqual(len(skip), 7)
        self.assertEqual(idle[0].claim.review_status, Claim.REVIEW_SELECTED)
        self.assertEqual(idle[1].claim.review_status, Claim.REVIEW_SELECTED)
        self.assertEqual(idle[2].claim.review_status, Claim.REVIEW_SELECTED)

        # Summary
        claim_1, claim_2, claim_3 = idle[0].claim, idle[1].claim, idle[2].claim
        claim_1.review_status = Claim.REVIEW_DELIVERED
        claim_1.status = Claim.STATUS_PROCESSED
        claim_1.save()

        claim_2.review_status = Claim.REVIEW_DELIVERED
        claim_2.status = Claim.STATUS_REJECTED
        claim_2.save()

        claim_3.review_status = Claim.REVIEW_DELIVERED
        claim_3.status = Claim.STATUS_REJECTED
        claim_3.save()

        service = ClaimSamplingService(self.admin_user)
        rejected_from_review, reviewed_delivered, total = service.prepare_sampling_summary(claim_sampling.id)
        self.assertEqual(rejected_from_review.count(), 2)
        self.assertEqual(reviewed_delivered.count(), 3)
        self.assertEqual(total, 3)
        datetimeclaim = datetime.now() - timedelta(days=5)

        # Extrapolation
        service.extrapolate_results(claim_sampling.id)
        attachments = ClaimSamplingBatchAssignment.objects.filter(claim_batch=claim_sampling)
        # 50% of remaining claims should be rejected and 50% should be valuated
        skip = [x.claim for x in attachments.filter(status=ClaimSamplingBatchAssignmentStatus.SKIPPED)]
        accepted = [x for x in skip if x.status in [ Claim.STATUS_PROCESSED, Claim.STATUS_VALUATED]]
        rejected = [x for x in skip if x.status in [Claim.STATUS_REJECTED]]
        self.assertEqual(len(accepted), 7)
        self.assertEqual(len(rejected), 0)
        
        # FIXME check the ratio (done manually looks ok)
        

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
