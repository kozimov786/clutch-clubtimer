from rest_framework import serializers
from django.utils import timezone
from .models import (
    Computer, Tariff, Session, Category, Product, Order, OrderItem, Expense, Game, StockSupply,
    Customer, CustomerTransaction, ClientBuild, AuditLog
)

class TariffSerializer(serializers.ModelSerializer):
    effective_price_per_hour = serializers.SerializerMethodField()
    is_daytime_discount = serializers.SerializerMethodField()

    class Meta:
        model = Tariff
        fields = '__all__'

    def get_effective_price_per_hour(self, obj):
        return obj.get_effective_price_per_hour()

    def get_is_daytime_discount(self, obj):
        now = timezone.localtime()
        return 10 <= now.hour < 18

class ComputerSerializer(serializers.ModelSerializer):
    current_tariff_name = serializers.ReadOnlyField(source='current_tariff.name')
    calculated_time_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Computer
        fields = [
            'id', 'name', 'zone', 'hardware_spec', 'ip_address', 'mac_address', 'status',
            'is_open_time', 'time_remaining', 'calculated_time_remaining', 'current_tariff',
            'current_tariff_name', 'session_start_time', 'session_end_time',
            'last_heartbeat'
        ]

    def get_calculated_time_remaining(self, obj):
        return obj.calculate_time_remaining()

class SessionSerializer(serializers.ModelSerializer):
    computer_name = serializers.ReadOnlyField(source='computer.name')
    tariff_name = serializers.ReadOnlyField(source='tariff.name')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)

    class Meta:
        model = Session
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = Product
        fields = ['id', 'name', 'cost_price', 'price', 'stock', 'image', 'category', 'category_name', 'is_available', 'created_at']

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    product_image = serializers.ReadOnlyField(source='product.image')

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_image', 'quantity', 'unit_price']

class OrderSerializer(serializers.ModelSerializer):
    computer_name = serializers.ReadOnlyField(source='computer.name')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'computer', 'computer_name', 'customer', 'customer_name', 'total_price', 'payment_method', 'payment_method_display', 'status', 'created_at', 'updated_at', 'items']

class ExpenseSerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)

    class Meta:
        model = Expense
        fields = '__all__'

class GameSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Game
        fields = '__all__'

class StockSupplySerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)

    class Meta:
        model = StockSupply
        fields = '__all__'


class CustomerTransactionSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    created_by_username = serializers.ReadOnlyField(source='created_by.username')

    class Meta:
        model = CustomerTransaction
        fields = ['id', 'customer', 'type', 'type_display', 'amount', 'balance_after', 'note', 'created_by_username', 'created_at']


class CustomerSerializer(serializers.ModelSerializer):
    total_spent = serializers.SerializerMethodField()
    session_count = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ['id', 'full_name', 'phone', 'balance', 'bonus_points', 'notes', 'created_at', 'total_spent', 'session_count']

    def get_total_spent(self, obj):
        session_total = sum(float(s.total_price) for s in obj.sessions.all())
        order_total = sum(float(o.total_price) for o in obj.orders.exclude(status='CANCELLED'))
        return session_total + order_total

    def get_session_count(self, obj):
        return obj.sessions.count()


class ClientBuildSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientBuild
        fields = ['id', 'version', 'zip_file', 'notes', 'is_active', 'released_at']


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'username', 'action', 'action_display', 'description', 'created_at']

