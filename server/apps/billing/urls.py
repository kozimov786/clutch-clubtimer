from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DashboardView, LauncherView, ComputerViewSet, TariffViewSet, SessionViewSet,
    AdminLoginView, AdminLogoutView, CategoryViewSet, ProductViewSet, OrderViewSet, ExpenseViewSet, GameViewSet, GamePathOverrideViewSet, StockSupplyViewSet,
    CustomerViewSet, AuditLogViewSet, ClientLatestVersionView, ClientDownloadView
)

router = DefaultRouter()
router.register(r'computers', ComputerViewSet, basename='computer')
router.register(r'tariffs', TariffViewSet, basename='tariff')
router.register(r'sessions', SessionViewSet, basename='session')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'games', GameViewSet, basename='game')
router.register(r'game-path-overrides', GamePathOverrideViewSet, basename='game-path-override')
router.register(r'stock-supplies', StockSupplyViewSet, basename='stock-supply')
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('launcher/', LauncherView.as_view(), name='launcher'),
    path('api/login/', AdminLoginView.as_view(), name='admin_login'),
    path('api/logout/', AdminLogoutView.as_view(), name='admin_logout'),
    path('api/client/latest/', ClientLatestVersionView.as_view(), name='client_latest'),
    path('api/client/download/', ClientDownloadView.as_view(), name='client_download'),
    path('api/', include(router.urls)),
]


