from decimal import Decimal

from django.db.models import Sum

from accounts.models import Notification
from accounts.testkit import BaseTestCase, book, make_load, make_user
from loads.models import Offer
from wallet.models import Dispute, Escrow, LedgerEntry
from wallet.services import (WalletError, balance, fund_escrow, refund_escrow,
                             release_escrow, resolve_dispute, split_escrow, topup, withdraw)


class WalletTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.transporter = make_user('trucker', 'transporter')
        self.admin = make_user('admin', 'shipper', staff=True)

    def booked_job(self, price='700', paid='both'):
        load = make_load(self.shipper)
        return book(load, self.transporter, price=price, paid=paid)

    def test_top_up_and_withdraw(self):
        topup(self.shipper, '100')
        self.assertEqual(balance(self.shipper), Decimal('100.00'))
        withdraw(self.shipper, '40')
        self.assertEqual(balance(self.shipper), Decimal('60.00'))

    def test_you_cannot_withdraw_more_than_you_have(self):
        topup(self.shipper, '50')
        with self.assertRaises(WalletError):
            withdraw(self.shipper, '50.01')
        self.assertEqual(balance(self.shipper), Decimal('50.00'))

    def test_zero_and_negative_amounts_are_refused(self):
        with self.assertRaises(WalletError):
            topup(self.shipper, '0')
        with self.assertRaises(WalletError):
            topup(self.shipper, '-5')
        with self.assertRaises(WalletError):
            withdraw(self.shipper, '0')

    def test_funding_escrow_moves_money_out_of_the_wallet(self):
        offer = self.booked_job()
        topup(self.shipper, '1000')
        fund_escrow(offer)
        self.assertEqual(balance(self.shipper), Decimal('300.00'))
        escrow = Escrow.objects.get(offer=offer)
        self.assertEqual(escrow.amount, Decimal('700.00'))
        self.assertEqual(escrow.status, 'held')

    def test_escrow_needs_both_platform_fees_first(self):
        offer = self.booked_job(paid='shipper')
        topup(self.shipper, '1000')
        with self.assertRaises(WalletError):
            fund_escrow(offer)
        self.assertFalse(Escrow.objects.exists())

    def test_escrow_needs_enough_money(self):
        offer = self.booked_job()
        topup(self.shipper, '699.99')
        with self.assertRaises(WalletError):
            fund_escrow(offer)
        self.assertEqual(balance(self.shipper), Decimal('699.99'))

    def test_escrow_cannot_be_funded_twice(self):
        offer = self.booked_job()
        topup(self.shipper, '2000')
        fund_escrow(offer)
        with self.assertRaises(WalletError):
            fund_escrow(offer)
        self.assertEqual(balance(self.shipper), Decimal('1300.00'))

    def test_escrow_cannot_be_funded_during_a_dispute(self):
        offer = self.booked_job()
        topup(self.shipper, '1000')
        Dispute.objects.create(offer=offer, raised_by=self.transporter,
                               reason='other', description='x' * 25)
        with self.assertRaises(WalletError):
            fund_escrow(offer)

    def test_release_pays_the_transporter(self):
        offer = self.booked_job()
        topup(self.shipper, '1000')
        fund_escrow(offer)
        release_escrow(offer)
        self.assertEqual(balance(self.transporter), Decimal('700.00'))
        self.assertEqual(Escrow.objects.get(offer=offer).status, 'released')

    def test_refund_returns_the_money_to_the_shipper(self):
        offer = self.booked_job()
        topup(self.shipper, '1000')
        fund_escrow(offer)
        refund_escrow(offer)
        self.assertEqual(balance(self.shipper), Decimal('1000.00'))
        self.assertEqual(balance(self.transporter), Decimal('0.00'))

    def test_escrow_can_only_be_paid_out_once(self):
        offer = self.booked_job()
        topup(self.shipper, '1000')
        fund_escrow(offer)
        release_escrow(offer)
        with self.assertRaises(WalletError):
            release_escrow(offer)
        with self.assertRaises(WalletError):
            refund_escrow(offer)
        self.assertEqual(balance(self.transporter), Decimal('700.00'))

    def test_a_split_never_loses_or_creates_a_cent(self):
        offer = self.booked_job(price='700.01')
        topup(self.shipper, '1000')
        fund_escrow(offer)
        split_escrow(offer)
        paid_out = balance(self.transporter)
        refunded = balance(self.shipper) - Decimal('299.99')
        self.assertEqual(paid_out + refunded, Decimal('700.01'))

    def test_the_wallet_system_never_creates_money(self):
        offer = self.booked_job()
        topup(self.shipper, '1000')
        topup(self.transporter, '50')
        fund_escrow(offer)
        release_escrow(offer)
        total = LedgerEntry.objects.aggregate(t=Sum('amount'))['t']
        self.assertEqual(total, Decimal('1050.00'))


class DisputeTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.transporter = make_user('trucker', 'transporter')
        self.admin = make_user('admin', 'shipper', staff=True)
        self.load = make_load(self.shipper)
        self.offer = book(self.load, self.transporter, price='700')
        topup(self.shipper, '1000')
        fund_escrow(self.offer)
        self.dispute = Dispute.objects.create(offer=self.offer, raised_by=self.transporter,
                                              reason='no_show', description='x' * 25)

    def refresh(self):
        self.load.refresh_from_db()
        self.offer.refresh_from_db()
        self.dispute.refresh_from_db()

    def test_releasing_pays_the_transporter_and_delivers_the_load(self):
        resolve_dispute(self.dispute, 'release', self.admin, 'Delivery confirmed.')
        self.refresh()
        self.assertEqual(balance(self.transporter), Decimal('700.00'))
        self.assertEqual(self.load.status, 'delivered')
        self.assertEqual(self.dispute.status, 'resolved')
        self.assertEqual(self.dispute.resolved_by, self.admin)

    def test_refunding_repays_the_shipper_and_reopens_the_load(self):
        resolve_dispute(self.dispute, 'refund', self.admin)
        self.refresh()
        self.assertEqual(balance(self.shipper), Decimal('1000.00'))
        self.assertEqual(self.load.status, 'open')
        self.assertEqual(self.offer.status, 'expired')

    def test_splitting_pays_both_sides(self):
        resolve_dispute(self.dispute, 'split', self.admin)
        self.refresh()
        self.assertEqual(balance(self.transporter), Decimal('350.00'))
        self.assertEqual(balance(self.shipper), Decimal('650.00'))
        self.assertEqual(self.load.status, 'delivered')

    def test_closing_without_money_changes_nothing_else(self):
        resolve_dispute(self.dispute, 'no_escrow', self.admin)
        self.refresh()
        self.assertEqual(Escrow.objects.get(offer=self.offer).status, 'held')
        self.assertEqual(self.load.status, 'booked')
        self.assertEqual(self.dispute.status, 'resolved')

    def test_a_dispute_cannot_be_resolved_twice(self):
        resolve_dispute(self.dispute, 'release', self.admin)
        with self.assertRaises(WalletError):
            resolve_dispute(self.dispute, 'refund', self.admin)
        self.assertEqual(balance(self.transporter), Decimal('700.00'))
        self.assertEqual(balance(self.shipper), Decimal('300.00'))

    def test_an_unknown_resolution_is_refused(self):
        with self.assertRaises(WalletError):
            resolve_dispute(self.dispute, 'keep-it-all', self.admin)
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.status, 'open')

    def test_both_sides_are_told_the_outcome(self):
        resolve_dispute(self.dispute, 'split', self.admin, 'Both share the blame.')
        for person in (self.shipper, self.transporter):
            note = Notification.objects.filter(user=person).latest('id')
            self.assertIn('resolved', note.message)
            self.assertIn('Both share the blame.', note.message)