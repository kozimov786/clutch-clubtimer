from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DashboardView, LauncherView, ComputerViewSet, TariffViewSet, SessionViewSet,
    AdminLoginView, AdminLogoutView, CategoryViewSet, ProductViewSet, OrderViewSet, ExpenseViewSet, GameViewSet, StockSupplyViewSet
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
router.register(r'stock-supplies', StockSupplyViewSet, basename='stock-supply')

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('launcher/', LauncherView.as_view(), name='launcher'),
    path('api/login/', AdminLoginView.as_view(), name='admin_login'),
    path('api/logout/', AdminLogoutView.as_view(), name='admin_logout'),
    path('api/', include(router.urls)),
]


