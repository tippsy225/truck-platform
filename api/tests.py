from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import Notification
from accounts.testkit import (PASSWORD, BaseTestCase, book, make_load, make_offer,
                              make_truck, make_user)
from loads.models import Load, Offer, OfferEvent
from wallet.services import topup


class ApiTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper', phone='0771111111')
        self.trucker = make_user('trucker', 'transporter', phone='0772222222')
        self.trucker2 = make_user('trucker2', 'transporter', phone='0773333333')
        self.truck = make_truck(self.trucker)
        self.client = APIClient()

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def load_payload(self, **extra):
        data = {
            'title': 'Maize',
            'pickup': 'Harare',
            'destination': 'Gweru',
            'weight_tonnes': '12',
            'offered_price': '450',
            'pickup_date': str(timezone.localdate() + timedelta(days=2)),
        }
        data.update(extra)
        return data


class SignInTests(ApiTestCase):
    def test_every_endpoint_needs_a_login(self):
        for name in ('api_loads', 'api_me', 'api_trucks', 'api_wallet', 'api_notifications'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 401, name)

    def test_a_token_can_be_used_to_call_the_api(self):
        response = self.client.post(reverse('api_token'),
                                    {'username': 'shipper', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        token = response.json()['token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        me = self.client.get(reverse('api_me'))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['username'], 'shipper')
        self.assertEqual(me.json()['role'], 'shipper')

    def test_a_wrong_password_gets_no_token(self):
        response = self.client.post(reverse('api_token'),
                                    {'username': 'shipper', 'password': 'wrong'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('token', response.json())
        self.assertFalse(Token.objects.exists())

    def test_logging_out_deletes_the_token(self):
        token = Token.objects.create(user=self.shipper)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.post(reverse('api_logout')).status_code, 204)
        self.assertEqual(self.client.get(reverse('api_me')).status_code, 401)

    def test_repeated_login_attempts_are_rate_limited(self):
        codes = [self.client.post(reverse('api_token'),
                                  {'username': 'shipper', 'password': 'wrong'}).status_code
                 for _ in range(12)]
        self.assertIn(429, codes)
        self.assertEqual(codes[0], 400)


class LoadApiTests(ApiTestCase):
    def test_a_shipper_can_post_a_load(self):
        response = self.as_user(self.shipper).post(reverse('api_loads'), self.load_payload())
        self.assertEqual(response.status_code, 201)
        load = Load.objects.get(pk=response.json()['id'])
        self.assertEqual(load.shipper, self.shipper)
        self.assertEqual(load.status, 'open')
        self.assertIsNotNone(response.json()['distance_km'])

    def test_a_transporter_cannot_post_a_load(self):
        response = self.as_user(self.trucker).post(reverse('api_loads'), self.load_payload())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Load.objects.exists())

    def test_bad_loads_are_rejected_with_clear_errors(self):
        client = self.as_user(self.shipper)
        past = str(timezone.localdate() - timedelta(days=1))
        cases = [
            ({'destination': 'Harare'}, 'destination'),
            ({'pickup': 'Atlantis'}, 'pickup'),
            ({'pickup_date': past}, 'pickup_date'),
            ({'weight_tonnes': '0'}, 'weight_tonnes'),
            ({'weight_tonnes': '900'}, 'weight_tonnes'),
            ({'offered_price': '-5'}, 'offered_price'),
            ({'insured': True}, 'insurance_provider'),
            ({'urgency': 'scheduled', 'pickup_date': None}, 'pickup_date'),
        ]
        for extra, field in cases:
            response = client.post(reverse('api_loads'), self.load_payload(**extra), format='json')
            self.assertEqual(response.status_code, 400, extra)
            self.assertIn(field, response.json(), extra)
        self.assertFalse(Load.objects.exists())

    @override_settings(REQUIRE_VERIFICATION=True)
    def test_the_verification_switch_blocks_unverified_shippers(self):
        response = self.as_user(self.shipper).post(reverse('api_loads'), self.load_payload())
        self.assertEqual(response.status_code, 403)

    def test_only_open_loads_are_listed(self):
        open_load = make_load(self.shipper)
        make_load(self.shipper, status='booked')
        make_load(self.shipper, status='expired')
        response = self.as_user(self.trucker).get(reverse('api_loads'))
        ids = [item['id'] for item in response.json()['results']]
        self.assertEqual(ids, [open_load.pk])

    def test_urgent_loads_come_first(self):
        normal = make_load(self.shipper, title='Normal')
        urgent = make_load(self.shipper, title='Urgent', urgency='urgent')
        ids = [i['id'] for i in self.as_user(self.trucker).get(reverse('api_loads')).json()['results']]
        self.assertEqual(ids, [urgent.pk, normal.pk])

    def test_loads_can_be_filtered_by_route_and_cargo(self):
        make_load(self.shipper, destination='Mutare')
        wanted = make_load(self.shipper, destination='Gweru', cargo_type='perishable')
        client = self.as_user(self.trucker)
        by_route = client.get(reverse('api_loads'), {'destination': 'Gweru'}).json()['results']
        by_cargo = client.get(reverse('api_loads'), {'cargo': 'perishable'}).json()['results']
        self.assertEqual([i['id'] for i in by_route], [wanted.pk])
        self.assertEqual([i['id'] for i in by_cargo], [wanted.pk])

    def test_my_loads_shows_only_my_own(self):
        mine = make_load(self.shipper)
        make_load(make_user('other', 'shipper'))
        response = self.as_user(self.shipper).get(reverse('api_my_loads'))
        self.assertEqual([i['id'] for i in response.json()['results']], [mine.pk])
        self.assertEqual(self.as_user(self.trucker).get(reverse('api_my_loads')).status_code, 403)

    def test_results_are_paginated(self):
        for _ in range(25):
            make_load(self.shipper)
        data = self.as_user(self.trucker).get(reverse('api_loads')).json()
        self.assertEqual(data['count'], 25)
        self.assertEqual(len(data['results']), 20)
        self.assertIsNotNone(data['next'])


class ContactPrivacyTests(ApiTestCase):
    def detail(self, user, load):
        return self.as_user(user).get(reverse('api_load', args=[load.pk])).json()

    def test_phone_numbers_stay_hidden_until_both_fees_are_paid(self):
        load = make_load(self.shipper)
        book(load, self.trucker, paid='shipper')
        for person in (self.shipper, self.trucker):
            data = self.detail(person, load)
            self.assertIsNone(data['contacts'])
            self.assertIsNotNone(data['booking'])
            self.assertFalse(data['booking']['fees_paid'])

    def test_both_parties_see_the_numbers_once_both_fees_are_paid(self):
        load = make_load(self.shipper)
        book(load, self.trucker, paid='both')
        for person in (self.shipper, self.trucker):
            contacts = self.detail(person, load)['contacts']
            self.assertEqual(contacts['shipper']['phone'], '0771111111')
            self.assertEqual(contacts['transporter']['phone'], '0772222222')

    def test_strangers_never_see_contacts_or_booking_details(self):
        load = make_load(self.shipper)
        book(load, self.trucker, paid='both')
        response = self.as_user(self.trucker2).get(reverse('api_load', args=[load.pk]))
        data = response.json()
        self.assertIsNone(data['contacts'])
        self.assertIsNone(data['booking'])
        for number in ('0771111111', '0772222222'):
            self.assertNotIn(number, response.content.decode())

    def test_phone_numbers_never_appear_in_lists(self):
        load = make_load(self.shipper)
        make_offer(load, self.trucker)
        for name in ('api_loads', 'api_trucks'):
            body = self.as_user(self.trucker2).get(reverse(name)).content.decode()
            self.assertNotIn('0771111111', body)
            self.assertNotIn('0772222222', body)

    def test_the_booking_shows_fees_to_the_parties(self):
        load = make_load(self.shipper)
        book(load, self.trucker, price='1000', paid='none')
        booking = self.detail(self.shipper, load)['booking']
        self.assertEqual(Decimal(booking['price']), Decimal('1000.00'))
        self.assertEqual(Decimal(booking['shipper_fee']), Decimal('25.00'))
        self.assertIsNotNone(booking['pay_deadline'])


class OfferApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.load = make_load(self.shipper)
        self.url = reverse('api_load_offers', args=[self.load.pk])

    def offer(self, **extra):
        data = {'price': '700', 'truck': self.truck.pk, 'message': 'Can load tomorrow'}
        data.update(extra)
        return data

    def test_a_transporter_can_send_an_offer(self):
        response = self.as_user(self.trucker).post(self.url, self.offer())
        self.assertEqual(response.status_code, 201)
        offer = Offer.objects.get()
        self.assertEqual((offer.transporter, offer.status), (self.trucker, 'pending'))
        self.assertEqual(OfferEvent.objects.filter(offer=offer, kind='offer').count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.shipper).exists())

    def test_a_shipper_cannot_offer_on_a_load(self):
        response = self.as_user(self.shipper).post(self.url, self.offer())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Offer.objects.exists())

    def test_a_truck_that_is_too_small_is_refused(self):
        small = make_truck(self.trucker, capacity='5', registration_number='SMALL 1')
        response = self.as_user(self.trucker).post(self.url, self.offer(truck=small.pk))
        self.assertEqual(response.status_code, 400)
        self.assertIn('truck', response.json())

    def test_a_truck_with_expired_insurance_is_refused(self):
        expired = make_truck(self.trucker, registration_number='OLD 1',
                             insurance_expiry=timezone.localdate() - timedelta(days=1))
        response = self.as_user(self.trucker).post(self.url, self.offer(truck=expired.pk))
        self.assertEqual(response.status_code, 400)
        self.assertIn('insurance', str(response.json()['truck']).lower())

    def test_the_wrong_type_of_truck_is_refused(self):
        load = make_load(self.shipper, truck_type_needed='tanker')
        response = self.as_user(self.trucker).post(
            reverse('api_load_offers', args=[load.pk]), self.offer())
        self.assertEqual(response.status_code, 400)

    def test_you_cannot_use_somebody_elses_truck(self):
        theirs = make_truck(self.trucker2, registration_number='THEIRS 1')
        response = self.as_user(self.trucker).post(self.url, self.offer(truck=theirs.pk))
        self.assertEqual(response.status_code, 400)

    def test_prices_must_be_above_zero(self):
        response = self.as_user(self.trucker).post(self.url, self.offer(price='0'))
        self.assertEqual(response.status_code, 400)

    def test_you_cannot_have_two_offers_on_one_load(self):
        client = self.as_user(self.trucker)
        self.assertEqual(client.post(self.url, self.offer()).status_code, 201)
        self.assertEqual(client.post(self.url, self.offer(price='650')).status_code, 409)
        self.assertEqual(Offer.objects.count(), 1)

    def test_no_offers_on_a_load_that_is_not_open(self):
        self.load.status = 'booked'
        self.load.save()
        response = self.as_user(self.trucker).post(self.url, self.offer())
        self.assertEqual(response.status_code, 409)

    def test_the_shipper_sees_every_offer_but_transporters_only_their_own(self):
        make_offer(self.load, self.trucker, truck=self.truck)
        make_offer(self.load, self.trucker2, truck=make_truck(self.trucker2, registration_number='T2'))
        shipper_view = self.as_user(self.shipper).get(self.url).json()['results']
        mine = self.as_user(self.trucker).get(self.url).json()['results']
        stranger = self.as_user(make_user('t3', 'transporter')).get(self.url).json()['results']
        self.assertEqual(len(shipper_view), 2)
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]['transporter']['username'], 'trucker')
        self.assertEqual(stranger, [])

    def test_a_transporter_can_list_their_own_offers(self):
        make_offer(self.load, self.trucker, truck=self.truck)
        data = self.as_user(self.trucker).get(reverse('api_my_offers')).json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(self.as_user(self.shipper).get(reverse('api_my_offers')).status_code, 403)


class OfferActionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.load = make_load(self.shipper)
        self.offer = make_offer(self.load, self.trucker, price='700', truck=self.truck)

    def act(self, user, action, **data):
        url = reverse(f'api_offer_{action}', args=[self.offer.pk])
        return self.as_user(user).post(url, data, format='json')

    def refresh(self):
        self.offer.refresh_from_db()
        self.load.refresh_from_db()

    def test_a_full_negotiation(self):
        counter = self.act(self.shipper, 'counter', price='650')
        self.assertEqual(counter.status_code, 200)
        self.assertEqual(counter.json()['status'], 'countered')
        self.assertEqual(Decimal(counter.json()['price']), Decimal('650.00'))

        view = self.as_user(self.trucker).get(reverse('api_my_offers')).json()['results'][0]
        self.assertTrue(view['your_turn'])
        self.assertTrue(Notification.objects.filter(user=self.trucker).exists())

        again = self.act(self.trucker, 'counter', price='680')
        self.assertEqual(again.json()['status'], 'pending')

        accepted = self.act(self.shipper, 'accept')
        self.assertEqual(accepted.json()['status'], 'accepted')
        self.refresh()
        self.assertEqual(self.load.status, 'booked')
        self.assertEqual(self.offer.price, Decimal('680.00'))
        self.assertIsNotNone(self.offer.accepted_at)
        kinds = list(self.offer.events.values_list('kind', flat=True))
        self.assertEqual(kinds, ['counter', 'counter', 'accept'])

    def test_accepting_declines_the_rival_offers(self):
        rival = make_offer(self.load, self.trucker2, truck=make_truck(self.trucker2, registration_number='T2'))
        self.act(self.shipper, 'accept')
        rival.refresh_from_db()
        self.assertEqual(rival.status, 'declined')
        self.assertTrue(Notification.objects.filter(user=self.trucker2).exists())

    def test_you_can_only_act_on_your_own_turn(self):
        self.assertEqual(self.act(self.trucker, 'accept').status_code, 409)
        self.assertEqual(self.act(self.trucker, 'counter', price='600').status_code, 409)
        self.act(self.shipper, 'counter', price='650')
        self.assertEqual(self.act(self.shipper, 'counter', price='640').status_code, 409)
        self.assertEqual(self.act(self.shipper, 'accept').status_code, 409)
        self.refresh()
        self.assertEqual(self.load.status, 'open')

    def test_strangers_cannot_tell_the_offer_exists(self):
        self.assertEqual(self.act(self.trucker2, 'accept').status_code, 404)
        self.assertEqual(self.act(make_user('nosy', 'shipper'), 'decline').status_code, 404)
        self.refresh()
        self.assertEqual(self.offer.status, 'pending')

    def test_unknown_offers_give_a_404(self):
        url = reverse('api_offer_accept', args=[99999])
        self.assertEqual(self.as_user(self.shipper).post(url).status_code, 404)

    def test_the_shipper_can_decline(self):
        self.assertEqual(self.act(self.shipper, 'decline').json()['status'], 'declined')

    def test_the_transporter_can_withdraw_but_the_shipper_cannot(self):
        self.assertEqual(self.act(self.shipper, 'withdraw').status_code, 409)
        self.assertEqual(self.act(self.trucker, 'withdraw').json()['status'], 'withdrawn')

    def test_nothing_changes_once_the_load_is_booked(self):
        self.act(self.shipper, 'accept')
        self.assertEqual(self.act(self.shipper, 'decline').status_code, 409)
        self.assertEqual(self.act(self.trucker, 'withdraw').status_code, 409)

    def test_a_counter_needs_a_positive_price(self):
        self.assertEqual(self.act(self.shipper, 'counter', price='0').status_code, 400)
        self.assertEqual(self.act(self.shipper, 'counter').status_code, 400)
        self.assertEqual(self.act(self.shipper, 'counter', price='abc').status_code, 400)

    def test_actions_must_be_posted(self):
        url = reverse('api_offer_accept', args=[self.offer.pk])
        self.assertEqual(self.as_user(self.shipper).get(url).status_code, 405)


