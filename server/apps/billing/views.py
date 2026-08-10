from datetime import timedelta, datetime, time
import calendar
from django.utils import timezone
from django.shortcuts import render
from django.views import View
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Count, F
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Computer, Tariff, Session, Category, Product, Order, OrderItem, Expense
from .serializers import (
    ComputerSerializer, TariffSerializer, SessionSerializer,
    CategorySerializer, ProductSerializer, OrderSerializer, OrderItemSerializer, ExpenseSerializer
)
from .consumers import notify_pc_status_change, notify_bar_order_change

class AdminLoginView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            login(request, user)
            return Response({'success': True, 'username': user.username, 'is_admin': True})
        return Response({'success': False, 'error': 'Invalid admin credentials'}, status=status.HTTP_401_UNAUTHORIZED)

class AdminLogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({'success': True})



class DashboardView(View):
    def get(self, request):
        return render(request, 'billing/dashboard.html')

class TariffViewSet(viewsets.ModelViewSet):
    queryset = Tariff.objects.all().order_by('id')
    serializer_class = TariffSerializer

class SessionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Session.objects.all().order_by('-start_time')
    serializer_class = SessionSerializer

class ComputerViewSet(viewsets.ModelViewSet):
    queryset = Computer.objects.all().order_by('name')
    serializer_class = ComputerSerializer

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
                minutes = int(round(total_price / price_per_minute))
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
            price_per_minute = (active_session.tariff.price_per_hour / 60) if active_session.tariff else 250
            active_session.total_price += price_per_minute * minutes
            active_session.end_time = pc.session_end_time
            active_session.save()

        serializer = self.get_serializer(pc)
        notify_pc_status_change({
            'action': 'TIME_ADDED',
            'pc': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def stop_session(self, request, pk=None):
        pc = self.get_object()
        now = timezone.now()

        active_session = Session.objects.filter(computer=pc, is_active=True).first()
        if active_session:
            if pc.is_open_time and pc.session_start_time:
                elapsed_seconds = (now - pc.session_start_time).total_seconds()
                duration_minutes = int(round(elapsed_seconds / 60.0))
                tariff = pc.current_tariff or active_session.tariff or Tariff.objects.first()
                price_per_min = tariff.get_effective_price_per_hour() / 60.0 if tariff else 200.0
                total_price = price_per_min * duration_minutes
                active_session.duration_minutes = duration_minutes
                active_session.total_price = total_price
            active_session.end_time = now
            active_session.is_active = False
            active_session.save()

        pc.status = 'LOCKED'
        pc.is_open_time = False
        pc.time_remaining = 0
        pc.session_start_time = None
        pc.session_end_time = None
        pc.current_tariff = None
        pc.save()

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
        pc.session_start_time = None
        pc.session_end_time = None
        pc.save()

        Session.objects.filter(computer=pc, is_active=True).update(is_active=False, end_time=now)

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
            pc.session_start_time = None
            pc.session_end_time = None
            pc.save()

        Session.objects.filter(is_active=True).update(is_active=False, end_time=now)

        notify_pc_status_change({
            'action': 'EMERGENCY_LOCK_ALL'
        })
        return Response({'status': 'All PCs emergency locked'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def heartbeat(self, request):
        pc_name = request.data.get('pc_name')
        ip_addr = request.data.get('ip_address', '127.0.0.1')
        mac_addr = request.data.get('mac_address', '')

        if not pc_name:
            return Response({'error': 'pc_name is required'}, status=status.HTTP_400_BAD_REQUEST)

        pc, created = Computer.objects.get_or_create(
            name=pc_name,
            defaults={'ip_address': ip_addr, 'mac_address': mac_addr, 'status': 'LOCKED'}
        )

        pc.ip_address = ip_addr
        if mac_addr:
            pc.mac_address = mac_addr
        pc.calculate_time_remaining()
        pc.save()

        serializer = self.get_serializer(pc)
        return Response(serializer.data, status=status.HTTP_200_OK)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('id')
    serializer_class = CategorySerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('category', 'name')
    serializer_class = ProductSerializer

    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        product = self.get_object()
        quantity = int(request.data.get('quantity', 10))
        product.stock += quantity
        product.save()
        serializer = self.get_serializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer

    def create(self, request, *args, **kwargs):
        pc_name = request.data.get('pc_name')
        computer_id = request.data.get('computer')
        items_data = request.data.get('items', [])

        if not items_data:
            return Response({'error': 'Buyurtmada tovarlar yo\'q!'}, status=status.HTTP_400_BAD_REQUEST)

        computer = None
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

        payment_method = request.data.get('payment_method', 'CASH')

        order = Order.objects.create(
            computer=computer,
            total_price=total_price,
            payment_method=payment_method,
            status='PENDING'
        )

        for oi in order_items_to_create:
            OrderItem.objects.create(
                order=order,
                product=oi['product'],
                quantity=oi['quantity'],
                unit_price=oi['unit_price']
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
            for item in order.items.all():
                item.product.stock = max(0, item.product.stock - item.quantity)
                item.product.save()

        order.status = 'APPROVED'
        order.save()

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
            for item in order.items.all():
                item.product.stock = max(0, item.product.stock - item.quantity)
                item.product.save()

        order.status = 'DELIVERED'
        order.save()

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

        serializer = self.get_serializer(order)
        notify_bar_order_change({
            'action': 'ORDER_CANCELLED',
            'order': serializer.data
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def analytics(self, request):
        valid_orders = Order.objects.filter(status__in=['APPROVED', 'DELIVERED'])
        total_revenue = valid_orders.aggregate(Sum('total_price'))['total_price__sum'] or 0.00
        total_orders_count = Order.objects.count()
        pending_orders_count = Order.objects.filter(status='PENDING').count()

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
            'total_orders_count': total_orders_count,
            'pending_orders_count': pending_orders_count,
            'low_stock_count': low_stock_products.count(),
            'low_stock_products': low_stock_serializer.data,
            'inventory': inventory_serializer.data,
            'top_selling': list(top_selling_items)
        }, status=status.HTTP_200_OK)


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by('-created_at')
    serializer_class = ExpenseSerializer

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
        session_cash = float(sessions_qs.filter(payment_method='CASH').aggregate(Sum('total_price'))['total_price__sum'] or 0.0)
        session_card = float(sessions_qs.filter(payment_method='CARD').aggregate(Sum('total_price'))['total_price__sum'] or 0.0)

        orders_qs = Order.objects.filter(status__in=['APPROVED', 'DELIVERED'], created_at__range=(start_dt, end_dt))
        bar_cash = float(orders_qs.filter(payment_method='CASH').aggregate(Sum('total_price'))['total_price__sum'] or 0.0)
        bar_card = float(orders_qs.filter(payment_method='CARD').aggregate(Sum('total_price'))['total_price__sum'] or 0.0)

        expenses_qs = Expense.objects.filter(created_at__range=(start_dt, end_dt)).order_by('-created_at')
        expense_cash = float(expenses_qs.filter(payment_method='CASH').aggregate(Sum('amount'))['amount__sum'] or 0.0)
        expense_card = float(expenses_qs.filter(payment_method='CARD').aggregate(Sum('amount'))['amount__sum'] or 0.0)

        cash_balance = (session_cash + bar_cash) - expense_cash
        card_balance = (session_card + bar_card) - expense_card
        total_balance = cash_balance + card_balance
        total_expenses = expense_cash + expense_card
        total_revenue = session_cash + session_card + bar_cash + bar_card

        expense_serializer = ExpenseSerializer(expenses_qs, many=True)

        return Response({
            'period': period,
            'start_date': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'end_date': end_dt.strftime('%Y-%m-%d %H:%M:%S'),
            'session_cash': session_cash,
            'session_card': session_card,
            'bar_cash': bar_cash,
            'bar_card': bar_card,
            'total_session': session_cash + session_card,
            'total_bar': bar_cash + bar_card,
            'expense_cash': expense_cash,
            'expense_card': expense_card,
            'total_expenses': total_expenses,
            'cash_balance': cash_balance,
            'card_balance': card_balance,
            'total_balance': total_balance,
            'total_revenue': total_revenue,
            'expenses': expense_serializer.data
        }, status=status.HTTP_200_OK)


