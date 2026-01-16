"""
URL configuration for the accounts app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserRegistrationView,
    EmailVerificationView,
    ResendOTPView,
    LoginView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetConfirmView,
    UserProfileView,
)
from .account_views import AccountManagementViewSet
from .network_views import InvestorNetworkViewSet

app_name = 'accounts'

# Router for account management
router = DefaultRouter()
router.register(r'account', AccountManagementViewSet, basename='account-management')
router.register(r'network', InvestorNetworkViewSet, basename='investor-network')

urlpatterns = [
    # Authentication endpoints
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('verify-email/', EmailVerificationView.as_view(), name='verify-email'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('login/', LoginView.as_view(), name='login'),
    
    # JWT token endpoints
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Password reset endpoints
    path('password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/verify/', PasswordResetVerifyView.as_view(), name='password-reset-verify'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    
    # User profile endpoints
    path('me/', UserProfileView.as_view(), name='user-profile'),
    
    # Account management and investor network endpoints
    path('', include(router.urls)),
]

