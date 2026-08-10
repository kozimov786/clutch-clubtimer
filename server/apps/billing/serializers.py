from rest_framework import serializers
from django.utils import timezone
from .models import Computer, Tariff, Session, Category, Product, Order, OrderItem

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
        fields = ['id', 'name', 'price', 'stock', 'image', 'category', 'category_name', 'is_available', 'created_at']

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    product_image = serializers.ReadOnlyField(source='product.image')

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_image', 'quantity', 'unit_price']

class OrderSerializer(serializers.ModelSerializer):
    computer_name = serializers.ReadOnlyField(source='computer.name')
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'computer', 'computer_name', 'total_price', 'status', 'created_at', 'updated_at', 'items']

