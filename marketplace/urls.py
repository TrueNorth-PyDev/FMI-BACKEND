"""
URL configuration for the marketplace app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MarketplaceOpportunityViewSet, WatchlistViewSet

app_name = 'marketplace'

router = DefaultRouter()
router.register(r'opportunities', MarketplaceOpportunityViewSet, basename='opportunity')
router.register(r'watchlist', WatchlistViewSet, basename='watchlist')

urlpatterns = [
    path('', include(router.urls)),
]
