from datetime import timedelta

from django.utils import timezone

from accounts.models import KycSubmission, Notification, Review, rating_summary
from accounts.notify import notify
from accounts.testkit import BaseTestCase, book, make_load, make_user


class RatingTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.transporter = make_user('trucker', 'transporter')
        self.offer = book(make_load(self.shipper), self.transporter)

    def rate(self, reviewer, reviewee, stars):
        return Review.objects.create(offer=self.offer, reviewer=reviewer,
                                     reviewee=reviewee, stars=stars)

    def test_a_rating_is_hidden_until_the_other_side_rates_too(self):
        self.rate(self.shipper, self.transporter, 5)
        self.assertEqual(rating_summary(self.transporter), (None, 0))

    def test_both_ratings_appear_once_both_sides_have_rated(self):
        self.rate(self.shipper, self.transporter, 5)
        self.rate(self.transporter, self.shipper, 3)
        self.assertEqual(rating_summary(self.transporter), (5.0, 1))
        self.assertEqual(rating_summary(self.shipper), (3.0, 1))

    def test_a_rating_appears_by_itself_after_fourteen_days(self):
        review = self.rate(self.shipper, self.transporter, 4)
        Review.objects.filter(pk=review.pk).update(created_at=timezone.now() - timedelta(days=15))
        self.assertEqual(rating_summary(self.transporter), (4.0, 1))

    def test_the_average_uses_every_visible_rating(self):
        self.rate(self.shipper, self.transporter, 5)
        self.rate(self.transporter, self.shipper, 5)
        other_offer = book(make_load(self.shipper), self.transporter)
        Review.objects.create(offer=other_offer, reviewer=self.shipper, reviewee=self.transporter, stars=3)
        Review.objects.create(offer=other_offer, reviewer=self.transporter, reviewee=self.shipper, stars=4)
        average, count = rating_summary(self.transporter)
        self.assertEqual(count, 2)
        self.assertEqual(average, 4.0)


class VerificationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('trucker', 'transporter')

    def submit(self, status):
        return KycSubmission.objects.create(user=self.user, id_number='63-123456 A78',
                                            front='kyc/test.jpg', status=status)

    def test_nobody_starts_verified(self):
        self.assertEqual(self.user.profile.kyc_status, 'none')
        self.assertFalse(self.user.profile.is_verified)

    def test_an_approved_submission_verifies_the_user(self):
        self.submit('approved')
        self.assertTrue(self.user.profile.is_verified)

    def test_pending_and_rejected_submissions_do_not(self):
        self.submit('pending')
        self.assertFalse(self.user.profile.is_verified)
        KycSubmission.objects.all().delete()
        self.submit('rejected')
        self.assertFalse(self.user.profile.is_verified)


class NotificationTests(BaseTestCase):
    def test_a_notification_is_stored_for_the_user(self):
        user = make_user('shipper', 'shipper')
        notify(user, 'Hello', '/loads/1/')
        note = Notification.objects.get(user=user)
        self.assertEqual(note.message, 'Hello')
        self.assertFalse(note.is_read)

    def test_very_long_messages_are_shortened_to_fit(self):
        user = make_user('shipper', 'shipper')
        notify(user, 'x' * 400)
        self.assertEqual(len(Notification.objects.get(user=user).message), 255)

    def test_notifying_nobody_does_nothing(self):
        notify(None, 'Hello')
        self.assertEqual(Notification.objects.count(), 0)