class OtherEndpointTests(ApiTestCase):
    def test_the_price_guide_answers_with_a_range(self):
        response = self.as_user(self.shipper).get(
            reverse('api_price_guide'), {'pickup': 'Harare', 'destination': 'Bulawayo', 'tonnes': '10'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(data['low'], data['suggested'])
        self.assertLessEqual(data['suggested'], data['high'])
        self.assertEqual(data['basis'], 'formula')

    def test_the_price_guide_refuses_bad_questions(self):
        client = self.as_user(self.shipper)
        url = reverse('api_price_guide')
        self.assertEqual(client.get(url, {'pickup': 'Harare', 'destination': 'Harare', 'tonnes': '5'}).status_code, 400)
        self.assertEqual(client.get(url, {'pickup': 'Atlantis', 'destination': 'Harare', 'tonnes': '5'}).status_code, 400)
        self.assertEqual(client.get(url, {'pickup': 'Harare', 'destination': 'Gweru', 'tonnes': '0'}).status_code, 400)
        self.assertEqual(client.get(url).status_code, 400)

    def test_the_truck_list_hides_plates_and_expired_documents(self):
        make_truck(self.trucker2, registration_number='EXPIRED 1',
                   insurance_expiry=timezone.localdate() - timedelta(days=1))
        response = self.as_user(self.shipper).get(reverse('api_trucks'))
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertNotIn('registration_number', results[0])
        self.assertNotIn('ABC 1234', response.content.decode())
        self.assertNotIn('insurance_expiry', results[0])

    def test_transporters_see_their_own_truck_details(self):
        results = self.as_user(self.trucker).get(reverse('api_my_trucks')).json()['results']
        self.assertEqual(results[0]['registration_number'], 'ABC 1234')
        self.assertTrue(results[0]['documents_ok'])
        self.assertEqual(self.as_user(self.shipper).get(reverse('api_my_trucks')).status_code, 403)

    def test_notifications_can_be_listed_and_marked_as_read(self):
        Notification.objects.create(user=self.shipper, message='One')
        Notification.objects.create(user=self.shipper, message='Two')
        Notification.objects.create(user=self.trucker, message='Not yours')
        client = self.as_user(self.shipper)
        data = client.get(reverse('api_notifications')).json()
        self.assertEqual(data['count'], 2)
        self.assertEqual(client.post(reverse('api_notifications_read')).json(), {'marked': 2})
        self.assertFalse(Notification.objects.filter(user=self.shipper, is_read=False).exists())
        self.assertTrue(Notification.objects.filter(user=self.trucker, is_read=False).exists())

    def test_the_wallet_endpoint_shows_balance_and_entries(self):
        topup(self.shipper, '100')
        data = self.as_user(self.shipper).get(reverse('api_wallet')).json()
        self.assertEqual(data['balance'], '100.00')
        self.assertEqual(data['entries'][0]['kind'], 'topup')
        self.assertEqual(self.as_user(self.trucker).get(reverse('api_wallet')).json()['balance'], '0.00')

    def test_the_me_endpoint_describes_the_caller(self):
        data = self.as_user(self.trucker).get(reverse('api_me')).json()
        self.assertEqual(data['role'], 'transporter')
        self.assertEqual(data['plan'], 'free')
        self.assertFalse(data['verified'])
        self.assertNotIn('password', data)

    def test_the_documentation_is_published(self):
        schema = self.client.get(reverse('api_schema'))
        self.assertEqual(schema.status_code, 200)
        self.assertIn('openapi', schema.content.decode())
        self.assertEqual(self.client.get(reverse('api_docs')).status_code, 200)