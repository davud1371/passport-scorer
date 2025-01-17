import datetime

import pytest
from account.models import Account, AccountAPIKey, Community
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from registry.api.v1 import get_scorer_by_id
from registry.models import Passport, Score
from web3 import Web3

User = get_user_model()
web3 = Web3()
web3.eth.account.enable_unaudited_hdwallet_features()
my_mnemonic = settings.TEST_MNEMONIC

pytestmark = pytest.mark.django_db


@pytest.fixture
def paginated_scores(scorer_passport, passport_holder_addresses, scorer_community):
    scores = []
    i = 0
    for holder in passport_holder_addresses:
        passport = Passport.objects.create(
            address=holder["address"],
            community=scorer_community,
        )

        score = Score.objects.create(
            passport=passport,
            score="1",
            last_score_timestamp=datetime.datetime.now()
            + datetime.timedelta(days=i + 1),
        )

        scores.append(score)
        i += 1
    return scores


class TestPassportGetScore:
    def test_get_scores_with_valid_community_with_no_scores(
        self, scorer_api_key, scorer_account
    ):
        additional_community = Community.objects.create(
            name="My Community",
            description="My Community description",
            account=scorer_account,
        )

        client = Client()
        response = client.get(
            f"/registry/score/{additional_community.pk}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200
        assert len(response_data["items"]) == 0

    def test_get_scores_returns_first_page_scores_v1(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        offset = 0
        limit = 2

        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?limit={limit}&offset={offset}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200

        for i in range(0, 1):
            assert (
                response_data["items"][i]["address"]
                == passport_holder_addresses[offset + i]["address"].lower()
            )

    def test_get_scores_returns_second_page_scores_v1(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        offset = 2
        limit = 2

        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?limit={limit}&offset={offset}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200

        for i in range(0, 2):
            assert (
                response_data["items"][i]["address"]
                == passport_holder_addresses[offset + i]["address"].lower()
            )

    def test_get_scores_returns_paginated_and_pk_sorted_response(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        request_params = [[0, 3], [3, 5]]

        for offset, limit in request_params:
            # Get the PKs of the scores we are expecting
            expected_pks = [
                score.pk for score in paginated_scores[offset : offset + limit]
            ]

            client = Client()
            response = client.get(
                f"/registry/score/{scorer_community.id}?limit={limit}&offset={offset}",
                HTTP_AUTHORIZATION="Token " + scorer_api_key,
            )
            response_data = response.json()

            assert response.status_code == 200
            returned_pks = [
                Score.objects.filter(passport__address=item["address"]).get().pk
                for item in response_data["items"]
            ]

            assert expected_pks == returned_pks

    def test_get_scores_returns_paginated_and_datetime_sorted_response(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        request_params = [[0, 3], [3, 5]]

        for offset, limit in request_params:
            # Get the PKs of the scores we are expecting
            sorted_scores = sorted(
                paginated_scores,
                key=lambda score: score.last_score_timestamp,
            )
            expected_pks = [
                score.pk for score in sorted_scores[offset : offset + limit]
            ]

            client = Client()
            response = client.get(
                f"/registry/score/{scorer_community.id}?limit={limit}&offset={offset}&order_by=last_score_timestamp",
                HTTP_AUTHORIZATION="Token " + scorer_api_key,
            )
            response_data = response.json()

            assert response.status_code == 200
            returned_pks = [
                Score.objects.filter(passport__address=item["address"]).get().pk
                for item in response_data["items"]
            ]

            assert expected_pks == returned_pks

    def test_get_scores_returns_first_page_scores_v2(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        limit = 2

        client = Client()
        response = client.get(
            f"/registry/v2/score/{scorer_community.id}?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200
        assert response_data["prev"] == None

        next_page = client.get(
            response_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert next_page.status_code == 200

        for i in range(limit):
            assert (
                response_data["items"][i]["address"]
                == passport_holder_addresses[i]["address"].lower()
            )

    def test_get_scores_returns_second_page_scores_v2(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        limit = 2

        client = Client()
        page_one_response = client.get(
            f"/registry/v2/score/{scorer_community.id}?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        page_one_data = page_one_response.json()

        assert page_one_response.status_code == 200

        page_two_response = client.get(
            page_one_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        page_two_data = page_two_response.json()

        assert page_two_response.status_code == 200

        page_two_prev = client.get(
            page_two_data["prev"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert page_two_prev.status_code == 200
        assert page_two_prev.json() == page_one_data

        for i in range(limit):
            assert (
                page_two_data["items"][i]["address"]
                == passport_holder_addresses[i + limit]["address"].lower()
            )

    def test_get_scores_request_throws_400_for_invalid_community(self, scorer_api_key):
        client = Client()
        response = client.get(
            f"/registry/score/3",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        # assert response.status_code == 404
        assert response.json() == {
            "detail": "No Community matches the given query.",
        }

    def test_get_single_score_for_address(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?address={passport_holder_addresses[0]['address']}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

        assert (
            response.json()["items"][0]["address"]
            == passport_holder_addresses[0]["address"].lower()
        )

    def test_get_scores_filter_by_last_score_timestamp__gt(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        scores = list(Score.objects.all())
        middle = len(scores) // 2
        older_scores = scores[:middle]
        newer_scores = scores[middle:]
        now = datetime.datetime.now()
        past_time_stamp = now - datetime.timedelta(days=1)
        future_time_stamp = now + datetime.timedelta(days=1)

        # Make sure we have sufficient data in both queries
        assert len(newer_scores) >= 2
        assert len(older_scores) >= 2

        for score in older_scores:
            score.last_score_timestamp = past_time_stamp
            score.save()

        # The first score will have a last_score_timestamp equal to the value we filter by
        for idx, score in enumerate(newer_scores):
            if idx == 0:
                score.last_score_timestamp = now
            else:
                score.last_score_timestamp = future_time_stamp
            score.save()

        # Check the query when the filtered timestamo equals a score last_score_timestamp
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?last_score_timestamp__gt={now.isoformat()}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == len(newer_scores) - 1

        # Check the query when the filtered timestamo does not equal a score last_score_timestamp
        response = client.get(
            f"/registry/score/{scorer_community.id}?last_score_timestamp__gt={(now - datetime.timedelta(milliseconds=1)).isoformat()}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == len(newer_scores)

    def test_get_scores_filter_by_last_score_timestamp__gte(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        scores = list(Score.objects.all())
        middle = len(scores) // 2
        older_scores = scores[:middle]
        newer_scores = scores[middle:]
        now = datetime.datetime.now()
        past_time_stamp = now - datetime.timedelta(days=1)
        future_time_stamp = now + datetime.timedelta(days=1)

        # Make sure we have sufficient data in both queries
        assert len(newer_scores) >= 2
        assert len(older_scores) >= 2

        for score in older_scores:
            score.last_score_timestamp = past_time_stamp
            score.save()

        # The first score will have a last_score_timestamp equal to the value we filter by
        for idx, score in enumerate(newer_scores):
            if idx == 0:
                score.last_score_timestamp = now
            else:
                score.last_score_timestamp = future_time_stamp
            score.save()

        # Check the query when the filtered timestamo equals a score last_score_timestamp
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?last_score_timestamp__gte={now.isoformat()}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == len(newer_scores)

        # Check the query when the filtered timestamo does not equal a score last_score_timestamp
        response = client.get(
            f"/registry/score/{scorer_community.id}?last_score_timestamp__gte={(now - datetime.timedelta(milliseconds=1)).isoformat()}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == len(newer_scores)

    def test_get_single_score_for_address_in_path(
        self,
        scorer_api_key,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}/{passport_holder_addresses[0]['address']}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        assert response.status_code == 200

        assert (
            response.json()["address"]
            == passport_holder_addresses[0]["address"].lower()
        )

    def test_cannot_get_single_score_for_address_in_path_for_other_community(
        self,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        """
        Test that a user can't get scores for a community they don't belong to.
        """
        # Create another user, account & api key
        user = User.objects.create_user(username="anoter-test-user", password="12345")
        web3_account = web3.eth.account.from_mnemonic(
            my_mnemonic, account_path="m/44'/60'/0'/0/0"
        )

        account = Account.objects.create(user=user, address=web3_account.address)
        (_, api_key) = AccountAPIKey.objects.create_key(
            account=account,
            name="Token for user 1",
        )

        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}/{passport_holder_addresses[0]['address']}",
            HTTP_AUTHORIZATION="Token " + api_key,
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "No Community matches the given query."}

    def test_limit_greater_than_1000_throws_an_error(
        self, scorer_community, passport_holder_addresses, scorer_api_key
    ):
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?limit=1001",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert response.status_code == 400
        assert response.json() == {
            "detail": "Invalid limit.",
        }

    def test_limit_of_1000_is_ok(
        self, scorer_community, passport_holder_addresses, scorer_api_key
    ):
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?limit=1000",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert response.status_code == 200

    def test_get_single_score_for_address_without_permissions(
        self,
        passport_holder_addresses,
        scorer_community,
        scorer_api_key_no_permissions,
    ):
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}/{passport_holder_addresses[0]['address']}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key_no_permissions,
        )
        assert response.status_code == 403

    def test_get_single_score_by_scorer_id_without_permissions(
        self,
        scorer_community,
        scorer_api_key_no_permissions,
    ):
        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key_no_permissions,
        )
        assert response.status_code == 403

    def test_cannot_get_score_for_other_community(self, scorer_community):
        """Test that a user can't get scores for a community they don't belong to."""
        # Create another user, account & api key
        user = User.objects.create_user(username="anoter-test-user", password="12345")
        web3_account = web3.eth.account.from_mnemonic(
            my_mnemonic, account_path="m/44'/60'/0'/0/0"
        )

        account = Account.objects.create(user=user, address=web3_account.address)
        (_, api_key) = AccountAPIKey.objects.create_key(
            account=account,
            name="Token for user 1",
        )

        client = Client()
        response = client.get(
            f"/registry/score/{scorer_community.id}?limit=1000",
            HTTP_AUTHORIZATION="Token " + api_key,
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "No Community matches the given query."}

    def test_get_scores_request_throws_403_for_non_researcher(self, scorer_api_key):
        client = Client()
        response = client.get(
            f"/analytics/score/",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        assert response.status_code == 403
        assert response.json() == {
            "detail": "You are not allowed to access this endpoint.",
        }

    def test_get_first_page_scores_for_researcher(
        self,
        scorer_api_key,
        scorer_account,
        passport_holder_addresses,
        paginated_scores,
    ):
        group, _ = Group.objects.get_or_create(name="Researcher")
        scorer_account.user.groups.add(group)

        limit = 2

        client = Client()
        response = client.get(
            f"/analytics/score/?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        response_data = response.json()

        assert response.status_code == 200
        assert response_data["prev"] == None

        next_page = client.get(
            response_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert next_page.status_code == 200

        for i in range(limit):
            assert (
                response_data["items"][i]["address"]
                == passport_holder_addresses[i]["address"].lower()
            )

    def test_get_second_page_scores_for_researcher(
        self,
        scorer_api_key,
        scorer_account,
        passport_holder_addresses,
        paginated_scores,
    ):
        group, _ = Group.objects.get_or_create(name="Researcher")
        scorer_account.user.groups.add(group)

        limit = 2

        client = Client()
        page_one_response = client.get(
            f"/analytics/score/?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        page_one_data = page_one_response.json()

        assert page_one_response.status_code == 200

        page_two_response = client.get(
            page_one_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        page_two_data = page_two_response.json()

        assert page_two_response.status_code == 200

        page_two_prev = client.get(
            page_two_data["prev"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert page_two_prev.status_code == 200
        assert page_two_prev.json() == page_one_data

        for i in range(limit):
            assert (
                page_two_data["items"][i]["address"]
                == passport_holder_addresses[i + limit]["address"].lower()
            )

    def test_get_last_page_scores_for_researcher(
        self,
        scorer_api_key,
        scorer_account,
        passport_holder_addresses,
        paginated_scores,
    ):
        group, _ = Group.objects.get_or_create(name="Researcher")
        scorer_account.user.groups.add(group)

        num_scores = len(paginated_scores)  # 5

        limit = int(num_scores / 2)  # 2

        # [1, 2], [3, 4], [5]
        client = Client()

        # Read the 1st batch
        response = client.get(
            f"/analytics/score/?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200
        assert len(response_data["items"]) == limit
        assert len(response_data["next"]) != None

        # Read the 2nd batch
        response = client.get(
            response_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        # Read the 3rd batch
        response = client.get(
            response_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200
        assert len(response_data["items"]) == 1
        assert response_data["next"] == None

    def test_get_first_page_scores_by_community_id_for_researcher(
        self,
        scorer_api_key,
        scorer_account,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        group, _ = Group.objects.get_or_create(name="Researcher")
        scorer_account.user.groups.add(group)

        limit = 2

        client = Client()
        response = client.get(
            f"/analytics/score/{scorer_community.id}?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200
        assert response_data["prev"] == None

        next_page = client.get(
            response_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert next_page.status_code == 200

        for i in range(limit):
            assert (
                response_data["items"][i]["address"]
                == passport_holder_addresses[i]["address"].lower()
            )

    def test_get_second_page_scores_by_community_id_for_researcher(
        self,
        scorer_api_key,
        scorer_account,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        group, _ = Group.objects.get_or_create(name="Researcher")
        scorer_account.user.groups.add(group)

        limit = 2

        client = Client()
        page_one_response = client.get(
            f"/analytics/score/{scorer_community.id}?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        page_one_data = page_one_response.json()

        assert page_one_response.status_code == 200

        page_two_response = client.get(
            page_one_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        page_two_data = page_two_response.json()

        assert page_two_response.status_code == 200

        page_two_prev = client.get(
            page_two_data["prev"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )

        assert page_two_prev.status_code == 200
        assert page_two_prev.json() == page_one_data

        for i in range(limit):
            assert (
                page_two_data["items"][i]["address"]
                == passport_holder_addresses[i + limit]["address"].lower()
            )

    def test_get_last_page_scores_by_community_id_for_researcher(
        self,
        scorer_api_key,
        scorer_account,
        passport_holder_addresses,
        scorer_community,
        paginated_scores,
    ):
        """
        We will try reading all scores in 2 request (2 batches). We expect the next link after the 1st page to be valid,
        and the second page to be null.
        """
        group, _ = Group.objects.get_or_create(name="Researcher")
        scorer_account.user.groups.add(group)

        num_scores = len(paginated_scores)

        limit = int(num_scores / 2)
        client = Client()

        # Read the 1st batch
        response = client.get(
            f"/analytics/score/{scorer_community.id}?limit={limit}",
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200
        assert len(response_data["items"]) == limit
        assert len(response_data["next"]) != None

        # Read the 2nd batch
        response = client.get(
            response_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        # Read the 3rd batch
        response = client.get(
            response_data["next"],
            HTTP_AUTHORIZATION="Token " + scorer_api_key,
        )
        response_data = response.json()

        assert response.status_code == 200
        assert len(response_data["items"]) == 1
        assert response_data["next"] == None

    def test_get_scorer_by_id(self, scorer_account):
        scorer = Community.objects.create(
            name="The Scorer",
            description="A great scorer",
            account=scorer_account,
            external_scorer_id="scorer1",
        )

        result = get_scorer_by_id(scorer.pk, scorer_account)

        assert result == scorer

    def test_get_scorer_by_external_id(self, scorer_account):
        scorer = Community.objects.create(
            name="The Scorer",
            description="A great scorer",
            account=scorer_account,
            external_scorer_id="scorer1",
        )

        result = get_scorer_by_id("scorer1", scorer_account)

        assert result == scorer

    def test_get_scorer_by_id_not_found(self, scorer_account):
        try:
            get_scorer_by_id(999, scorer_account)
        except Exception as e:
            assert str(e) == "No Community matches the given query."

        try:
            get_scorer_by_id("scorer1", scorer_account)
        except Exception as e:
            assert str(e) == "Field 'id' expected a number but got 'scorer1'."
