import io
import os
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from accounts.testkit import BaseTestCase, make_load, make_offer, make_truck, make_user
from loads.forms import OfferForm
from space.forms import TripForm
from trucks.models import Truck, TruckPhoto
from trucks.photos import MAX_PHOTOS, PhotoError, process

TEMP_MEDIA = tempfile.mkdtemp(prefix='trucklink-test-')


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def image_bytes(size=(1200, 800), fmt='JPEG', mode='RGB', color=(200, 30, 30), **save_options):
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, fmt, **save_options)
    return buffer.getvalue()


def upload(data=None, name='truck.jpg', content_type='image/jpeg', **options):
    return SimpleUploadedFile(name, data if data is not None else image_bytes(**options),
                              content_type=content_type)


def open_image(data):
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


class PhotoProcessingTests(SimpleTestCase):
    def run_process(self, **options):
        main, thumb = process(upload(**options))
        return open_image(main.read()), open_image(thumb.read())

    def test_a_normal_photo_gives_a_full_size_and_a_thumbnail(self):
        main, thumb = self.run_process(size=(1200, 800))
        self.assertEqual(main.format, 'JPEG')
        self.assertEqual(thumb.format, 'JPEG')
        self.assertEqual(main.size, (1200, 800))
        self.assertLessEqual(max(thumb.size), 480)

    def test_huge_photos_are_shrunk(self):
        main, thumb = self.run_process(size=(3200, 2400))
        self.assertEqual(max(main.size), 1600)
        self.assertLessEqual(max(thumb.size), 480)

    def test_png_and_webp_are_accepted_and_saved_as_jpeg(self):
        for fmt, mode in (('PNG', 'RGBA'), ('WEBP', 'RGB')):
            main, _ = self.run_process(fmt=fmt, mode=mode, color=(255, 0, 0, 128) if mode == 'RGBA' else (255, 0, 0))
            self.assertEqual((main.format, main.mode), ('JPEG', 'RGB'), fmt)

    def test_hidden_location_data_is_removed(self):
        exif = Image.Exif()
        exif[0x010F] = 'TestCamera'
        exif[0x8825] = {1: 'S', 2: (17.0, 49.0, 45.0), 3: 'E', 4: (31.0, 3.0, 8.0)}
        original = image_bytes(exif=exif.tobytes())
        self.assertTrue(Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825))
        main, thumb = process(upload(data=original))
        for result in (main, thumb):
            saved = Image.open(io.BytesIO(result.read()))
            self.assertEqual(dict(saved.getexif()), {})
            self.assertEqual(saved.getexif().get_ifd(0x8825), {})

    def test_photos_taken_sideways_are_turned_the_right_way_up(self):
        exif = Image.Exif()
        exif[0x0112] = 6   # the phone was held sideways
        main, _ = self.run_process(size=(800, 500), exif=exif.tobytes())
        self.assertEqual(main.size, (500, 800))

    def test_files_that_are_not_photos_are_refused(self):
        bad_files = [
            b'just some text',
            b'<html><script>alert(1)</script></html>',
            b'%PDF-1.4 fake pdf',
            image_bytes()[:400],                  # a photo cut off part-way
        ]
        for data in bad_files:
            with self.assertRaises(PhotoError):
                process(upload(data=data))

    def test_other_picture_formats_are_refused(self):
        with self.assertRaises(PhotoError):
            process(upload(data=image_bytes(fmt='GIF', mode='P'), name='x.gif', content_type='image/gif'))

    def test_tiny_photos_are_refused(self):
        with self.assertRaises(PhotoError) as caught:
            process(upload(size=(200, 150)))
        self.assertIn('too small', str(caught.exception))

    def test_photos_with_too_many_pixels_are_refused(self):
        with mock.patch('trucks.photos.MAX_PIXELS', 1000):
            with self.assertRaises(PhotoError):
                process(upload())

    def test_very_large_files_are_refused(self):
        with mock.patch('trucks.photos.MAX_BYTES', 100):
            with self.assertRaises(PhotoError) as caught:
                process(upload())
        self.assertIn('10 MB', str(caught.exception))


