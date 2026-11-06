from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import Notification
from accounts.notify import notify
from loads.learning import refine
from loads.models import Load, Offer, OfferEvent
from loads.pricing import suggest_price
from loads.services import run_housekeeping
from trucks.models import Truck
from wallet.services import balance

from . import actions
from .permissions import IsShipper, IsTransporter
from .rules import Conflict, needs_verification, role_of
from .serializers import (CounterSerializer, LoadCreateSerializer, LoadDetailSerializer,
                          LoadSerializer, MeSerializer, NotificationSerializer,
                          OfferCreateSerializer, OfferSerializer, PriceGuideQuerySerializer,
                          PriceGuideSerializer, TruckOwnSerializer, TruckPublicSerializer,
                          WalletSerializer)
from wallet.models import LedgerEntry


# ---------------------------------------------------------------- sign in

class LoginView(ObtainAuthToken):
    """Exchange a username and password for an API token."""
    # ObtainAuthToken switches throttling off by default, so it is switched back on here.
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = 'login'
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(summary='Get an API token',
                   responses={200: {'type': 'object', 'properties': {'token': {'type': 'string'}}}})
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        token, _ = Token.objects.get_or_create(user=serializer.validated_data['user'])
        return Response({'token': token.key})


class LogoutView(APIView):
    @extend_schema(summary='Delete the token you are using', request=None, responses={204: None})
    def post(self, request):
        if isinstance(request.auth, Token):
            request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(summary='Your account', responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user).data)


# ---------------------------------------------------------------- price guide

class PriceGuideView(APIView):
    @extend_schema(summary='Suggested price for a route and weight',
                   parameters=[PriceGuideQuerySerializer], responses=PriceGuideSerializer)
    def get(self, request):
        query = PriceGuideQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        tonnes = float(data['tonnes'])
        result = suggest_price(data['pickup'], data['destination'], tonnes)
        if result is None:
            return Response({'detail': 'Choose two different towns.'}, status=status.HTTP_400_BAD_REQUEST)
        result = refine(result, data['pickup'], data['destination'], tonnes)
        return Response(PriceGuideSerializer(result).data)


# ---------------------------------------------------------------- loads

def _open_loads(params):
    loads = Load.objects.filter(status='open').select_related('shipper')
    if params.get('pickup'):
        loads = loads.filter(pickup=params['pickup'])
    if params.get('destination'):
        loads = loads.filter(destination=params['destination'])
    if params.get('cargo'):
        loads = loads.filter(cargo_type=params['cargo'])
    if params.get('truck'):
        loads = loads.filter(truck_type_needed__in=['any', params['truck']])
    urgent_first = Case(When(urgency='urgent', then=Value(0)), default=Value(1),
                        output_field=IntegerField())
    return loads.annotate(urgent_first=urgent_first).order_by('urgent_first', '-created_at')


LOAD_FILTERS = [
    OpenApiParameter('pickup', OpenApiTypes.STR, description='Pickup town'),
    OpenApiParameter('destination', OpenApiTypes.STR, description='Destination town'),
    OpenApiParameter('cargo', OpenApiTypes.STR, description='Cargo type, for example general or perishable'),
    OpenApiParameter('truck', OpenApiTypes.STR, description='Show loads that this truck type can take'),
]


