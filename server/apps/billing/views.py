from pathlib import Path
from datetime import timedelta, datetime, time
import calendar
import secrets
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from django.shortcuts import render
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import re
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Sum, Count, F, Case, When, Value, DecimalField, Q
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from .models import (
    Computer, Tariff, Session, Category, Product, Order, OrderItem, Expense, Game, StockSupply,
    Customer, CustomerTransaction, ClientBuild, AuditLog
)
from .serializers import (
    ComputerSerializer, TariffSerializer, SessionSerializer,
    CategorySerializer, ProductSerializer, OrderSerializer, OrderItemSerializer, ExpenseSerializer,
    GameSerializer, StockSupplySerializer,
    CustomerSerializer, CustomerTransactionSerializer, ClientBuildSerializer, AuditLogSerializer
)
from .consumers import notify_pc_status_change, notify_bar_order_change
from .permissions import HasClientApiKey, IsStaffOrHasApiKey

# Balans to'ldirish bonus bosqichlari — (chegara, bonus) juftliklari,
# chegara BO'YICHA KAMAYISH tartibida. Mijoz to'ldirgan summa eng
# yuqori mos keladigan chegaraga yetsa/oshsa, o'sha bonus qo'shiladi
# (masalan 150,000 UZS to'ldirilsa — faqat 100,000'lik bosqich
# qo'llaniladi, ikkalasi qo'shilmaydi).
TOPUP_BONUS_TIERS = [
    (200_000, 50_000),
    (100_000, 20_000),
]


def _log_action(request, action_key, description):
    """Muhim admin/xodim amallarini AuditLog'ga yozadi (kim, qachon, nima qildi)."""
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    AuditLog.objects.create(user=user, action=action_key, description=description)


def _normalize_phone_core(phone):
    """Telefon raqamni solishtirish uchun "asosiy" (mamlakat kodisiz)
    9 xonali shaklga keltiradi — xodim dashboard'da "+998 90 111 22 33"
    deb kiritgan bo'lishi mumkin, mijoz esa kiosk'da shunchaki
    "90 111 22 33" yoki "0901112233" deb yozishi mumkin. Ikkalasi ham
    bitta odamni anglatishi kerak."""
    digits = re.sub(r'\D', '', str(phone or ''))
    if digits.startswith('998') and len(digits) == 12:
        digits = digits[3:]
    elif digits.startswith('0') and len(digits) == 10:
        digits = digits[1:]
    return digits


KIOSK_SESSION_TOKEN_TTL_SECONDS = 600  # 10 daqiqa

def _create_kiosk_session_token(customer_id):
    """kiosk_login muvaffaqiyatli bo'lgach chaqiriladi — mijoz ID'sini
    o'zi bilan taxmin qilib bo'lmaydigan, muddati cheklangan tokenga
    bog'laydi. customer_start_session ENDI xom customer_id'ga emas,
    shu tokenga ishonadi — aks holda istalgan kiosk (umumiy API kalit
    bilan) boshqa mijozning ID raqamini taxmin qilib, uning
    balansidan pul yechib qo'yishi mumkin edi."""
    token = secrets.token_urlsafe(24)
    cache.set(f"kiosk_session:{token}", customer_id, timeout=KIOSK_SESSION_TOKEN_TTL_SECONDS)
    return token


