from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Standart DRF SessionAuthentication tizimga kirgan foydalanuvchi uchun
    har bir o'zgartiruvchi (POST/PUT/PATCH/DELETE) so'rovda CSRF token
    talab qiladi. Dashboard'ning ko'plab fetch() chaqiruvlari bu tokenni
    yubormaydi (faqat frontend'ni butunlay qayta yozish evaziga tuzatish
    mumkin bo'lardi), shuning uchun bu ichki, faqat LAN tarmog'ida
    ishlaydigan boshqaruv paneli uchun CSRF tekshiruvi o'chirilgan —
    lekin sessiya orqali autentifikatsiya (kim ekanini bilish) va shunga
    asoslangan ruxsat tekshiruvi (IsAuthenticated) to'liq ishlaydi.
    """
    def enforce_csrf(self, request):
        return
