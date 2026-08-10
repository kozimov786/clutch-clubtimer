from django.contrib import admin
from .models import Computer, Session, Tariff, Category, Product, Order, OrderItem, Expense, Game, StockSupply

@admin.register(StockSupply)
class StockSupplyAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_name', 'quantity', 'cost_price', 'selling_price', 'total_cost', 'payment_method', 'created_at')
    list_filter = ('payment_method',)
    search_fields = ('product_name', 'supplier_note')

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'executable_path', 'working_directory', 'is_active', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'executable_path', 'working_directory')


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price_per_hour', 'created_at')
    search_fields = ('name',)

@admin.register(Computer)
class ComputerAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'ip_address', 'status', 'time_remaining', 'current_tariff', 'last_heartbeat')
    list_filter = ('status',)
    search_fields = ('name', 'ip_address')

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'computer', 'tariff', 'payment_method', 'start_time', 'end_time', 'duration_minutes', 'total_price', 'is_active')
    list_filter = ('is_active', 'payment_method')
    search_fields = ('computer__name',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'icon')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'stock', 'category', 'is_available', 'created_at')
    list_filter = ('category', 'is_available')
    search_fields = ('name',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'computer', 'total_price', 'payment_method', 'status', 'created_at')
    list_filter = ('status', 'payment_method')
    search_fields = ('computer__name',)

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('id', 'amount', 'payment_method', 'category', 'recipient_name', 'created_at')
    list_filter = ('payment_method', 'category')
    search_fields = ('category', 'recipient_name', 'description')

