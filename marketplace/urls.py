"""
URL configuration for the marketplace app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MarketplaceOpportunityViewSet, WatchlistViewSet, InvestorInterestViewSet

app_name = 'marketplace'

router = DefaultRouter()
router.register(r'opportunities', MarketplaceOpportunityViewSet, basename='opportunity')
router.register(r'watchlist', WatchlistViewSet, basename='watchlist')
router.register(r'investor-interest', InvestorInterestViewSet, basename='investor-interest')

urlpatterns = [
    path('', include(router.urls)),
]
