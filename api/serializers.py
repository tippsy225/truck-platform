from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.models import Notification, rating_summary
from growth.plans import current_plan_key
from loads.models import Load, Offer, OfferEvent
from loads.pricing import TOWNS, distance_km
from trucks.models import Truck, TruckPhoto
from trucks.photos import photo_requirement_message
from wallet.models import LedgerEntry

from .rules import accepted_offer, role_of, side_of

TOWN_NAMES = sorted(TOWNS)


class UserBriefSerializer(serializers.Serializer):
    username = serializers.CharField()
    verified = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    @extend_schema_field(serializers.BooleanField())
    def get_verified(self, user):
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.is_verified)

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_rating(self, user):
        avg, _ = rating_summary(user)
        return round(avg, 1) if avg else None

    @extend_schema_field(serializers.IntegerField())
    def get_rating_count(self, user):
        return rating_summary(user)[1]


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    role = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    both_roles = serializers.SerializerMethodField()
    verified = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_role(self, user):
        return role_of(user)

    @extend_schema_field(serializers.CharField())
    def get_phone(self, user):
        profile = getattr(user, 'profile', None)
        return profile.phone if profile else ''

    @extend_schema_field(serializers.BooleanField())
    def get_both_roles(self, user):
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.both_roles)

    @extend_schema_field(serializers.BooleanField())
    def get_verified(self, user):
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.is_verified)

    @extend_schema_field(serializers.CharField())
    def get_plan(self, user):
        return current_plan_key(user)

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_rating(self, user):
        avg, _ = rating_summary(user)
        return round(avg, 1) if avg else None

    @extend_schema_field(serializers.IntegerField())
    def get_rating_count(self, user):
        return rating_summary(user)[1]


class TruckPhotoSerializer(serializers.ModelSerializer):
    """Picture addresses. They only open for someone who is signed in (a session or a token)."""
    url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = TruckPhoto
        fields = ['id', 'kind', 'url', 'thumb_url']

    def _link(self, photo, size):
        path = reverse('truck_photo_file', args=[photo.pk, size])
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request is not None else path

    @extend_schema_field(serializers.CharField())
    def get_url(self, photo):
        return self._link(photo, 'full')

    @extend_schema_field(serializers.CharField())
    def get_thumb_url(self, photo):
        return self._link(photo, 'thumb')


class TruckBriefSerializer(serializers.ModelSerializer):
    photos = TruckPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Truck
        fields = ['id', 'truck_type', 'capacity_tonnes', 'make', 'vehicle_model', 'year', 'photos']


class TruckPublicSerializer(serializers.ModelSerializer):
    """What other people see: no registration plate and no document dates."""
    owner = UserBriefSerializer(read_only=True)
    photos = TruckPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Truck
        fields = ['id', 'truck_type', 'capacity_tonnes', 'make', 'vehicle_model', 'year',
                  'axle_configuration', 'volume_cbm', 'current_location', 'available_from',
                  'owner', 'photos']


class TruckOwnSerializer(serializers.ModelSerializer):
    documents_ok = serializers.BooleanField(read_only=True)
    photos = TruckPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Truck
        fields = ['id', 'truck_type', 'capacity_tonnes', 'registration_number', 'make',
                  'vehicle_model', 'year', 'axle_configuration', 'volume_cbm',
                  'current_location', 'available_from', 'insurance_expiry',
                  'roadworthy_expiry', 'documents_ok', 'is_available', 'photos']


class OfferEventSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source='actor.username', allow_null=True, read_only=True)

    class Meta:
        model = OfferEvent
        fields = ['kind', 'price', 'actor', 'created_at']


class OfferSerializer(serializers.ModelSerializer):
    load = serializers.PrimaryKeyRelatedField(read_only=True)
    transporter = UserBriefSerializer(read_only=True)
    truck = TruckBriefSerializer(read_only=True)
    events = OfferEventSerializer(many=True, read_only=True)
    your_turn = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = ['id', 'load', 'transporter', 'truck', 'price', 'message', 'status',
                  'your_turn', 'accepted_at', 'created_at', 'events']

    @extend_schema_field(serializers.BooleanField())
    def get_your_turn(self, offer):
        request = self.context.get('request')
        if request is None or offer.load.status != 'open':
            return False
        user = request.user
        if user.id == offer.load.shipper_id:
            return offer.status == 'pending'
        if user.id == offer.transporter_id:
            return offer.status == 'countered'
        return False


class OfferCreateSerializer(serializers.ModelSerializer):
    truck = serializers.PrimaryKeyRelatedField(queryset=Truck.objects.none())

    class Meta:
        model = Offer
        fields = ['price', 'truck', 'message']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request is not None and request.user.is_authenticated:
            self.fields['truck'].queryset = Truck.objects.filter(owner=request.user)

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Enter a price above zero.')
        return value

    def validate_truck(self, truck):
        if truck.insurance_expired:
            raise serializers.ValidationError("This truck's insurance has expired. Update the truck before you bid.")
        if truck.roadworthy_expired:
            raise serializers.ValidationError("This truck's roadworthy certificate has expired. Update the truck before you bid.")
        problem = photo_requirement_message(truck)
        if problem:
            raise serializers.ValidationError(problem)
        load = self.context.get('load')
        if load is not None:
            if truck.capacity_tonnes < load.weight_tonnes:
                raise serializers.ValidationError(
                    f'This truck carries {truck.capacity_tonnes} t, but the load weighs {load.weight_tonnes} t.')
            if load.truck_type_needed not in ('any', truck.truck_type):
                raise serializers.ValidationError(
                    f'This load needs a {load.get_truck_type_needed_display().lower()} truck.')
        return truck


class CounterSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class ContactSerializer(serializers.Serializer):
    username = serializers.CharField()
    phone = serializers.CharField()


class ContactsSerializer(serializers.Serializer):
    shipper = ContactSerializer(allow_null=True)
    transporter = ContactSerializer()


class BookingSerializer(serializers.Serializer):
    offer_id = serializers.IntegerField(source='pk')
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    shipper_fee = serializers.DecimalField(max_digits=8, decimal_places=2)
    transporter_fee = serializers.DecimalField(max_digits=8, decimal_places=2)
    shipper_paid = serializers.BooleanField()
    transporter_paid = serializers.BooleanField()
    fees_paid = serializers.BooleanField(source='fee_paid')
    pay_deadline = serializers.DateTimeField(allow_null=True)


LOAD_FIELDS = ['id', 'title', 'pickup', 'destination', 'distance_km', 'cargo_type',
               'weight_tonnes', 'truck_type_needed', 'offered_price', 'urgency',
               'pickup_date', 'description', 'insured', 'insurance_provider',
               'coverage_amount', 'status', 'created_at', 'shipper']


class LoadSerializer(serializers.ModelSerializer):
    shipper = UserBriefSerializer(read_only=True)
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Load
        fields = LOAD_FIELDS

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_distance_km(self, load):
        if load.pickup in TOWNS and load.destination in TOWNS and load.pickup != load.destination:
            return distance_km(load.pickup, load.destination)
        return None


class LoadDetailSerializer(LoadSerializer):
    my_offer = serializers.SerializerMethodField()
    booking = serializers.SerializerMethodField()
    contacts = serializers.SerializerMethodField()

    class Meta(LoadSerializer.Meta):
        fields = LOAD_FIELDS + ['my_offer', 'booking', 'contacts']

    @extend_schema_field(OfferSerializer(allow_null=True))
    def get_my_offer(self, load):
        user = self.context['request'].user
        if role_of(user) != 'transporter' or load.shipper_id == user.id:
            return None
        offer = (load.offers.filter(transporter=user)
                 .exclude(status__in=['declined', 'withdrawn', 'expired'])
                 .select_related('load', 'truck', 'transporter').first())
        return OfferSerializer(offer, context=self.context).data if offer else None

    @extend_schema_field(BookingSerializer(allow_null=True))
    def get_booking(self, load):
        user = self.context['request'].user
        offer = accepted_offer(load)
        if offer is None or side_of(user, load, offer) is None:
            return None
        return BookingSerializer(offer).data

    @extend_schema_field(ContactsSerializer(allow_null=True))
    def get_contacts(self, load):
        """Phone numbers are shown only to the two parties, and only after both platform fees are paid."""
        user = self.context['request'].user
        offer = accepted_offer(load)
        if offer is None or side_of(user, load, offer) is None or not offer.fee_paid:
            return None

        def phone(person):
            profile = getattr(person, 'profile', None)
            return profile.phone if profile else ''

        shipper = None
        if load.shipper is not None:
            shipper = {'username': load.shipper.username, 'phone': phone(load.shipper)}
        return {'shipper': shipper,
                'transporter': {'username': offer.transporter.username,
                                'phone': phone(offer.transporter)}}


class LoadCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Load
        fields = ['title', 'pickup', 'destination', 'cargo_type', 'weight_tonnes',
                  'truck_type_needed', 'offered_price', 'urgency', 'pickup_date',
                  'description', 'insured', 'insurance_provider', 'coverage_amount']

    def _town(self, value):
        if value not in TOWNS:
            raise serializers.ValidationError('Choose a town from the list: ' + ', '.join(TOWN_NAMES) + '.')
        return value

    def validate_pickup(self, value):
        return self._town(value)

    def validate_destination(self, value):
        return self._town(value)

    def validate_weight_tonnes(self, value):
        if not (0 < value <= 500):
            raise serializers.ValidationError('Enter a weight above 0 and up to 500 tonnes.')
        return value

    def validate_offered_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Enter a price above zero.')
        return value

    def validate_pickup_date(self, value):
        if value is not None and value < timezone.localdate():
            raise serializers.ValidationError('The pickup date cannot be in the past.')
        return value

    def validate(self, attrs):
        if attrs.get('pickup') and attrs.get('pickup') == attrs.get('destination'):
            raise serializers.ValidationError(
                {'destination': 'The destination must be a different town from the pickup.'})
        if attrs.get('urgency') == 'scheduled' and not attrs.get('pickup_date'):
            raise serializers.ValidationError({'pickup_date': 'Choose a pickup date for a scheduled load.'})
        if attrs.get('insured') and not attrs.get('insurance_provider'):
            raise serializers.ValidationError({'insurance_provider': 'Enter the insurance provider.'})
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'message', 'url', 'is_read', 'created_at']


class LedgerEntrySerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ['id', 'amount', 'kind', 'kind_label', 'note', 'created_at']


class WalletSerializer(serializers.Serializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    entries = LedgerEntrySerializer(many=True)


class PriceGuideQuerySerializer(serializers.Serializer):
    pickup = serializers.ChoiceField(choices=TOWN_NAMES)
    destination = serializers.ChoiceField(choices=TOWN_NAMES)
    tonnes = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal('0.1'), max_value=Decimal('500'))


class PriceGuideSerializer(serializers.Serializer):
    distance_km = serializers.IntegerField()
    suggested = serializers.IntegerField()
    low = serializers.IntegerField()
    high = serializers.IntegerField()
    basis = serializers.CharField()
    samples = serializers.IntegerField()
    note = serializers.CharField()