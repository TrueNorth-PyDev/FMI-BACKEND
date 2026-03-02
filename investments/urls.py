"""
URL configuration for the investments app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InvestmentViewSet,
    CapitalActivityViewSet,
    PortfolioAnalyticsViewSet,
    OwnershipTransferViewSet,
    SecondaryMarketplaceViewSet,
    SecondaryMarketInterestViewSet,
)

app_name = 'investments'

router = DefaultRouter()
router.register(r'investments', InvestmentViewSet, basename='investment')
router.register(r'capital-activities', CapitalActivityViewSet, basename='capital-activity')
router.register(r'portfolio', PortfolioAnalyticsViewSet, basename='portfolio')
router.register(r'transfers', OwnershipTransferViewSet, basename='transfer')
router.register(r'secondary-market', SecondaryMarketplaceViewSet, basename='secondary-market')
router.register(r'secondary-market-interests', SecondaryMarketInterestViewSet, basename='secondary-market-interest')

urlpatterns = [
    path('', include(router.urls)),
]