class LoadListView(generics.ListAPIView):
    serializer_class = LoadSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Load.objects.none()
        run_housekeeping()
        return _open_loads(self.request.query_params)

    @extend_schema(summary='Open loads, urgent first', parameters=LOAD_FILTERS)
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    @extend_schema(summary='Post a load (shippers)', request=LoadCreateSerializer,
                   responses={201: LoadSerializer})
    def post(self, request, *args, **kwargs):
        if role_of(request.user) != 'shipper':
            raise PermissionDenied('Only shippers can post loads.')
        if needs_verification(request.user):
            raise PermissionDenied('Verify your identity before you post a load.')
        serializer = LoadCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        load = serializer.save(shipper=request.user)
        return Response(LoadSerializer(load, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class MyLoadsView(generics.ListAPIView):
    serializer_class = LoadSerializer
    permission_classes = [IsShipper]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Load.objects.none()
        run_housekeeping()
        return Load.objects.filter(shipper=self.request.user).select_related('shipper').order_by('-created_at')

    @extend_schema(summary='Loads you posted (shippers)')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class LoadDetailView(generics.RetrieveAPIView):
    serializer_class = LoadDetailSerializer
    queryset = Load.objects.select_related('shipper')

    @extend_schema(summary='One load, with your offer, booking and contacts when they apply to you')
    def get(self, request, *args, **kwargs):
        run_housekeeping()
        return self.retrieve(request, *args, **kwargs)


# ---------------------------------------------------------------- offers

def _offer_queryset():
    return (Offer.objects.select_related('load', 'transporter', 'truck')
            .prefetch_related('events__actor'))


class LoadOffersView(generics.ListAPIView):
    serializer_class = OfferSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Offer.objects.none()
        load = get_object_or_404(Load, pk=self.kwargs['pk'])
        offers = _offer_queryset().filter(load=load).order_by('-created_at')
        if load.shipper_id == self.request.user.id:
            return offers
        return offers.filter(transporter=self.request.user)

    @extend_schema(summary='Offers on a load: all of them for the shipper, only your own for a transporter')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    @extend_schema(summary='Send an offer (transporters)', request=OfferCreateSerializer,
                   responses={201: OfferSerializer})
    def post(self, request, pk):
        load = get_object_or_404(Load.objects.select_related('shipper'), pk=pk)
        user = request.user
        if role_of(user) != 'transporter':
            raise PermissionDenied('Only transporters can send offers.')
        if load.shipper_id == user.id:
            raise PermissionDenied('You cannot make an offer on your own load.')
        if needs_verification(user):
            raise PermissionDenied('Verify your identity before you send an offer.')
        if load.status != 'open':
            raise Conflict('This load is no longer open for offers.')
        active = load.offers.filter(transporter=user).exclude(
            status__in=['declined', 'withdrawn', 'expired'])
        if active.exists():
            raise Conflict('You already have an offer on this load. Withdraw it before you send another.')

        serializer = OfferCreateSerializer(data=request.data,
                                           context={'request': request, 'load': load})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            offer = serializer.save(load=load, transporter=user)
            OfferEvent.objects.create(offer=offer, actor=user, kind='offer', price=offer.price)
        notify(load.shipper, f'{user.username} offered ${offer.price} on "{load.title}".',
               reverse('load_detail', args=[load.pk]))
        offer = _offer_queryset().get(pk=offer.pk)
        return Response(OfferSerializer(offer, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class MyOffersView(generics.ListAPIView):
    serializer_class = OfferSerializer
    permission_classes = [IsTransporter]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Offer.objects.none()
        run_housekeeping()
        offers = _offer_queryset().filter(transporter=self.request.user).order_by('-created_at')
        wanted = self.request.query_params.get('status')
        return offers.filter(status=wanted) if wanted else offers

    @extend_schema(summary='Offers you made (transporters)',
                   parameters=[OpenApiParameter('status', OpenApiTypes.STR, description='For example countered or accepted')])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class _OfferAction(APIView):
    action = ''

    def post(self, request, pk):
        price = None
        if self.action == 'counter':
            body = CounterSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            price = body.validated_data['price']
        offer = actions.perform(pk, request.user, self.action, price)
        offer = _offer_queryset().get(pk=offer.pk)
        return Response(OfferSerializer(offer, context={'request': request}).data)


@extend_schema(summary='Accept the offer at its current price', request=None, responses=OfferSerializer)
class OfferAcceptView(_OfferAction):
    action = 'accept'


@extend_schema(summary='Decline the offer', request=None, responses=OfferSerializer)
class OfferDeclineView(_OfferAction):
    action = 'decline'


@extend_schema(summary='Answer with a new price', request=CounterSerializer, responses=OfferSerializer)
class OfferCounterView(_OfferAction):
    action = 'counter'


@extend_schema(summary='Withdraw your offer (transporters)', request=None, responses=OfferSerializer)
class OfferWithdrawView(_OfferAction):
    action = 'withdraw'


# ---------------------------------------------------------------- trucks

class TruckListView(generics.ListAPIView):
    serializer_class = TruckPublicSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Truck.objects.none()
        today = timezone.localdate()
        trucks = (Truck.objects.filter(is_available=True)
                  .exclude(insurance_expiry__lt=today).exclude(roadworthy_expiry__lt=today)
                  .select_related('owner').order_by('-created_at'))
        params = self.request.query_params
        if params.get('type'):
            trucks = trucks.filter(truck_type=params['type'])
        if params.get('location'):
            trucks = trucks.filter(current_location=params['location'])
        if params.get('min_capacity'):
            try:
                trucks = trucks.filter(capacity_tonnes__gte=Decimal(params['min_capacity']))
            except InvalidOperation:
                pass
        return trucks

    @extend_schema(summary='Available trucks',
                   parameters=[OpenApiParameter('type', OpenApiTypes.STR),
                               OpenApiParameter('location', OpenApiTypes.STR),
                               OpenApiParameter('min_capacity', OpenApiTypes.NUMBER)])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class MyTrucksView(generics.ListAPIView):
    serializer_class = TruckOwnSerializer
    permission_classes = [IsTransporter]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Truck.objects.none()
        return Truck.objects.filter(owner=self.request.user).order_by('-created_at')

    @extend_schema(summary='Your own trucks, with document dates (transporters)')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


# ---------------------------------------------------------------- wallet and notifications

class WalletView(APIView):
    @extend_schema(summary='Your simulated wallet balance and recent entries', responses=WalletSerializer)
    def get(self, request):
        entries = LedgerEntry.objects.filter(user=request.user)[:50]
        return Response(WalletSerializer({'balance': balance(request.user), 'entries': entries}).data)


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    @extend_schema(summary='Your notifications, newest first')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class NotificationReadView(APIView):
    @extend_schema(summary='Mark all your notifications as read', request=None,
                   responses={200: {'type': 'object', 'properties': {'marked': {'type': 'integer'}}}})
    def post(self, request):
        marked = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'marked': marked})