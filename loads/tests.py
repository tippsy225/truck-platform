from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from accounts.models import Notification
from accounts.testkit import BaseTestCase, book, make_load, make_offer, make_user, pay_fees
from growth.models import Subscription
from loads.learning import refine
from loads.models import Load, Offer, OfferEvent, Payment
from loads.pricing import distance_km, suggest_price
from loads.services import expire_loads, release_unpaid_bookings


class PricingTests(SimpleTestCase):
    def test_harare_to_bulawayo_distance_is_realistic(self):
        self.assertTrue(400 <= distance_km('Harare', 'Bulawayo') <= 480)

    def test_suggestion_is_rounded_to_five_dollars(self):
        result = suggest_price('Harare', 'Bulawayo', 10)
        self.assertEqual(result['suggested'] % 5, 0)

    def test_range_surrounds_the_suggestion(self):
        result = suggest_price('Harare', 'Mutare', 12)
        self.assertLessEqual(result['low'], result['suggested'])
        self.assertLessEqual(result['suggested'], result['high'])

    def test_heavier_loads_cost_more(self):
        light = suggest_price('Harare', 'Bulawayo', 5)['suggested']
        heavy = suggest_price('Harare', 'Bulawayo', 25)['suggested']
        self.assertGreater(heavy, light)

    def test_longer_routes_cost_more(self):
        short = suggest_price('Harare', 'Marondera', 10)['suggested']
        long = suggest_price('Harare', 'Beitbridge', 10)['suggested']
        self.assertGreater(long, short)

    @override_settings(PRICING={'minimum': 5000})
    def test_the_minimum_price_applies(self):
        self.assertEqual(suggest_price('Harare', 'Marondera', 1)['suggested'], 5000)

    @override_settings(PRICING={'per_km': 5.0})
    def test_rates_can_be_changed_in_settings(self):
        normal = suggest_price('Harare', 'Gweru', 10)['suggested']
        self.assertGreater(normal, 1000)

    def test_same_unknown_or_empty_requests_are_refused(self):
        self.assertIsNone(suggest_price('Harare', 'Harare', 10))
        self.assertIsNone(suggest_price('Harare', 'Atlantis', 10))
        self.assertIsNone(suggest_price('Harare', 'Bulawayo', 0))


class LearningTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.transporter = make_user('trucker', 'transporter')

    def formula(self):
        return suggest_price('Harare', 'Bulawayo', 10)

    def job(self, price, **load_extra):
        load = make_load(self.shipper, **load_extra)
        return book(load, self.transporter, price=price)

    def test_without_history_the_formula_is_used(self):
        result = refine(self.formula(), 'Harare', 'Bulawayo', 10)
        self.assertEqual(result['basis'], 'formula')
        self.assertEqual(result['samples'], 0)

    def test_agreed_jobs_on_the_route_move_the_suggestion(self):
        before = self.formula()['suggested']
        for _ in range(3):
            self.job('1500')
        result = refine(self.formula(), 'Harare', 'Bulawayo', 10)
        self.assertEqual(result['basis'], 'learned')
        self.assertEqual(result['samples'], 3)
        self.assertGreater(result['suggested'], before)
        self.assertIn('this route', result['note'])

    def test_the_formula_keeps_a_say_even_with_lots_of_data(self):
        for _ in range(15):
            self.job('1500')
        result = refine(self.formula(), 'Harare', 'Bulawayo', 10)
        self.assertLess(result['suggested'], 1500)

    def test_old_jobs_are_ignored(self):
        old = timezone.now() - timedelta(days=200)
        for _ in range(4):
            load = make_load(self.shipper)
            book(load, self.transporter, price='1500', accepted_at=old)
        result = refine(self.formula(), 'Harare', 'Bulawayo', 10)
        self.assertEqual(result['basis'], 'formula')

    def test_other_routes_help_once_there_are_enough_of_them(self):
        for _ in range(5):
            self.job('600', pickup='Harare', destination='Mutare')
        result = refine(self.formula(), 'Harare', 'Bulawayo', 10)
        self.assertEqual(result['basis'], 'learned')
        self.assertIn('all routes', result['note'])

    def test_unbooked_offers_do_not_count(self):
        for _ in range(4):
            load = make_load(self.shipper)
            make_offer(load, self.transporter, price='1500', status='pending')
        result = refine(self.formula(), 'Harare', 'Bulawayo', 10)
        self.assertEqual(result['basis'], 'formula')


@override_settings(PLATFORM_FEE_PERCENT_SHIPPER=2.5, PLATFORM_FEE_PERCENT_TRANSPORTER=2.5,
                   PLATFORM_FEE_MINIMUM=1)
class FeeTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.transporter = make_user('trucker', 'transporter')

    def offer(self, price):
        return make_offer(make_load(self.shipper), self.transporter, price=price, status='accepted')

    def test_the_fee_is_a_percentage_of_the_price(self):
        offer = self.offer('1000')
        self.assertEqual(offer.shipper_fee, Decimal('25.00'))
        self.assertEqual(offer.transporter_fee, Decimal('25.00'))

    def test_the_minimum_fee_applies_to_small_jobs(self):
        self.assertEqual(self.offer('20').shipper_fee, Decimal('1.00'))

    def subscribe(self, user, plan, days=10):
        now = timezone.now()
        Subscription.objects.create(user=user, plan_key=plan, started_at=now - timedelta(days=1),
                                    expires_at=now + timedelta(days=days), price_paid=Decimal('9'))

    def test_a_pro_plan_gives_the_discount_to_that_person_only(self):
        offer = self.offer('1000')
        self.subscribe(self.shipper, 'pro')
        self.assertEqual(offer.shipper_fee, Decimal('18.75'))
        self.assertEqual(offer.transporter_fee, Decimal('25.00'))

    def test_a_business_plan_halves_the_fee(self):
        offer = self.offer('1000')
        self.subscribe(self.transporter, 'business')
        self.assertEqual(offer.transporter_fee, Decimal('12.50'))

    def test_an_expired_plan_gives_no_discount(self):
        offer = self.offer('1000')
        self.subscribe(self.shipper, 'pro', days=-2)
        self.assertEqual(offer.shipper_fee, Decimal('25.00'))

    def test_fees_are_paid_only_when_both_sides_have_paid(self):
        offer = self.offer('1000')
        self.assertFalse(offer.fee_paid)
        pay_fees(offer, shipper=True, transporter=False)
        self.assertTrue(offer.shipper_paid)
        self.assertFalse(offer.fee_paid)
        pay_fees(offer, shipper=False, transporter=True)
        self.assertTrue(offer.fee_paid)

    def test_a_failed_payment_does_not_count(self):
        offer = self.offer('1000')
        Payment.objects.create(offer=offer, payer=self.shipper, payer_role='shipper',
                               amount=Decimal('25'), phone='0771111111', status='failed')
        self.assertFalse(offer.shipper_paid)


@override_settings(PAYMENT_DEADLINE_HOURS=24)
class HousekeepingTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.transporter = make_user('trucker', 'transporter')

    def test_loads_past_their_pickup_date_expire_and_close_their_offers(self):
        load = make_load(self.shipper, pickup_date=timezone.localdate() - timedelta(days=1))
        offer = make_offer(load, self.transporter, status='pending')
        expire_loads()
        load.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(load.status, 'expired')
        self.assertEqual(offer.status, 'declined')
        self.assertTrue(OfferEvent.objects.filter(offer=offer, kind='expire').exists())
        self.assertTrue(Notification.objects.filter(user=self.shipper).exists())
        self.assertTrue(Notification.objects.filter(user=self.transporter).exists())

    def test_future_loads_are_left_alone(self):
        load = make_load(self.shipper)
        expire_loads()
        load.refresh_from_db()
        self.assertEqual(load.status, 'open')

    def test_booked_loads_never_expire_by_date(self):
        load = make_load(self.shipper, pickup_date=timezone.localdate() - timedelta(days=1))
        book(load, self.transporter)
        expire_loads()
        load.refresh_from_db()
        self.assertEqual(load.status, 'booked')

    def test_unpaid_bookings_are_released_after_the_deadline(self):
        load = make_load(self.shipper)
        offer = book(load, self.transporter, paid='shipper',
                     accepted_at=timezone.now() - timedelta(hours=25))
        release_unpaid_bookings()
        load.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(load.status, 'open')
        self.assertEqual(offer.status, 'expired')
        self.assertEqual(offer.payments.get(payer_role='shipper').status, 'refund_due')
        self.assertTrue(Notification.objects.filter(user=self.shipper).exists())
        self.assertTrue(Notification.objects.filter(user=self.transporter).exists())

    def test_bookings_inside_the_deadline_are_kept(self):
        load = make_load(self.shipper)
        offer = book(load, self.transporter, paid='shipper',
                     accepted_at=timezone.now() - timedelta(hours=2))
        release_unpaid_bookings()
        load.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(load.status, 'booked')
        self.assertEqual(offer.status, 'accepted')

    def test_fully_paid_bookings_are_never_released(self):
        load = make_load(self.shipper)
        offer = book(load, self.transporter, paid='both',
                     accepted_at=timezone.now() - timedelta(hours=48))
        release_unpaid_bookings()
        load.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(load.status, 'booked')
        self.assertEqual(offer.status, 'accepted')

    def test_a_released_load_can_be_booked_again(self):
        load = make_load(self.shipper)
        book(load, self.transporter, paid='none', accepted_at=timezone.now() - timedelta(hours=30))
        release_unpaid_bookings()
        load.refresh_from_db()
        other = make_user('other', 'transporter')
        second = make_offer(load, other, status='pending')
        self.assertEqual(load.status, 'open')
        self.assertEqual(Offer.objects.filter(load=load, status='pending').count(), 1)
        self.assertEqual(second.status, 'pending')