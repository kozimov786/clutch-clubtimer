from rest_framework.permissions import BasePermission
from django.conf import settings


def _request_api_key(request):
    return request.headers.get('X-API-Key') or request.headers.get('X-Api-Key')


class HasClientApiKey(BasePermission):
    """client_locker.py kiosk ilovasi uchun: foydalanuvchi hisobi bo'lmagan
    stansiya kompyuterlari X-API-Key header orqali autentifikatsiya qiladi."""

    def has_permission(self, request, view):
        api_key = _request_api_key(request)
        return bool(api_key) and api_key == settings.CLIENT_API_KEY


class IsStaffOrHasApiKey(BasePermission):
    """Admin panelidan tizimga kirgan xodim, YOKI to'g'ri API kalitini
    yuborayotgan kiosk klienti — ikkalasiga ham ruxsat beradi. Bar
    menyusi/o'yinlar ro'yxati va buyurtma berish kabi ikkala tomon ham
    foydalanadigan endpointlar uchun ishlatiladi."""

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and user.is_staff:
            return True
        return HasClientApiKey().has_permission(request, view)
