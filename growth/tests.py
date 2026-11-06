from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone

from accounts.testkit import BaseTestCase, book, make_load, make_user
from growth.billing import BillingError, subscribe
from growth.models import Referral, Subscription
from growth.plans import current_plan_key
from wallet.services import balance, topup


class SubscriptionTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('shipper', 'shipper')

    def test_buying_a_plan_takes_the_price_from_the_wallet(self):
        topup(self.user, '50')
        subscribe(self.user, 'pro')
        self.assertEqual(balance(self.user), Decimal('41.00'))
        self.assertEqual(current_plan_key(self.user), 'pro')

    def test_you_cannot_buy_a_plan_without_enough_money(self):
        topup(self.user, '8.99')
        with self.assertRaises(BillingError):
            subscribe(self.user, 'pro')
        self.assertEqual(balance(self.user), Decimal('8.99'))
        self.assertEqual(current_plan_key(self.user), 'free')

    def test_free_and_unknown_plans_cannot_be_bought(self):
        topup(self.user, '50')
        for key in ('free', 'platinum'):
            with self.assertRaises(BillingError):
                subscribe(self.user, key)

    def test_renewing_adds_time_after_the_current_period(self):
        topup(self.user, '50')
        first = subscribe(self.user, 'pro')
        second = subscribe(self.user, 'pro')
        self.assertEqual(second.started_at, first.expires_at)
        self.assertEqual(second.expires_at, first.expires_at + timedelta(days=30))

    def test_switching_plan_ends_the_old_one_straight_away(self):
        topup(self.user, '100')
        subscribe(self.user, 'pro')
        subscribe(self.user, 'business')
        self.assertEqual(current_plan_key(self.user), 'business')
        old = Subscription.objects.get(plan_key='pro')
        self.assertLessEqual(old.expires_at, timezone.now())

    def test_an_expired_plan_stops_applying(self):
        topup(self.user, '50')
        sub = subscribe(self.user, 'pro')
        Subscription.objects.filter(pk=sub.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(current_plan_key(self.user), 'free')


class ReferralTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.referrer = make_user('referrer', 'shipper')
        self.newcomer = make_user('newcomer', 'shipper')
        self.partner = make_user('partner', 'transporter')
        self.referral = Referral.objects.create(referrer=self.referrer, referred=self.newcomer)

    def deliver(self, shipper, transporter):
        load = make_load(shipper)
        book(load, transporter)
        load.status = 'delivered'
        load.save()
        return load

    def test_both_sides_are_rewarded_after_the_first_delivered_job(self):
        self.deliver(self.newcomer, self.partner)
        self.referral.refresh_from_db()
        self.assertEqual(self.referral.status, 'rewarded')
        self.assertEqual(balance(self.referrer), Decimal('2.00'))
        self.assertEqual(balance(self.newcomer), Decimal('2.00'))

    def test_nothing_is_paid_before_a_job_is_delivered(self):
        load = make_load(self.newcomer)
        book(load, self.partner)
        self.referral.refresh_from_db()
        self.assertEqual(self.referral.status, 'pending')
        self.assertEqual(balance(self.referrer), Decimal('0.00'))

    def test_the_bonus_is_paid_only_once(self):
        self.deliver(self.newcomer, self.partner)
        self.deliver(self.newcomer, self.partner)
        self.assertEqual(balance(self.referrer), Decimal('2.00'))
        self.assertEqual(balance(self.newcomer), Decimal('2.00'))

    def test_a_job_with_the_referrer_does_not_count(self):
        transporter_referrer = make_user('referrer2', 'transporter')
        Referral.objects.filter(pk=self.referral.pk).update(referrer=transporter_referrer)
        self.deliver(self.newcomer, transporter_referrer)
        self.referral.refresh_from_db()
        self.assertEqual(self.referral.status, 'pending')
        self.assertEqual(balance(transporter_referrer), Decimal('0.00'))
        self.assertEqual(balance(self.newcomer), Decimal('0.00'))

    def test_the_transporter_side_can_earn_a_welcome_bonus_too(self):
        newcomer_driver = make_user('driver', 'transporter')
        Referral.objects.create(referrer=self.referrer, referred=newcomer_driver)
        self.deliver(self.partner_shipper(), newcomer_driver)
        self.assertEqual(balance(newcomer_driver), Decimal('2.00'))

    def partner_shipper(self):
        return make_user('someone', 'shipper')

    @override_settings(REFERRAL_MAX_REWARDS=1)
    def test_there_is_a_limit_on_rewarded_referrals(self):
        second = make_user('second', 'shipper')
        second_referral = Referral.objects.create(referrer=self.referrer, referred=second)
        self.deliver(self.newcomer, self.partner)
        self.deliver(second, self.partner)
        second_referral.refresh_from_db()
        self.assertEqual(second_referral.status, 'capped')
        self.assertEqual(balance(self.referrer), Decimal('2.00'))