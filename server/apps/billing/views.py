from datetime import timedelta, datetime, time
import calendar
from django.utils import timezone
from django.shortcuts import render
from django.views import View
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Count, F, Case, When, Value, DecimalField
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Computer, Tariff, Session, Category, Product, Order, OrderItem, Expense, Game, StockSupply
from .serializers import (
    ComputerSerializer, TariffSerializer, SessionSerializer,
    CategorySerializer, ProductSerializer, OrderSerializer, OrderItemSerializer, ExpenseSerializer,
    GameSerializer, StockSupplySerializer
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

class GameViewSet(viewsets.ModelViewSet):
    queryset = Game.objects.filter(is_active=True).order_by('name')
    serializer_class = GameSerializer

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

        duration_minutes = 0
        time_price = 0.0

        if pc.is_open_time and start_time:
            elapsed_seconds = max(0, (now - start_time).total_seconds())
            duration_minutes = int(round(elapsed_seconds / 60.0))
            price_per_min = (tariff.get_effective_price_per_hour() / 60.0) if tariff else 200.0
            time_price = round(price_per_min * duration_minutes)
        elif active_session and active_session.duration_minutes > 0:
            duration_minutes = active_session.duration_minutes
            time_price = float(active_session.total_price)
        elif start_time:
            if pc.session_end_time:
                duration_minutes = int(round(max(0, (pc.session_end_time - start_time).total_seconds()) / 60.0))
            else:
                duration_minutes = int(round(max(0, (now - start_time).total_seconds()) / 60.0))
            price_per_min = (tariff.get_effective_price_per_hour() / 60.0) if tariff else 200.0
            time_price = round(price_per_min * duration_minutes)

        bar_items = []
        bar_total_price = 0.0

        if start_time:
            orders = Order.objects.filter(
                computer=pc,
                created_at__gte=start_time - timedelta(seconds=30)
            ).exclude(status='CANCELLED')
        else:
            orders = Order.objects.filter(
                computer=pc,
                status__in=['PENDING', 'APPROVED', 'DELIVERED']
            ).exclude(status='CANCELLED')

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

        duration_minutes = 0
        time_price = 0.0

        if pc.is_open_time and start_time:
            elapsed_seconds = max(0, (now - start_time).total_seconds())
            duration_minutes = int(round(elapsed_seconds / 60.0))
            price_per_min = (tariff.get_effective_price_per_hour() / 60.0) if tariff else 200.0
            time_price = round(price_per_min * duration_minutes)
        elif active_session and active_session.duration_minutes > 0:
            duration_minutes = active_session.duration_minutes
            time_price = float(active_session.total_price)
        elif start_time:
            if pc.session_end_time:
                duration_minutes = int(round(max(0, (pc.session_end_time - start_time).total_seconds()) / 60.0))
            else:
                duration_minutes = int(round(max(0, (now - start_time).total_seconds()) / 60.0))
            price_per_min = (tariff.get_effective_price_per_hour() / 60.0) if tariff else 200.0
            time_price = round(price_per_min * duration_minutes)

        if start_time:
            session_orders = Order.objects.filter(computer=pc, created_at__gte=start_time - timedelta(seconds=30)).exclude(status='CANCELLED')
        else:
            session_orders = Order.objects.filter(computer=pc).exclude(status='CANCELLED')

        bar_total_price = float(sum(o.total_price for o in session_orders))
        grand_total = float(time_price) + bar_total_price

        if payment_method == 'CASH':
            final_cash = grand_total
            final_card = 0.0
        elif payment_method == 'CARD':
            final_cash = 0.0
            final_card = grand_total
        elif payment_method == 'SPLIT':
            final_cash = req_cash
            final_card = req_card
            if abs((final_cash + final_card) - grand_total) > 0.01:
                final_card = max(0.0, grand_total - final_cash)
        else:
            final_cash = grand_total
            final_card = 0.0

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
                order.status = 'DELIVERED'
            order.save()

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

        if payment_method == 'CASH':
            cash_amt = float(total_price)
            card_amt = 0.0
        elif payment_method == 'CARD':
            cash_amt = 0.0
            card_amt = float(total_price)
        elif payment_method == 'SPLIT':
            cash_amt = float(request.data.get('cash_amount', 0.0))
            card_amt = float(request.data.get('card_amount', 0.0))
            if abs((cash_amt + card_amt) - float(total_price)) > 0.01:
                card_amt = max(0.0, float(total_price) - cash_amt)
        else:
            cash_amt = float(total_price)
            card_amt = 0.0

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


class StockSupplyViewSet(viewsets.ModelViewSet):
    queryset = StockSupply.objects.all().order_by('-created_at')
    serializer_class = StockSupplySerializer

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product_id')
        product_name = request.data.get('product_name', '').strip()
        quantity = int(request.data.get('quantity', 1))
        cost_price = float(request.data.get('cost_price', 0.0))
        selling_price = float(request.data.get('selling_price', 0.0))
        payment_method = request.data.get('payment_method', 'CASH')
        supplier_note = request.data.get('supplier_note', '').strip()

        total_cost = float(quantity * cost_price)

        product = None
        if product_id:
            product = Product.objects.filter(id=product_id).first()
        if not product and product_name:
            product = Product.objects.filter(name__iexact=product_name).first()

        if not product:
            if not product_name:
                return Response({'error': 'Iltimos, mahsulotni tanlang yoki yangi mahsulot nomini kiriting!'}, status=status.HTTP_400_BAD_REQUEST)
            
            default_category = Category.objects.first()
            product = Product.objects.create(
                name=product_name,
                cost_price=cost_price,
                price=selling_price,
                stock=0,
                category=default_category,
                is_available=True
            )

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

        serializer = self.get_serializer(supply)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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