@override_settings(PRIVATE_MEDIA_ROOT=TEMP_MEDIA)
class PhotoViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user('trucker', 'transporter')
        self.other = make_user('other', 'transporter')
        self.shipper = make_user('shipper', 'shipper')
        self.truck = make_truck(self.owner, registration_number='ZZ 9999')
        self.client = Client()
        self.client.force_login(self.owner)
        self.url = reverse('truck_photos', args=[self.truck.pk])

    def add_photo(self, client=None, **options):
        return (client or self.client).post(self.url, {'kind': 'front', 'image': upload(**options)})

    def test_the_owner_can_add_a_photo(self):
        response = self.add_photo()
        self.assertEqual(response.status_code, 302)
        photo = self.truck.photos.get()
        self.assertEqual(photo.kind, 'front')
        self.assertTrue(os.path.exists(photo.image.path))
        self.assertTrue(os.path.exists(photo.thumb.path))
        self.assertTrue(photo.image.path.startswith(TEMP_MEDIA))
        self.assertIn(f'trucks{os.sep}{self.truck.pk}{os.sep}', photo.image.path)
        self.assertTrue(photo.image.name.endswith('.jpg'))

    def test_stored_files_have_unguessable_names(self):
        self.add_photo()
        self.add_photo()
        names = [p.image.name for p in self.truck.photos.all()] + [p.thumb.name for p in self.truck.photos.all()]
        self.assertEqual(len(set(names)), 4)
        for name in names:
            self.assertNotIn('truck', os.path.basename(name))   # the uploader's file name is not kept

    def test_a_bad_file_is_explained_and_nothing_is_saved(self):
        response = self.client.post(self.url, {'kind': 'side', 'image': upload(data=b'not a photo')})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'could not be read as a photo')
        self.assertFalse(TruckPhoto.objects.exists())

    def test_a_truck_can_have_only_a_limited_number_of_photos(self):
        for _ in range(MAX_PHOTOS):
            self.add_photo()
        self.assertEqual(self.truck.photos.count(), MAX_PHOTOS)
        self.add_photo()
        self.assertEqual(self.truck.photos.count(), MAX_PHOTOS)

    def test_other_people_cannot_manage_my_photos(self):
        self.add_photo()
        photo = self.truck.photos.get()
        for person in (self.other, self.shipper):
            client = Client()
            client.force_login(person)
            self.assertEqual(client.get(self.url).status_code, 404)
            self.assertEqual(self.add_photo(client=client).status_code, 404)
            delete = client.post(reverse('delete_truck_photo', args=[self.truck.pk, photo.pk]))
            self.assertEqual(delete.status_code, 404)
        self.assertEqual(self.truck.photos.count(), 1)

    def test_deleting_a_photo_removes_its_files(self):
        self.add_photo()
        photo = self.truck.photos.get()
        paths = [photo.image.path, photo.thumb.path]
        response = self.client.post(reverse('delete_truck_photo', args=[self.truck.pk, photo.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.truck.photos.exists())
        for path in paths:
            self.assertFalse(os.path.exists(path))

    def test_deleting_a_truck_removes_its_photo_files(self):
        self.add_photo()
        self.add_photo()
        paths = [p.image.path for p in self.truck.photos.all()] + [p.thumb.path for p in self.truck.photos.all()]
        self.client.post(reverse('delete_truck', args=[self.truck.pk]))
        self.assertFalse(Truck.objects.filter(pk=self.truck.pk).exists())
        for path in paths:
            self.assertFalse(os.path.exists(path))

    def test_pictures_can_only_be_opened_by_signed_in_people(self):
        self.add_photo()
        photo = self.truck.photos.get()
        url = reverse('truck_photo_file', args=[photo.pk, 'thumb'])
        self.assertEqual(Client().get(url).status_code, 302)   # sent to the login page
        shipper = Client()
        shipper.force_login(self.shipper)
        response = shipper.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('private', response['Cache-Control'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        thumb = open_image(b''.join(response.streaming_content))
        full = open_image(b''.join(shipper.get(reverse('truck_photo_file', args=[photo.pk, 'full'])).streaming_content))
        self.assertLess(max(thumb.size), max(full.size))

    def test_unknown_pictures_and_sizes_give_a_404(self):
        self.add_photo()
        photo = self.truck.photos.get()
        shipper = Client()
        shipper.force_login(self.shipper)
        self.assertEqual(shipper.get(reverse('truck_photo_file', args=[photo.pk, 'huge'])).status_code, 404)
        self.assertEqual(shipper.get(reverse('truck_photo_file', args=[99999, 'thumb'])).status_code, 404)

    def test_a_missing_file_gives_a_404_instead_of_a_crash(self):
        self.add_photo()
        photo = self.truck.photos.get()
        os.remove(photo.thumb.path)
        shipper = Client()
        shipper.force_login(self.shipper)
        self.assertEqual(shipper.get(reverse('truck_photo_file', args=[photo.pk, 'thumb'])).status_code, 404)

    def test_the_plate_is_shown_only_to_the_owner_and_a_booked_shipper(self):
        detail = reverse('truck_detail', args=[self.truck.pk])
        stranger = Client()
        stranger.force_login(self.shipper)
        self.assertNotContains(stranger.get(detail), 'ZZ 9999')
        self.assertContains(self.client.get(detail), 'ZZ 9999')

        load = make_load(self.shipper)
        make_offer(load, self.owner, truck=self.truck, status='accepted')
        self.assertContains(stranger.get(detail), 'ZZ 9999')

        someone_else = Client()
        someone_else.force_login(make_user('curious', 'shipper'))
        self.assertNotContains(someone_else.get(detail), 'ZZ 9999')

    def test_the_truck_page_says_when_there_are_no_photos(self):
        shipper = Client()
        shipper.force_login(self.shipper)
        response = shipper.get(reverse('truck_detail', args=[self.truck.pk]))
        self.assertContains(response, 'has not added photos')

    def test_the_truck_list_shows_a_thumbnail_or_a_note(self):
        with_photo = make_truck(self.other, registration_number='PHOTO 1')
        self.client.force_login(self.owner)
        photo_url = reverse('truck_photos', args=[with_photo.pk])
        owner_two = Client()
        owner_two.force_login(self.other)
        owner_two.post(photo_url, {'kind': 'side', 'image': upload()})
        shipper = Client()
        shipper.force_login(self.shipper)
        page = shipper.get(reverse('truck_list')).content.decode()
        photo = with_photo.photos.get()
        self.assertIn(reverse('truck_photo_file', args=[photo.pk, 'thumb']), page)
        self.assertIn('No photo yet', page)
        self.assertNotIn('PHOTO 1', page)   # plates stay out of the public list

    def test_adding_a_truck_leads_straight_to_its_photo_page(self):
        response = self.client.post(reverse('add_truck'), {
            'truck_type': 'flatbed', 'capacity_tonnes': '20', 'registration_number': 'NEW 1',
            'current_location': 'Harare', 'is_available': 'on'})
        new = Truck.objects.get(registration_number='NEW 1')
        self.assertRedirects(response, reverse('truck_photos', args=[new.pk]))


class PhotoRuleTests(BaseTestCase):
    """REQUIRE_TRUCK_PHOTOS makes a photo compulsory before a truck can bid or post a trip."""

    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.trucker = make_user('trucker', 'transporter')
        self.truck = make_truck(self.trucker)
        self.load = make_load(self.shipper)

    def give_photo(self):
        TruckPhoto.objects.create(truck=self.truck, image='trucks/x/a.jpg', thumb='trucks/x/b.jpg')

    def offer_form(self):
        return OfferForm({'price': '700', 'truck': self.truck.pk, 'message': ''},
                         user=self.trucker, load=self.load)

    def trip_form(self):
        return TripForm({'truck': self.truck.pk, 'origin': 'Harare', 'destination': 'Bulawayo',
                         'via': '', 'departure_date': timezone.localdate() + timedelta(days=2),
                         'tonnes_available': '10', 'price_per_tonne': '40'}, user=self.trucker)

    def api_offer(self):
        client = APIClient()
        client.force_authenticate(self.trucker)
        return client.post(reverse('api_load_offers', args=[self.load.pk]),
                           {'price': '700', 'truck': self.truck.pk})

    def test_the_rule_is_off_by_default_in_the_tests(self):
        self.assertTrue(self.offer_form().is_valid())

    @override_settings(REQUIRE_TRUCK_PHOTOS=True)
    def test_a_truck_without_photos_cannot_bid_on_the_website(self):
        form = self.offer_form()
        self.assertFalse(form.is_valid())
        self.assertIn('photo', str(form.errors['truck']).lower())
        self.give_photo()
        self.assertTrue(self.offer_form().is_valid())

    @override_settings(REQUIRE_TRUCK_PHOTOS=True)
    def test_a_truck_without_photos_cannot_bid_through_the_api(self):
        response = self.api_offer()
        self.assertEqual(response.status_code, 400)
        self.assertIn('photo', str(response.json()['truck']).lower())
        self.give_photo()
        self.assertEqual(self.api_offer().status_code, 201)

    @override_settings(REQUIRE_TRUCK_PHOTOS=True)
    def test_a_truck_without_photos_cannot_post_a_trip(self):
        form = self.trip_form()
        self.assertFalse(form.is_valid())
        self.assertIn('truck', form.errors)
        self.give_photo()
        self.assertTrue(self.trip_form().is_valid())

    def test_with_the_rule_off_no_photo_is_needed(self):
        self.assertEqual(self.api_offer().status_code, 201)


@override_settings(PRIVATE_MEDIA_ROOT=TEMP_MEDIA)
class PhotoApiTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.shipper = make_user('shipper', 'shipper')
        self.trucker = make_user('trucker', 'transporter')
        self.truck = make_truck(self.trucker, registration_number='ZZ 9999')
        owner = Client()
        owner.force_login(self.trucker)
        owner.post(reverse('truck_photos', args=[self.truck.pk]), {'kind': 'front', 'image': upload()})
        self.photo = self.truck.photos.get()
        self.api = APIClient()
        self.api.force_authenticate(self.shipper)

    def test_the_truck_list_includes_photo_addresses(self):
        results = self.api.get(reverse('api_trucks')).json()['results']
        photos = results[0]['photos']
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0]['kind'], 'front')
        self.assertTrue(photos[0]['url'].startswith('http'))
        self.assertTrue(photos[0]['url'].endswith(f'/trucks/photo/{self.photo.pk}/full/'))
        self.assertTrue(photos[0]['thumb_url'].endswith(f'/trucks/photo/{self.photo.pk}/thumb/'))

    def test_the_plate_still_stays_out_of_the_public_list(self):
        body = self.api.get(reverse('api_trucks')).content.decode()
        self.assertNotIn('ZZ 9999', body)
        self.assertNotIn('registration_number', body)

    def test_the_shipper_sees_the_truck_photos_on_each_offer(self):
        load = make_load(self.shipper)
        make_offer(load, self.trucker, truck=self.truck)
        offers = self.api.get(reverse('api_load_offers', args=[load.pk])).json()['results']
        self.assertEqual(len(offers[0]['truck']['photos']), 1)
        self.assertNotIn('ZZ 9999', str(offers))

    def test_owners_see_their_photos_in_their_own_list(self):
        mine = APIClient()
        mine.force_authenticate(self.trucker)
        results = mine.get(reverse('api_my_trucks')).json()['results']
        self.assertEqual(len(results[0]['photos']), 1)

    def test_the_picture_itself_needs_a_login(self):
        url = reverse('truck_photo_file', args=[self.photo.pk, 'full'])
        self.assertEqual(Client().get(url).status_code, 302)