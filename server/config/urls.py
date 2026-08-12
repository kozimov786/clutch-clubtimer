from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

# django.conf.urls.static.static() faqat DEBUG=True bo'lganda URL
# qo'shadi — bu loyihada alohida statik-fayl serveri (nginx va h.k.)
# yo'qligi sababli, static fayllar (dashboard.js, CSS) DEBUG holatidan
# qat'iy nazar doim xizmat qilinishi kerak, aks holda DEBUG=False'da
# butun boshqaruv paneli dizaynsiz qolib ketadi.
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.billing.urls')),
    re_path(
        r'^static/(?P<path>.*)$', serve,
        {'document_root': settings.BASE_DIR / 'apps' / 'billing' / 'static'}
    ),
]