def _resolve_kiosk_session_customer(request):
    token = request.data.get('session_token')
    if not token:
        return None, Response({'error': "Avval tizimga kiring."}, status=status.HTTP_401_UNAUTHORIZED)
    customer_id = cache.get(f"kiosk_session:{token}")
    if not customer_id:
        return None, Response({'error': "Sessiya tugagan, qayta kiring."}, status=status.HTTP_401_UNAUTHORIZED)
    customer = Customer.objects.filter(id=customer_id).first()
    if not customer:
        return None, Response({'error': "Mijoz topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
    return customer, None


def _calculate_session_duration_and_price(pc, active_session, start_time, tariff, now):
    """Shared by finish_summary and stop_session so both always agree on the charge."""
    duration_minutes = 0
    time_price = 0.0

    if pc.is_open_time and start_time:
        elapsed_seconds = max(0, (now - start_time).total_seconds())
        duration_minutes = round(elapsed_seconds / 60.0)
        price_per_min = (tariff.get_effective_price_per_hour() / 60.0) if tariff else 200.0
        time_price = round(price_per_min * duration_minutes)
    elif active_session and active_session.duration_minutes > 0:
        duration_minutes = active_session.duration_minutes
        time_price = float(active_session.total_price)
    elif start_time:
        if pc.session_end_time:
            duration_minutes = round(max(0, (pc.session_end_time - start_time).total_seconds()) / 60.0)
        else:
            duration_minutes = round(max(0, (now - start_time).total_seconds()) / 60.0)
        price_per_min = (tariff.get_effective_price_per_hour() / 60.0) if tariff else 200.0
        time_price = round(price_per_min * duration_minutes)

    return duration_minutes, time_price


def _split_payment(payment_method, grand_total, req_cash, req_card):
    """Shared CASH/CARD/SPLIT reconciliation used by session stop and bar-order creation."""
    if payment_method == 'CASH':
        return grand_total, 0.0
    elif payment_method == 'CARD':
        return 0.0, grand_total
    elif payment_method == 'SPLIT':
        final_cash = req_cash
        final_card = req_card
        if abs((final_cash + final_card) - grand_total) > 0.01:
            final_card = max(0.0, grand_total - final_cash)
        return final_cash, final_card
    else:
        return grand_total, 0.0


def _deduct_stock_for_order(order):
    """Shared by approve()/deliver()/stop_session() when a PENDING order clears."""
    for item in order.items.all():
        item.product.stock = max(0, item.product.stock - item.quantity)
        item.product.save()

class AdminLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            login(request, user)
            AuditLog.objects.create(user=user, action='LOGIN', description=f"{user.username} tizimga kirdi")
            return Response({'success': True, 'username': user.username, 'is_admin': True})
        return Response({'success': False, 'error': 'Invalid admin credentials'}, status=status.HTTP_401_UNAUTHORIZED)

class AdminLogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({'success': True})



class DashboardView(View):
    def get(self, request):
        return render(request, 'billing/dashboard.html')

class LauncherView(View):
    def get(self, request):
        return render(request, 'billing/launcher.html')


class TariffViewSet(viewsets.ModelViewSet):
    queryset = Tariff.objects.all().order_by('id')
    serializer_class = TariffSerializer

    def perform_update(self, serializer):
        old_price = serializer.instance.price_per_hour
        instance = serializer.save()
        if old_price != instance.price_per_hour:
            _log_action(
                self.request, 'TARIFF_CHANGED',
                f"Tarif '{instance.name}' narxi {old_price:,.0f} → {instance.price_per_hour:,.0f} UZS/soat ga o'zgartirildi"
            )

class GameViewSet(viewsets.ModelViewSet):
    queryset = Game.objects.filter(is_active=True).order_by('name')
    serializer_class = GameSerializer

    def get_permissions(self):
        if self.action == 'list':
            return [IsStaffOrHasApiKey()]
        return super().get_permissions()

class SessionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Session.objects.all().order_by('-start_time')
    serializer_class = SessionSerializer

class ComputerViewSet(viewsets.ModelViewSet):
    queryset = Computer.objects.all().order_by('name')
    serializer_class = ComputerSerializer

    def get_permissions(self):
        if self.action in ('heartbeat', 'upload_screenshot', 'customer_start_session', 'customer_stop_session'):
            return [HasClientApiKey()]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        for pc in queryset:
            pc.calculate_time_remaining()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.calculate_time_remaining()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def start_session(self, request, pk=None):
        pc = self.get_object()
        minutes = request.data.get('minutes')
        amount = request.data.get('amount')
        is_open_time = request.data.get('is_open_time', False) or (request.data.get('mode') == 'open')
        tariff_id = request.data.get('tariff_id')
        customer_id = request.data.get('customer_id')
        customer = Customer.objects.filter(id=customer_id).first() if customer_id else None

        tariff = Tariff.objects.filter(id=tariff_id).first() if tariff_id else pc.current_tariff or Tariff.objects.first()

        now = timezone.now()
        effective_price_per_hour = tariff.get_effective_price_per_hour() if tariff else 12000.0
        price_per_minute = effective_price_per_hour / 60.0

        if is_open_time:
            end_time = None
            total_price = 0.0
            minutes = 0
            pc.is_open_time = True
            pc.time_remaining = 0
        else:
            pc.is_open_time = False
            if amount and float(amount) > 0:
                total_price = float(amount)
                minutes = round(total_price / price_per_minute)
            else:
                minutes = int(minutes) if minutes else 60
                total_price = price_per_minute * minutes
            end_time = now + timedelta(minutes=minutes)
            pc.time_remaining = minutes * 60

        pc.status = 'ACTIVE'
        pc.session_start_time = now
        pc.session_end_time = end_time
        pc.current_tariff = tariff
        pc.save()

        payment_method = request.data.get('payment_method', 'CASH')

        # End old active sessions for this PC
        Session.objects.filter(computer=pc, is_active=True).update(is_active=False, end_time=now)

        # Create new session
        Session.objects.create(
            computer=pc,
            tariff=tariff,
            customer=customer,
            is_open_time=is_open_time,
            start_time=now,
            end_time=end_time,
            duration_minutes=minutes,
            total_price=total_price,
            payment_method=payment_method,
            is_active=True
        )

        serializer = self.get_serializer(pc)
        notify_pc_status_change({
            'action': 'SESSION_STARTED',
            'pc': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def customer_start_session(self, request, pk=None):
        """Kiosk qulf ekranidan: mijoz o'zi tizimga kirgach, "Kompyuterni
        ochish" tugmasini bosganda chaqiriladi. Seans Open Time rejimida
        boshlanadi — pul darhol yechilmaydi, buni fon ishchisi
        (balance_worker.py) har 30 soniyada bosqichma-bosqich yechib
        boradi (balans tugasa, seansni o'zi to'xtatadi)."""
        pc = self.get_object()
        if pc.status != 'LOCKED':
            return Response({'error': "Bu kompyuter band yoki allaqachon faol."}, status=status.HTTP_400_BAD_REQUEST)

        # Xom customer_id EMAS — faqat kiosk_login muvaffaqiyatli
        # bo'lgandan keyin berilgan, taxmin qilib bo'lmaydigan tokenga
        # ishonamiz. Aks holda istalgan kiosk (umumiy API kalit bilan)
        # boshqa mijozning ID raqamini kiritib, uning balansidan pul
        # yechib qo'yishi mumkin edi.
        customer, error_response = _resolve_kiosk_session_customer(request)
        if error_response:
            return error_response

        tariff = pc.current_tariff or Tariff.objects.first()
        if not tariff:
            return Response({'error': "Tarif sozlanmagan, administratorga murojaat qiling."}, status=status.HTTP_400_BAD_REQUEST)

        price_per_minute = tariff.get_effective_price_per_hour() / 60.0
        if price_per_minute <= 0:
            # 0/manfiy narxli tarif bilan seans boshlashga yo'l
            # qo'yilmaydi — aks holda balans hech qachon yechilmay,
            # mijoz cheksiz bepul vaqtga ega bo'lib qolar edi
            # (balance_worker.py bunday holatda hisoblashni o'tkazib
            # yuboradi, chunki yechish uchun narx yo'q).
            return Response({'error': "Tarif narxi sozlanmagan, administratorga murojaat qiling."}, status=status.HTTP_400_BAD_REQUEST)
        min_required = round(price_per_minute * 3, 2)  # kamida 3 daqiqalik pul
        if float(customer.balance) < min_required:
            return Response(
                {'error': f"Balans yetarli emas (kamida {min_required:,.0f} UZS kerak, mavjud: {float(customer.balance):,.0f} UZS)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        now = timezone.now()
        # Shart bilan (status hali ham LOCKED bo'lsagina) bitta SQL
        # UPDATE orqali "band qilib olamiz" — bu ikkita bir vaqtdagi
        # so'rov (masalan tugma ikki marta bosilishi yoki tarmoq qayta
        # urinishi) bitta PC uchun ikkita faol seans yaratib
        # qo'yishining oldini oladi (aks holda balance_worker har
        # ikkalasidan ham pul yechardi).
        claimed = Computer.objects.filter(pk=pc.pk, status='LOCKED').update(
            status='ACTIVE', is_open_time=True, time_remaining=0,
            session_start_time=now, session_end_time=None, current_tariff=tariff
        )
        if not claimed:
            return Response({'error': "Bu kompyuter band yoki allaqachon faol."}, status=status.HTTP_400_BAD_REQUEST)
        pc.refresh_from_db()

        Session.objects.filter(computer=pc, is_active=True).update(is_active=False, end_time=now)
        Session.objects.create(
            computer=pc, tariff=tariff, customer=customer,
            is_open_time=True, start_time=now, end_time=None,
            duration_minutes=0, total_price=0.0, balance_deducted=0.0,
            payment_method='BALANCE', is_active=True
        )

        AuditLog.objects.create(
            action='CUSTOMER_LOGIN',
            description=f"{customer.full_name} ({customer.phone}) {pc.name}ni o'z balansidan ochdi"
        )

        serializer = self.get_serializer(pc)
        notify_pc_status_change({
            'action': 'SESSION_STARTED',
            'pc': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def customer_stop_session(self, request, pk=None):
        """Kiosk'dan: "Kabinet" oynasidan mijoz o'zi balansidan ochgan
        seansni o'zi to'xtatadi. Faqat shu mijozga tegishli, BALANCE
        to'lov usulidagi faol seans uchun ishlaydi — xodim boshlagan
        naqd/plastik seansni mijoz o'zi yopa olmaydi (xodim to'lovni
        yig'ib, rasmiylashtirishi shart)."""
        pc = self.get_object()
        customer, error_response = _resolve_kiosk_session_customer(request)
        if error_response:
            return error_response

        session = Session.objects.filter(computer=pc, is_active=True).first()
        if not session or session.customer_id != customer.id:
            return Response({'error': "Sizga tegishli faol seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        if session.payment_method != 'BALANCE':
            return Response(
                {'error': "Bu seansni faqat xodim to'xtata oladi (naqd/plastik to'lov kerak)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from . import balance_worker
        balance_worker.stop_balance_session(pc, session, customer, timezone.now(), reason="mijoz o'zi to'xtatdi:")
        return Response({'success': True})

    @action(detail=True, methods=['post'])
    def add_time(self, request, pk=None):
        pc = self.get_object()
        minutes = int(request.data.get('minutes', 30))

        now = timezone.now()
        if pc.status == 'ACTIVE' and pc.session_end_time and pc.session_end_time > now:
            pc.session_end_time += timedelta(minutes=minutes)
        else:
            pc.status = 'ACTIVE'
            pc.session_start_time = now
            pc.session_end_time = now + timedelta(minutes=minutes)

        pc.time_remaining = int((pc.session_end_time - now).total_seconds())
        pc.is_open_time = False
        pc.save()

        active_session = Session.objects.filter(computer=pc, is_active=True).first()
        if active_session:
            active_session.duration_minutes += minutes
            price_per_minute = (active_session.tariff.get_effective_price_per_hour() / 60) if active_session.tariff else 250
            active_session.total_price = float(active_session.total_price) + price_per_minute * minutes
            active_session.end_time = pc.session_end_time
            active_session.save()

        serializer = self.get_serializer(pc)
        notify_pc_status_change({
            'action': 'TIME_ADDED',
            'pc': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def finish_summary(self, request, pk=None):
        pc = self.get_object()
        now = timezone.now()
        active_session = Session.objects.filter(computer=pc, is_active=True).first()
        if not active_session:
            active_session = Session.objects.filter(computer=pc).order_by('-start_time').first()

        start_time = active_session.start_time if (active_session and active_session.start_time) else pc.session_start_time
        tariff = (active_session.tariff if active_session else None) or pc.current_tariff or Tariff.objects.first()
        tariff_name = tariff.name if tariff else "Standard"

        duration_minutes, time_price = _calculate_session_duration_and_price(pc, active_session, start_time, tariff, now)

        bar_items = []
        bar_total_price = 0.0

        # BALANCE buyurtmalar yaratilgan zahoti mijoz balansidan
        # yechilgan — xodim yakunlashda ularni QAYTA "to'lanishi kerak"
        # deb ko'rmasligi uchun bu yerdan chiqarib tashlanadi.
        if start_time:
            orders = Order.objects.filter(
                computer=pc,
                created_at__gte=start_time - timedelta(seconds=30)
            ).exclude(status='CANCELLED').exclude(payment_method='BALANCE')
        else:
            orders = Order.objects.filter(
                computer=pc,
                status__in=['PENDING', 'APPROVED', 'DELIVERED']
            ).exclude(status='CANCELLED').exclude(payment_method='BALANCE')

        items_map = {}
        for order in orders:
            for item in order.items.all():
                p_id = item.product.id
                if p_id not in items_map:
                    items_map[p_id] = {
                        'id': p_id,
                        'product_name': item.product.name,
                        'quantity': 0,
                        'unit_price': float(item.unit_price),
                        'total_price': 0.0
                    }
                items_map[p_id]['quantity'] += item.quantity
                item_cost = float(item.unit_price * item.quantity)
                items_map[p_id]['total_price'] += item_cost
                bar_total_price += item_cost
        bar_items = list(items_map.values())

        grand_total = time_price + bar_total_price
        payment_method = active_session.payment_method if active_session else 'CASH'

        return Response({
            'computer_id': pc.id,
            'computer_name': pc.name,
            'zone': pc.zone,
            'is_open_time': pc.is_open_time,
            'session_start_time': start_time.isoformat() if start_time else None,
            'duration_minutes': duration_minutes,
            'tariff_name': tariff_name,
            'time_price': time_price,
            'bar_items': bar_items,
            'bar_total_price': bar_total_price,
            'grand_total': grand_total,
            'payment_method': payment_method
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def stop_session(self, request, pk=None):
        pc = self.get_object()
        now = timezone.now()
        payment_method = request.data.get('payment_method', 'CASH')
        req_cash = float(request.data.get('cash_amount', 0.0))
        req_card = float(request.data.get('card_amount', 0.0))

        active_session = Session.objects.filter(computer=pc, is_active=True).first()
        if not active_session:
            active_session = Session.objects.filter(computer=pc).order_by('-start_time').first()

        start_time = active_session.start_time if (active_session and active_session.start_time) else pc.session_start_time
        tariff = (active_session.tariff if active_session else None) or pc.current_tariff or Tariff.objects.first()

        duration_minutes, time_price = _calculate_session_duration_and_price(pc, active_session, start_time, tariff, now)

        # payment_method='BALANCE' buyurtmalar bar buyurtma yaratilgan
        # zahoti mijoz balansidan allaqachon yechilgan (OrderViewSet.create)
        # — shuning uchun bu yerda xodimga QAYTA naqd/plastik sifatida
        # hisoblanmasligi kerak (aks holda mijoz ikki marta to'lagan
        # bo'lib chiqardi).
        if start_time:
            session_orders = Order.objects.filter(computer=pc, created_at__gte=start_time - timedelta(seconds=30)).exclude(status='CANCELLED').exclude(payment_method='BALANCE')
        else:
            session_orders = Order.objects.filter(computer=pc).exclude(status='CANCELLED').exclude(payment_method='BALANCE')

        bar_total_price = float(sum(o.total_price for o in session_orders))

        if active_session and active_session.payment_method == 'BALANCE':
            # Vaqt narxi allaqachon fon ishchisi (balance_worker.py)
            # orqali bosqichma-bosqich mijoz balansidan yechilgan —
            # bu yerda uni QAYTA naqd/plastik sifatida hisoblab
            # bo'lmaydi (aks holda mijoz ikki marta to'lagan bo'lib
            # chiqardi). Faqat shu seans davomidagi bar buyurtmalari
            # (bo'lsa) xodim ko'rsatgan to'lov usuli bilan alohida
            # hisoblanadi.
            bar_final_cash, bar_final_card = _split_payment(payment_method, bar_total_price, req_cash, req_card)

            active_session.duration_minutes = duration_minutes
            active_session.total_price = float(active_session.balance_deducted)
            active_session.cash_amount = 0.0
            active_session.card_amount = 0.0
            active_session.end_time = now
            active_session.is_active = False
            active_session.save()

            for order in session_orders:
                order.payment_method = payment_method
                if bar_total_price > 0:
                    o_ratio = float(order.total_price) / bar_total_price
                    order.cash_amount = round(bar_final_cash * o_ratio, 2)
                    order.card_amount = round(bar_final_card * o_ratio, 2)
                else:
                    order.cash_amount = 0.0
                    order.card_amount = 0.0
                if order.status == 'PENDING':
                    _deduct_stock_for_order(order)
                    order.status = 'DELIVERED'
                order.save()

            pc.status = 'LOCKED'
            pc.is_open_time = False
            pc.time_remaining = 0
            pc.session_start_time = None
            pc.session_end_time = None
            pc.current_tariff = None
            pc.save()

            _log_action(
                request, 'SESSION_STOPPED',
                f"{pc.name}: balans seansi yakunlandi, jami {float(active_session.balance_deducted):,.0f} UZS balansdan"
                + (f" + {bar_total_price:,.0f} UZS bar ({payment_method})" if bar_total_price > 0 else "")
            )

            serializer = self.get_serializer(pc)
            notify_pc_status_change({'action': 'SESSION_STOPPED', 'pc': serializer.data})
            return Response(serializer.data, status=status.HTTP_200_OK)

        grand_total = float(time_price) + bar_total_price

        final_cash, final_card = _split_payment(payment_method, grand_total, req_cash, req_card)

        if grand_total > 0:
            time_ratio = float(time_price) / grand_total
            sess_cash = round(final_cash * time_ratio, 2)
            sess_card = round(final_card * time_ratio, 2)
        else:
            sess_cash = final_cash
            sess_card = final_card

        if active_session:
            active_session.duration_minutes = duration_minutes
            active_session.total_price = time_price
            active_session.payment_method = payment_method
            active_session.cash_amount = sess_cash
            active_session.card_amount = sess_card
            active_session.end_time = now
            active_session.is_active = False
            active_session.save()
        else:
            active_session = Session.objects.create(
                computer=pc,
                tariff=tariff,
                is_open_time=pc.is_open_time,
                start_time=start_time or now,
                end_time=now,
                duration_minutes=duration_minutes,
                total_price=time_price,
                payment_method=payment_method,
                cash_amount=sess_cash,
                card_amount=sess_card,
                is_active=False
            )

        for order in session_orders:
            order.payment_method = payment_method
            if grand_total > 0:
                o_ratio = float(order.total_price) / grand_total
                order.cash_amount = round(final_cash * o_ratio, 2)
                order.card_amount = round(final_card * o_ratio, 2)
            else:
                order.cash_amount = float(order.total_price) if payment_method == 'CASH' else 0.0
                order.card_amount = float(order.total_price) if payment_method == 'CARD' else 0.0

            if order.status == 'PENDING':
                _deduct_stock_for_order(order)
                order.status = 'DELIVERED'
            order.save()

        pc.status = 'LOCKED'
        pc.is_open_time = False
        pc.time_remaining = 0
        pc.session_start_time = None
        pc.session_end_time = None
        pc.current_tariff = None
        pc.save()

        _log_action(request, 'SESSION_STOPPED', f"{pc.name}: seans yakunlandi, jami {grand_total:,.0f} UZS ({payment_method})")

        serializer = self.get_serializer(pc)
        notify_pc_status_change({
            'action': 'SESSION_STOPPED',
            'pc': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def emergency_lock(self, request, pk=None):
        pc = self.get_object()
        now = timezone.now()

        pc.status = 'LOCKED'
        pc.time_remaining = 0
        pc.is_open_time = False
        pc.session_start_time = None
        pc.session_end_time = None
        pc.save()

        Session.objects.filter(computer=pc, is_active=True).update(is_active=False, end_time=now)

        _log_action(request, 'EMERGENCY_LOCK', f"{pc.name} favqulodda bloklandi")

        serializer = self.get_serializer(pc)
        notify_pc_status_change({
            'action': 'EMERGENCY_LOCK',
            'pc': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def emergency_lock_all(self, request):
        now = timezone.now()
        computers = Computer.objects.all()
        for pc in computers:
            pc.status = 'LOCKED'
            pc.time_remaining = 0
            pc.is_open_time = False
            pc.session_start_time = None
            pc.session_end_time = None
            pc.save()

        Session.objects.filter(is_active=True).update(is_active=False, end_time=now)

        _log_action(request, 'EMERGENCY_LOCK', "Barcha kompyuterlar favqulodda bloklandi")

        notify_pc_status_change({
            'action': 'EMERGENCY_LOCK_ALL'
        })
        return Response({'status': 'All PCs emergency locked'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def remote_shutdown(self, request, pk=None):
        """Dashboarddan: shu kompyuterni Windows darajasida o'chiradi.
        Buyruq WebSocket orqali kiosk klientiga yuboriladi — klient
        o'zi "shutdown" buyrug'ini bajaradi (server kompyuterni
        to'g'ridan-to'g'ri o'chira olmaydi, faqat signal beradi)."""
        pc = self.get_object()
        _log_action(request, 'REMOTE_SHUTDOWN', f"{pc.name}: uzoqdan o'chirish buyrug'i yuborildi")
        notify_pc_status_change({
            'action': 'REMOTE_COMMAND',
            'command': 'SHUTDOWN',
            'target': pc.name
        })
        return Response({'success': True})

    @action(detail=False, methods=['post'])
    def shutdown_all_pcs(self, request):
        """Barcha kiosk kompyuterlarni birdaniga o'chiradi (klub
        yopilganda)."""
        _log_action(request, 'REMOTE_SHUTDOWN', "Barcha kompyuterlarga uzoqdan o'chirish buyrug'i yuborildi")
        notify_pc_status_change({
            'action': 'REMOTE_COMMAND',
            'command': 'SHUTDOWN',
            'target': 'ALL'
        })
        return Response({'success': True})

    @action(detail=True, methods=['post'])
    def force_close_app(self, request, pk=None):
        """Dashboarddan: shu kompyuterda muzlab/qotib qolgan
        o'yin/dasturni majburan yopadi (kompyuterning o'zi, Windows'i
        ishlab tursa — butunlay qotib qolgan kompyuterni bu buyruq
        qutqara olmaydi, chunki klientning o'zi ham javob bermay
        qoladi)."""
        pc = self.get_object()
        _log_action(request, 'FORCE_CLOSE_APP', f"{pc.name}: dasturni majburan yopish buyrug'i yuborildi")
        notify_pc_status_change({
            'action': 'REMOTE_COMMAND',
            'command': 'FORCE_CLOSE_APP',
            'target': pc.name
        })
        return Response({'success': True})

    @action(detail=False, methods=['post'])
    def heartbeat(self, request):
        pc_name = request.data.get('pc_name')
        ip_addr = request.data.get('ip_address')
        mac_addr = request.data.get('mac_address', '')

        if not pc_name:
            return Response({'error': 'pc_name is required'}, status=status.HTTP_400_BAD_REQUEST)

        pc, created = Computer.objects.get_or_create(
            name=pc_name,
            defaults={'ip_address': ip_addr or '127.0.0.1', 'mac_address': mac_addr, 'status': 'LOCKED'}
        )

        if ip_addr:
            pc.ip_address = ip_addr
        if mac_addr:
            pc.mac_address = mac_addr
        pc.calculate_time_remaining()
        pc.save()

        serializer = self.get_serializer(pc)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def upload_screenshot(self, request, pk=None):
        """Kiosk klienti (client_locker.py) davriy ravishda o'z ekran
        rasmini shu yerga yuklaydi — masofadan monitoring uchun."""
        pc = self.get_object()
        screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots'
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        path = screenshots_dir / f"{pc.id}.png"
        with open(path, 'wb') as f:
            f.write(request.body)
        return Response({'status': 'ok'})

    @action(detail=True, methods=['get'])
    def screenshot(self, request, pk=None):
        """Admin panelidan: shu PC uchun oxirgi yuklangan skrinshotni
        qaytaradi. Faqat tizimga kirgan xodim uchun (standart
        IsAuthenticated ruxsati, kiosk API kaliti bu yerga yetarli emas)."""
        pc = self.get_object()
        path = Path(settings.MEDIA_ROOT) / 'screenshots' / f"{pc.id}.png"
        if not path.exists():
            return Response({'error': "Skrinshot hali mavjud emas"}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(open(path, 'rb'), content_type='image/png')

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('id')
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action == 'list':
            return [IsStaffOrHasApiKey()]
        return super().get_permissions()

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('category', 'name')
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.action == 'list':
            return [IsStaffOrHasApiKey()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        product = self.get_object()
        quantity = int(request.data.get('quantity', 10))
        product.stock += quantity
        product.save()
        serializer = self.get_serializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def internal_expense(self, request):
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        employee_name = request.data.get('employee_name', 'Barman / Admin')
        reason = request.data.get('reason', 'Ichki rasxod / Spisaniye')

        if not product_id:
            return Response({'error': 'Mahsulot tanlanmagan!'}, status=status.HTTP_400_BAD_REQUEST)

        product = Product.objects.filter(id=product_id).first()
        if not product:
            return Response({'error': 'Mahsulot topilmadi!'}, status=status.HTTP_400_BAD_REQUEST)

        if product.stock < quantity:
            return Response({'error': f'{product.name} omborda yetarli emas! (Mavjud: {product.stock})'}, status=status.HTTP_400_BAD_REQUEST)

        product.stock -= quantity
        product.save()

        total_cost = float(product.price * quantity)

        expense = Expense.objects.create(
            amount=total_cost,
            payment_method='CASH',
            category='Bar Rasxodi (Spisaniye)',
            recipient_name=employee_name,
            description=f"Spisaniye: {quantity}x {product.name} ({total_cost:,.0f} UZS). Izoh: {reason}"
        )

        notify_bar_order_change({
            'action': 'INTERNAL_EXPENSE',
            'product_id': product.id,
            'new_stock': product.stock
        })

        return Response({
            'success': True,
            'product_name': product.name,
            'remaining_stock': product.stock,
            'expense_id': expense.id,
            'amount': total_cost
        }, status=status.HTTP_200_OK)

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsStaffOrHasApiKey()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        pc_name = request.data.get('pc_name')
        computer_id = request.data.get('computer')
        items_data = request.data.get('items', [])
        is_direct_sale = request.data.get('is_direct_sale', False) or request.data.get('direct_sale', False)
        payment_method = request.data.get('payment_method', 'CASH')
        order_status = request.data.get('status', 'PENDING')

        if not items_data:
            return Response({'error': 'Buyurtmada tovarlar yo\'q!'}, status=status.HTTP_400_BAD_REQUEST)

        computer = None
        if not is_direct_sale:
            if pc_name:
                computer = Computer.objects.filter(name=pc_name).first()
            elif computer_id:
                computer = Computer.objects.filter(id=computer_id).first()

            if not computer:
                return Response({'error': 'Kompyuter topilmadi!'}, status=status.HTTP_400_BAD_REQUEST)

        total_price = 0
        order_items_to_create = []

        for item in items_data:
            prod_id = item.get('product_id') or item.get('product')
            qty = int(item.get('quantity', 1))
            product = Product.objects.filter(id=prod_id).first()
            if not product:
                return Response({'error': f'Mahsulot topilmadi (ID: {prod_id})'}, status=status.HTTP_400_BAD_REQUEST)
            if product.stock < qty:
                return Response({'error': f'{product.name} omborda yetarli emas! (Mavjud: {product.stock})'}, status=status.HTTP_400_BAD_REQUEST)

            item_price = product.price * qty
            total_price += item_price
            order_items_to_create.append({
                'product': product,
                'quantity': qty,
                'unit_price': product.price
            })

        if is_direct_sale:
            order_status = 'DELIVERED'

        # Agar bu PC'da hozir mijoz o'z balansidan ochgan (BALANCE) seans
        # faol bo'lsa — bar buyurtmasi ham darhol o'sha mijozning
        # balansidan yechiladi (naqd/plastik emas), xuddi vaqt kabi.
        # Buning sababi: mijoz o'zi Kabinetdan seansni tugatib ketganda,
        # xodim hech qachon "ko'rmagan" holda to'lanmagan bar buyurtmasi
        # osilib qolmasligi kerak — mijoz allaqachon jismonan ketgan
        # bo'lishi mumkin.
        balance_session = None
        if computer:
            balance_session = Session.objects.filter(
                computer=computer, is_active=True, payment_method='BALANCE', customer__isnull=False
            ).select_related('customer').first()

        if balance_session:
            customer = balance_session.customer
            charge = float(total_price)
            updated = Customer.objects.filter(pk=customer.pk, balance__gte=charge).update(balance=F('balance') - charge)
            if not updated:
                return Response(
                    {'error': f"Balansda yetarli mablag' yo'q (kerak: {charge:,.0f} UZS)."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            customer.refresh_from_db(fields=['balance'])
            payment_method = 'BALANCE'
            cash_amt, card_amt = 0.0, 0.0
        else:
            cash_amt, card_amt = _split_payment(
                payment_method, float(total_price),
                float(request.data.get('cash_amount', 0.0)),
                float(request.data.get('card_amount', 0.0))
            )

        order = Order.objects.create(
            computer=computer,
            total_price=total_price,
            cash_amount=cash_amt,
            card_amount=card_amt,
            payment_method=payment_method,
            status=order_status
        )

        for oi in order_items_to_create:
            OrderItem.objects.create(
                order=order,
                product=oi['product'],
                quantity=oi['quantity'],
                unit_price=oi['unit_price']
            )

        if order_status in ('APPROVED', 'DELIVERED'):
            for oi in order_items_to_create:
                oi['product'].stock = max(0, oi['product'].stock - oi['quantity'])
                oi['product'].save()

        if balance_session:
            # Kabinetning "Jami harakatlar" ro'yxatida aniq nima
            # sotib olinganini ko'rsatish uchun — mahsulot nomi(lari)
            # to'g'ridan-to'g'ri note'ga yoziladi (masalan
            # "Cola 250ml" yoki bir nechta mahsulot bo'lsa
            # "Cola 250ml x2, Chips x1").
            item_summary = ", ".join(
                oi['product'].name + (f" x{oi['quantity']}" if oi['quantity'] > 1 else "")
                for oi in order_items_to_create
            )
            CustomerTransaction.objects.create(
                customer=balance_session.customer, type='SPEND', amount=total_price,
                balance_after=balance_session.customer.balance,
                note=item_summary or f"{computer.name}: bar buyurtma #{order.id}"
            )

        serializer = self.get_serializer(order)
        notify_bar_order_change({
            'action': 'NEW_ORDER',
            'order': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        order = self.get_object()
        if order.status == 'PENDING':
            _deduct_stock_for_order(order)

        order.status = 'APPROVED'
        order.save()

        _log_action(request, 'ORDER_APPROVED', f"Buyurtma #{order.id} tasdiqlandi ({order.total_price:,.0f} UZS)")

        serializer = self.get_serializer(order)
        notify_bar_order_change({
            'action': 'ORDER_APPROVED',
            'order': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def deliver(self, request, pk=None):
        order = self.get_object()
        if order.status == 'PENDING':
            _deduct_stock_for_order(order)

        order.status = 'DELIVERED'
        order.save()

        _log_action(request, 'ORDER_DELIVERED', f"Buyurtma #{order.id} yetkazildi ({order.total_price:,.0f} UZS)")

        serializer = self.get_serializer(order)
        notify_bar_order_change({
            'action': 'ORDER_DELIVERED',
            'order': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status in ('APPROVED', 'DELIVERED'):
            for item in order.items.all():
                item.product.stock += item.quantity
                item.product.save()

        order.status = 'CANCELLED'
        order.save()

        _log_action(request, 'ORDER_CANCELLED', f"Buyurtma #{order.id} bekor qilindi ({order.total_price:,.0f} UZS)")

        serializer = self.get_serializer(order)
        notify_bar_order_change({
            'action': 'ORDER_CANCELLED',
            'order': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        valid_orders = Order.objects.filter(status__in=['APPROVED', 'DELIVERED'])
        total_revenue = float(valid_orders.aggregate(Sum('total_price'))['total_price__sum'] or 0.00)
        total_orders_count = Order.objects.count()
        pending_orders_count = Order.objects.filter(status='PENDING').count()

        bar_cogs = float(OrderItem.objects.filter(order__status__in=['APPROVED', 'DELIVERED']).aggregate(
            total_cogs=Sum(F('quantity') * F('product__cost_price'))
        )['total_cogs'] or 0.00)
        bar_gross_profit = total_revenue - bar_cogs

        low_stock_products = Product.objects.filter(stock__lt=5).order_by('stock')
        low_stock_serializer = ProductSerializer(low_stock_products, many=True)

        all_products = Product.objects.all().order_by('stock')
        inventory_serializer = ProductSerializer(all_products, many=True)

        top_selling_items = OrderItem.objects.filter(order__status__in=['APPROVED', 'DELIVERED']).values('product__name', 'product__image').annotate(
            total_sold=Sum('quantity'),
            total_amount=Sum(F('quantity') * F('unit_price'))
        ).order_by('-total_sold')[:5]

        return Response({
            'total_revenue': total_revenue,
            'bar_cogs': bar_cogs,
            'bar_gross_profit': bar_gross_profit,
            'total_orders_count': total_orders_count,
            'pending_orders_count': pending_orders_count,
            'low_stock_count': low_stock_products.count(),
            'low_stock_products': low_stock_serializer.data,
            'inventory': inventory_serializer.data,
            'top_selling': list(top_selling_items)
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class StockSupplyViewSet(viewsets.ModelViewSet):
    queryset = StockSupply.objects.all().order_by('-created_at')
    serializer_class = StockSupplySerializer

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product_id')
        product_name = request.data.get('product_name', '').strip()
        product_image = request.data.get('product_image', '').strip()
        quantity = int(request.data.get('quantity', 1))
        cost_price = float(request.data.get('cost_price', 0.0))
        selling_price = float(request.data.get('selling_price', 0.0))
        payment_method = request.data.get('payment_method', 'CASH')
        supplier_note = request.data.get('supplier_note', '').strip()

        total_cost = quantity * cost_price

        product = None
        if product_id:
            product = Product.objects.filter(id=product_id).first()
        if not product and product_name:
            product = Product.objects.filter(name__iexact=product_name).first()

        if not product:
            if not product_name:
                return Response({'error': 'Iltimos, mahsulotni tanlang yoki yangi mahsulot nomini kiriting!'}, status=status.HTTP_400_BAD_REQUEST)
            
            default_category = Category.objects.first()
            product_kwargs = dict(
                name=product_name,
                cost_price=cost_price,
                price=selling_price,
                stock=0,
                category=default_category,
                is_available=True
            )
            # Rasm URL kiritilmasa, Product modelining standart (umumiy
            # "placeholder") rasmi ishlatiladi — shuning uchun bu maydon
            # faqat foydalanuvchi haqiqatan URL kiritganda beriladi.
            if product_image:
                product_kwargs['image'] = product_image
            product = Product.objects.create(**product_kwargs)

        product.stock += quantity
        if cost_price > 0:
            product.cost_price = cost_price
        if selling_price > 0:
            product.price = selling_price
        product.save()

        supply = StockSupply.objects.create(
            product=product,
            product_name=product.name,
            quantity=quantity,
            cost_price=cost_price,
            selling_price=selling_price,
            total_cost=total_cost,
            payment_method=payment_method,
            supplier_note=supplier_note
        )

        note_str = f" ({supplier_note})" if supplier_note else ""
        Expense.objects.create(
            amount=total_cost,
            payment_method=payment_method,
            category='Tovar Kirimi',
            recipient_name=supplier_note or product.name,
            description=f"{quantity}x {product.name} kirim qilindi (@ {cost_price:,.0f} UZS){note_str}"
        )

        _log_action(request, 'STOCK_SUPPLY', f"{quantity}x {product.name} kirim qilindi ({total_cost:,.0f} UZS)")

        serializer = self.get_serializer(supply)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by('-created_at')
    serializer_class = ExpenseSerializer

    def perform_create(self, serializer):
        expense = serializer.save()
        _log_action(
            self.request, 'EXPENSE_CREATED',
            f"Rasxod: {expense.amount:,.0f} UZS ({expense.category})" + (f" - {expense.recipient_name}" if expense.recipient_name else "")
        )

    @action(detail=False, methods=['get'])
    def cashflow(self, request):
        period = request.query_params.get('period', 'daily')
        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')

        now = timezone.localtime()

        if period == 'monthly':
            start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            _, last_day = calendar.monthrange(now.year, now.month)
            end_dt = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
        elif period == 'yearly':
            start_dt = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_dt = now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        elif period == 'custom' and date_from_str and date_to_str:
            try:
                df = datetime.strptime(date_from_str, '%Y-%m-%d')
                dt = datetime.strptime(date_to_str, '%Y-%m-%d')
                start_dt = timezone.make_aware(datetime.combine(df.date(), time.min))
                end_dt = timezone.make_aware(datetime.combine(dt.date(), time.max))
            except Exception:
                start_dt = timezone.make_aware(datetime.combine(now.date(), time.min))
                end_dt = timezone.make_aware(datetime.combine(now.date(), time.max))
        else:
            start_dt = timezone.make_aware(datetime.combine(now.date(), time.min))
            end_dt = timezone.make_aware(datetime.combine(now.date(), time.max))

        sessions_qs = Session.objects.filter(start_time__range=(start_dt, end_dt))
        session_cash = float(sessions_qs.aggregate(
            total=Sum(Case(
                When(payment_method='CASH', then='total_price'),
                When(payment_method='CARD', then=Value(0)),
                default='cash_amount',
                output_field=DecimalField()
            ))
        )['total'] or 0.0)

        session_card = float(sessions_qs.aggregate(
            total=Sum(Case(
                When(payment_method='CARD', then='total_price'),
                When(payment_method='CASH', then=Value(0)),
                default='card_amount',
                output_field=DecimalField()
            ))
        )['total'] or 0.0)

        orders_qs = Order.objects.filter(status__in=['APPROVED', 'DELIVERED'], created_at__range=(start_dt, end_dt))
        bar_cash = float(orders_qs.aggregate(
            total=Sum(Case(
                When(payment_method='CASH', then='total_price'),
                When(payment_method='CARD', then=Value(0)),
                default='cash_amount',
                output_field=DecimalField()
            ))
        )['total'] or 0.0)

        bar_card = float(orders_qs.aggregate(
            total=Sum(Case(
                When(payment_method='CARD', then='total_price'),
                When(payment_method='CASH', then=Value(0)),
                default='card_amount',
                output_field=DecimalField()
            ))
        )['total'] or 0.0)
        total_bar = bar_cash + bar_card

        bar_cogs = float(OrderItem.objects.filter(order__in=orders_qs).aggregate(
            total_cogs=Sum(F('quantity') * F('product__cost_price'))
        )['total_cogs'] or 0.0)
        bar_margin = total_bar - bar_cogs
        bar_margin_percent = round((bar_margin / total_bar * 100), 1) if total_bar > 0 else 0.0

        expenses_qs = Expense.objects.filter(created_at__range=(start_dt, end_dt)).order_by('-created_at')
        expense_cash = float(expenses_qs.filter(payment_method='CASH').aggregate(Sum('amount'))['amount__sum'] or 0.0)
        expense_card = float(expenses_qs.filter(payment_method='CARD').aggregate(Sum('amount'))['amount__sum'] or 0.0)

        cash_balance = (session_cash + bar_cash) - expense_cash
        card_balance = (session_card + bar_card) - expense_card
        total_balance = cash_balance + card_balance
        total_expenses = expense_cash + expense_card
        total_revenue = session_cash + session_card + bar_cash + bar_card

        expense_serializer = ExpenseSerializer(expenses_qs, many=True)

        recent_sales = []
        for s in sessions_qs.filter(is_active=False).order_by('-end_time')[:15]:
            recent_sales.append({
                'id': f"session_{s.id}",
                'type': 'SESSION',
                'type_display': '🎮 Seans',
                'client_name': s.computer.name if s.computer else 'PC',
                'amount': float(s.total_price),
                'payment_method': s.payment_method,
                'payment_method_display': '💵 Naqd' if s.payment_method == 'CASH' else '💳 Plastik' if s.payment_method == 'CARD' else '🔀 Aralash',
                'created_at': (s.end_time or s.start_time).strftime('%Y-%m-%d %H:%M:%S'),
                'details': f"{s.tariff.name if s.tariff else 'Tarif'} ({s.duration_minutes} min)"
            })

        for o in orders_qs.order_by('-created_at')[:15]:
            items_str = ", ".join([f"{item.quantity}x {item.product.name}" for item in o.items.all()])
            pc_name = o.computer.name if o.computer else 'Tekzor Bar'
            recent_sales.append({
                'id': f"order_{o.id}",
                'type': 'BAR',
                'type_display': '🍸 Bar',
                'client_name': pc_name,
                'amount': float(o.total_price),
                'payment_method': o.payment_method,
                'payment_method_display': '💵 Naqd' if o.payment_method == 'CASH' else '💳 Plastik' if o.payment_method == 'CARD' else '🔀 Aralash',
                'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'details': items_str or 'Bar xaridi'
            })

        recent_sales.sort(key=lambda x: x['created_at'], reverse=True)
        recent_sales = recent_sales[:20]

        return Response({
            'period': period,
            'start_date': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'end_date': end_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'session_cash': session_cash,
            'session_card': session_card,
            'bar_cash': bar_cash,
            'bar_card': bar_card,
            'total_session': session_cash + session_card,
            'total_bar': total_bar,
            'bar_cogs': bar_cogs,
            'bar_margin': bar_margin,
            'bar_margin_percent': bar_margin_percent,
            'expense_cash': expense_cash,
            'expense_card': expense_card,
            'total_expenses': total_expenses,
            'cash_balance': cash_balance,
            'card_balance': card_balance,
            'total_balance': total_balance,
            'total_revenue': total_revenue,
            'expenses': expense_serializer.data,
            'recent_sales': recent_sales
        }, status=status.HTTP_200_OK)


class CustomerViewSet(viewsets.ModelViewSet):
    """Mijozlar/a'zolik: ism, telefon, balans (bonus/depozit hisobi).
    Sessiya/buyurtmalar ixtiyoriy ravishda mijozga bog'lanishi mumkin —
    to'lov (naqd/plastik) hisob-kitobiga ta'sir qilmaydi, faqat
    xarid tarixini ko'rish uchun ishlatiladi."""
    queryset = Customer.objects.all().order_by('full_name')
    serializer_class = CustomerSerializer

    def get_permissions(self):
        if self.action in ('kiosk_login', 'my_activity', 'kiosk_change_password', 'whoami'):
            return [HasClientApiKey()]
        return super().get_permissions()

    def get_throttles(self):
        if self.action == 'kiosk_login':
            self.throttle_scope = 'kiosk_login'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(phone__icontains=search))
        return qs

    @action(detail=False, methods=['post'])
    def kiosk_login(self, request):
        """Kiosk qulf ekranidan (client_locker.py): mijoz o'z telefon
        raqami va paroli bilan kiradi. Agar bu raqam uchun parol hali
        o'rnatilmagan bo'lsa (xodim faqat ism/telefonni kiritib
        qo'ygan), kiritilgan so'z avtomatik shu mijozning paroli
        sifatida saqlanadi (birinchi kirish = o'z-o'zini ro'yxatdan
        o'tkazish). PC holatiga (qulflanganligiga) hech qanday ta'sir
        qilmaydi — faqat mijozga o'z profilini ko'rsatish uchun."""
        phone_raw = str(request.data.get('phone', ''))
        password = str(request.data.get('password', ''))
        phone_core = _normalize_phone_core(phone_raw)

        if not phone_core or not password:
            return Response({'error': "Telefon raqam va parolni kiriting!"}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 4:
            return Response({'error': "Parol kamida 4 belgidan iborat bo'lishi kerak!"}, status=status.HTTP_400_BAD_REQUEST)

        customer = None
        for c in Customer.objects.all():
            if _normalize_phone_core(c.phone) == phone_core:
                customer = c
                break

        if not customer:
            return Response(
                {'error': "Bu raqam ro'yxatdan o'tmagan, avval administratorga murojaat qiling."},
                status=status.HTTP_404_NOT_FOUND
            )

        if not customer.password_hash:
            customer.password_hash = make_password(password)
            customer.save(update_fields=['password_hash'])
            AuditLog.objects.create(
                action='CUSTOMER_LOGIN',
                description=f"{customer.full_name} ({customer.phone}) birinchi marta kirdi (parol o'rnatildi)"
            )
            data = self.get_serializer(customer).data
            data['session_token'] = _create_kiosk_session_token(customer.id)
            return Response(data)

        if not check_password(password, customer.password_hash):
            return Response({'error': "Parol xato!"}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.objects.create(
            action='CUSTOMER_LOGIN',
            description=f"{customer.full_name} ({customer.phone}) tizimga kirdi"
        )
        data = self.get_serializer(customer).data
        data['session_token'] = _create_kiosk_session_token(customer.id)
        return Response(data)

    @action(detail=False, methods=['post'])
    def whoami(self, request):
        """Klient (client_locker.py) qayta ishga tushganda — masalan
        yangilanish/qulash/qayta yuklashdan keyin — "Kabinet" holatini
        tiklash uchun. session_token mahalliy faylda saqlangan bo'lsa
        ham, faqat shu mijoz HOZIR aynan shu PC'da BALANCE seansi ochib
        turgan bo'lsagina ma'lumot qaytariladi — aks holda eski/boshqa
        mijozning profili noto'g'ri PC'da yoki tugagan seans uchun
        qayta ko'rsatilib qolishi mumkin edi."""
        customer, error_response = _resolve_kiosk_session_customer(request)
        if error_response:
            return error_response
        pc_name = request.data.get('pc_name')
        has_active_balance_session = Session.objects.filter(
            computer__name=pc_name, customer=customer, is_active=True, payment_method='BALANCE'
        ).exists()
        if not has_active_balance_session:
            return Response({'error': "Bu PC'da faol seans topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        data = self.get_serializer(customer).data
        data['session_token'] = request.data.get('session_token')
        return Response(data)

    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """Xodim uchun: mijoz parolini unutgan bo'lsa, shu orqali
        tozalanadi — keyingi kirishda mijoz yana "birinchi marta"
        rejimida o'zi yangi parol o'rnatadi."""
        customer = self.get_object()
        customer.password_hash = None
        customer.save(update_fields=['password_hash'])
        _log_action(request, 'CUSTOMER_PASSWORD_RESET', f"{customer.full_name} ({customer.phone}) paroli tozalandi")
        return Response(self.get_serializer(customer).data)

    @action(detail=False, methods=['post'])
    def my_activity(self, request):
        """Kiosk'dan: login qilgan mijozning o'z tranzaksiyalari va
        seanslar tarixi — session_token orqali (URL'dagi pk emas,
        aks holda istalgan kiosk boshqa mijozning tarixini ko'ra
        olardi)."""
        customer, error_response = _resolve_kiosk_session_customer(request)
        if error_response:
            return error_response
        # balance_worker.py har 30 soniyada avtomatik yechgan mayda-
        # mayda tranzaksiyalarni bu yerda KO'RSATMAYMIZ (balans
        # hisob-kitobiga ta'sir qilmaydi, faqat ro'yxatni "to'ldirib"
        # yuborishining oldi olinadi) — buning o'rniga har bir tugagan
        # seans pastdagi `sessions`da BITTA qator (jami narxi bilan)
        # sifatida ko'rinadi. Qo'lda to'ldirish va xodim tomonidan
        # yechilgan summalar odatdagidek ko'rinaveradi.
        transactions = customer.transactions.exclude(type='SPEND', note__icontains='(avtomatik)')[:50]
        sessions = customer.sessions.exclude(is_active=True).order_by('-start_time')[:50]
        return Response({
            'transactions': CustomerTransactionSerializer(transactions, many=True).data,
            'sessions': SessionSerializer(sessions, many=True).data,
        })

    @action(detail=False, methods=['post'])
    def kiosk_change_password(self, request):
        """Kiosk'dan: login qilgan mijoz o'z parolini o'zgartiradi.
        session_token yetarli emas — joriy parolni ham bilishi shart
        (qo'shimcha himoya qatlami, masalan token qandaydir yo'l bilan
        "o'g'irlangan" taqdirda ham parolni o'zgartirib qo'ya olmasin)."""
        customer, error_response = _resolve_kiosk_session_customer(request)
        if error_response:
            return error_response

        old_password = str(request.data.get('old_password', ''))
        new_password = str(request.data.get('new_password', ''))

        if not check_password(old_password, customer.password_hash or ''):
            return Response({'error': "Joriy parol xato!"}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 4:
            return Response({'error': "Yangi parol kamida 4 belgidan iborat bo'lishi kerak!"}, status=status.HTTP_400_BAD_REQUEST)

        customer.password_hash = make_password(new_password)
        customer.save(update_fields=['password_hash'])
        AuditLog.objects.create(
            action='CUSTOMER_LOGIN',
            description=f"{customer.full_name} ({customer.phone}) parolini o'zi o'zgartirdi"
        )
        return Response({'success': True})

    @action(detail=True, methods=['post'])
    def top_up(self, request, pk=None):
        customer = self.get_object()
        try:
            amount = float(request.data.get('amount', 0))
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            return Response({'error': "Summani to'g'ri kiriting!"}, status=status.HTTP_400_BAD_REQUEST)

        note = request.data.get('note', '')
        # F() ifodasi orqali bitta atom SQL UPDATE — bir vaqtda boshqa
        # so'rov (masalan balance_worker.py yoki boshqa xodim) balansni
        # o'zgartirayotgan bo'lsa ham, hech qanday yangilanish yo'qolmaydi
        # (avval "customer.balance = X; customer.save()" o'qib-yozish
        # usuli edi — bu ikki bir vaqtdagi so'rovdan birini "yutib"
        # yuborishi mumkin edi).
        Customer.objects.filter(pk=customer.pk).update(balance=F('balance') + amount)
        customer.refresh_from_db()

        CustomerTransaction.objects.create(
            customer=customer, type='TOPUP', amount=amount, balance_after=customer.balance,
            note=note, created_by=request.user if request.user.is_authenticated else None
        )
        _log_action(
            request, 'CUSTOMER_TOPUP',
            f"{customer.full_name} ({customer.phone}) balansiga {amount:,.0f} UZS qo'shildi (yangi balans: {customer.balance:,.0f} UZS)"
        )

        # Balans to'ldirish bonusi — TOPUP_BONUS_TIERS'dagi eng yuqori
        # mos keladigan bosqich (masalan 100,000+ UZS -> +20,000 UZS,
        # 200,000+ UZS -> +50,000 UZS) qo'llaniladi. Asosiy to'ldirishdan
        # ALOHIDA tranzaksiya sifatida yoziladi — Kabinet/dashboard
        # tarixida bonus aniq ko'rinib tursin uchun.
        bonus = 0
        for threshold, bonus_amount in TOPUP_BONUS_TIERS:
            if amount >= threshold:
                bonus = bonus_amount
                break
        if bonus > 0:
            Customer.objects.filter(pk=customer.pk).update(balance=F('balance') + bonus)
            customer.refresh_from_db()
            CustomerTransaction.objects.create(
                customer=customer, type='TOPUP', amount=bonus, balance_after=customer.balance,
                note=f"Balans to'ldirish bonusi ({amount:,.0f} UZS to'ldirilgani uchun)",
                created_by=request.user if request.user.is_authenticated else None
            )
            _log_action(
                request, 'CUSTOMER_TOPUP',
                f"{customer.full_name} ({customer.phone}) balansiga bonus {bonus:,.0f} UZS qo'shildi "
                f"({amount:,.0f} UZS to'ldirilgani uchun, yangi balans: {customer.balance:,.0f} UZS)"
            )

        return Response(self.get_serializer(customer).data)

    @action(detail=True, methods=['post'])
    def spend(self, request, pk=None):
        customer = self.get_object()
        try:
            amount = float(request.data.get('amount', 0))
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            return Response({'error': "Summani to'g'ri kiriting!"}, status=status.HTTP_400_BAD_REQUEST)
        note = request.data.get('note', '')
        # Tekshirish + yechish BITTA atom SQL UPDATE'da (balance__gte
        # sharti bilan) — aks holda ikkita bir vaqtdagi so'rov ikkalasi
        # ham "balans yetarli" deb topib, uni manfiyga tushirib
        # qo'yishi mumkin edi.
        updated = Customer.objects.filter(pk=customer.pk, balance__gte=amount).update(balance=F('balance') - amount)
        if not updated:
            customer.refresh_from_db()
            return Response({'error': f"Balans yetarli emas (mavjud: {customer.balance:,.0f} UZS)"}, status=status.HTTP_400_BAD_REQUEST)
        customer.refresh_from_db()

        CustomerTransaction.objects.create(
            customer=customer, type='SPEND', amount=amount, balance_after=customer.balance,
            note=note, created_by=request.user if request.user.is_authenticated else None
        )
        _log_action(
            request, 'CUSTOMER_SPEND',
            f"{customer.full_name} ({customer.phone}) balansidan {amount:,.0f} UZS yechildi (qolgan balans: {customer.balance:,.0f} UZS)"
        )
        return Response(self.get_serializer(customer).data)

    @action(detail=True, methods=['get'])
    def transactions(self, request, pk=None):
        customer = self.get_object()
        txs = customer.transactions.all()[:100]
        return Response(CustomerTransactionSerializer(txs, many=True).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        customer = self.get_object()
        sessions = customer.sessions.order_by('-start_time')[:50]
        orders = customer.orders.exclude(status='CANCELLED').order_by('-created_at')[:50]
        return Response({
            'sessions': SessionSerializer(sessions, many=True).data,
            'orders': OrderSerializer(orders, many=True).data,
        })


class ClientLatestVersionView(APIView):
    """Kiosk klienti (client_locker.py) shu yerdan eng so'nggi versiya
    raqamini so'raydi. Kiosk API kaliti bilan himoyalangan (heartbeat
    kabi) — mijozlar/tashqi odamlar bu yerga kira olmaydi."""
    permission_classes = [HasClientApiKey]

    def get(self, request):
        build = ClientBuild.objects.filter(is_active=True).order_by('-released_at').first()
        if not build:
            return Response({'version': None})
        return Response({'version': build.version, 'notes': build.notes or ''})


class ClientDownloadView(APIView):
    """Eng so'nggi faol klient build'ining zip arxivini qaytaradi —
    client_locker.py shu yerdan yuklab olib, o'zini yangilaydi."""
    permission_classes = [HasClientApiKey]

    def get(self, request):
        build = ClientBuild.objects.filter(is_active=True).order_by('-released_at').first()
        if not build or not build.zip_file:
            return Response({'error': "Mavjud versiya topilmadi"}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(build.zip_file.open('rb'), content_type='application/zip', filename=f"client_{build.version}.zip")


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Xodimlar bajargan muhim amallarning tarixi (kim, qachon, nima
    qildi) — bitta umumiy admin hisobi ostida ham kunlik voqealarni
    keyinroq tekshirish uchun foydali."""
    queryset = AuditLog.objects.all().order_by('-created_at')
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        action_filter = self.request.query_params.get('action')
        if action_filter:
            qs = qs.filter(action=action_filter)
        return qs[:300]


