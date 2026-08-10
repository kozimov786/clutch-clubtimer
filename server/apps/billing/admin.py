from django.contrib import admin
from .models import Computer, Session, Tariff

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
    list_display = ('id', 'computer', 'tariff', 'start_time', 'end_time', 'duration_minutes', 'total_price', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('computer__name',)
