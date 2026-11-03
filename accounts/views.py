"""
Views for the accounts app.
Handles user registration, authentication, email verification, and password reset.
"""

from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.exceptions import InvalidToken
from .authentication import SESSION_CLAIM
from .models import UserActivity, UserSession
from .session_utils import create_session, parse_device_name
from .serializers import (
    UserRegistrationSerializer,
    EmailVerificationSerializer,
    ResendOTPSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    PasswordResetConfirmSerializer,
    UserSerializer,
    UserProfileSerializer
)
from .utils import get_client_ip, log_auth_event
import logging

logger = logging.getLogger('accounts')


def issue_tokens(user, request, ip_address):
    """
    Generate JWT tokens for a user and record the login as a UserSession keyed
    by the refresh token's JTI (so the session can later be revoked).
    """
    refresh = RefreshToken.for_user(user)
    try:
        session = create_session(user, request, refresh, ip_address)
        # Copied into every access token minted from this refresh token
        refresh[SESSION_CLAIM] = session.pk
        logger.info(f"Session created for {user.email} from {ip_address}")
    except Exception as e:
        # Don't fail login if session bookkeeping fails
        logger.error(f"Failed to create session for {user.email}: {str(e)}")
    update_last_login(None, user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


@method_decorator(never_cache, name='dispatch')
class UserRegistrationView(APIView):
    """
    API endpoint for user registration.
    Rate limited per client IP (the 'auth' throttle scope).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'
    serializer_class = UserRegistrationSerializer

    @extend_schema(
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiResponse(description="User registered successfully"),
            400: OpenApiResponse(description="Validation error"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            ip_address = get_client_ip(request)
            
            # Log registration event
            log_auth_event('registration', user.email, ip_address, success=True)
            
            return Response({
                'message': 'Registration successful. Please check your email for verification code.',
                'user': {
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
            }, status=status.HTTP_201_CREATED)
        
        # Log failed registration
        email = request.data.get('email', 'unknown')
        ip_address = get_client_ip(request)
        log_auth_event('registration', email, ip_address, success=False, 
                      details=str(serializer.errors))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(never_cache, name='dispatch')
class EmailVerificationView(APIView):
    """
    API endpoint for email verification.
    Rate limited per client IP (the 'auth' throttle scope).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'
    serializer_class = EmailVerificationSerializer

    @extend_schema(
        request=EmailVerificationSerializer,
        responses={
            200: OpenApiResponse(description="Email verified successfully"),
            400: OpenApiResponse(description="Invalid or expired OTP"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            ip_address = get_client_ip(request)
            
            tokens = issue_tokens(user, request, ip_address)
            
            # Log verification event
            log_auth_event('email_verification', user.email, ip_address, success=True)
            
            return Response({
                'message': 'Email verified successfully.',
                'user': UserSerializer(user).data,
                'tokens': tokens
            }, status=status.HTTP_200_OK)
        
        # Log failed verification
        email = request.data.get('email', 'unknown')
        ip_address = get_client_ip(request)
        log_auth_event('email_verification', email, ip_address, success=False,
                      details=str(serializer.errors))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(never_cache, name='dispatch')
class ResendOTPView(APIView):
    """
    API endpoint for resending OTP.
    Rate limited per client IP (the 'auth' throttle scope).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'
    serializer_class = ResendOTPSerializer

    @extend_schema(
        request=ResendOTPSerializer,
        responses={
            200: OpenApiResponse(description="OTP resent successfully"),
            400: OpenApiResponse(description="Invalid email"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            otp_type = serializer.validated_data['otp_type']
            log_auth_event(f'resend_otp_{otp_type}', serializer.validated_data['email'],
                           get_client_ip(request), success=user is not None)
            
            # Same response whether or not the account exists
            return Response({
                'message': 'If an account exists for this email, a new code has been sent.'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(never_cache, name='dispatch')
class LoginView(APIView):
    """
    API endpoint for user login.
    Rate limited per client IP (the 'auth' throttle scope).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful"),
            400: OpenApiResponse(description="Invalid credentials"),
            403: OpenApiResponse(description="Account locked or not verified"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.validated_data['user']
            ip_address = get_client_ip(request)
            
            # Update last login IP
            user.last_login_ip = ip_address
            user.save(update_fields=['last_login_ip'])
            
            tokens = issue_tokens(user, request, ip_address)
            
            UserActivity.log_activity(
                user=user,
                activity_type='LOGIN',
                description=f'Logged in from {parse_device_name(request.META.get("HTTP_USER_AGENT", "Unknown"))}',
                ip_address=ip_address
            )
            
            # Log successful login
            log_auth_event('login', user.email, ip_address, success=True)
            
            return Response({
                'message': 'Login successful.',
                'user': UserSerializer(user).data,
                'tokens': tokens
            }, status=status.HTTP_200_OK)
        
        # Log failed login
        email = request.data.get('email', 'unknown')
        ip_address = get_client_ip(request)
        log_auth_event('login', email, ip_address, success=False,
                      details=str(serializer.errors))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(never_cache, name='dispatch')
class PasswordResetRequestView(APIView):
    """
    API endpoint for requesting password reset.
    Rate limited per client IP (the 'auth' throttle scope).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={
            200: OpenApiResponse(description="Reset OTP sent"),
            404: OpenApiResponse(description="User not found"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save()
            log_auth_event('password_reset_request', serializer.validated_data['email'],
                           get_client_ip(request), success=True)
            
            return Response({
                'message': 'If this email exists, you will receive a password reset code.'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(never_cache, name='dispatch')
class PasswordResetVerifyView(APIView):
    """
    API endpoint for verifying password reset OTP.
    Rate limited per client IP (the 'auth' throttle scope).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'
    serializer_class = PasswordResetVerifySerializer

    @extend_schema(
        request=PasswordResetVerifySerializer,
        responses={
            200: OpenApiResponse(description="OTP verified"),
            400: OpenApiResponse(description="Invalid OTP"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        
        if serializer.is_valid():
            email = request.data.get('email')
            ip_address = get_client_ip(request)
            
            log_auth_event('password_reset_verify', email, ip_address, success=True)
            
            return Response({
                'message': 'OTP verified. You can now reset your password.'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(never_cache, name='dispatch')
class PasswordResetConfirmView(APIView):
    """
    API endpoint for confirming password reset.
    Rate limited per client IP (the 'auth' throttle scope).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successful"),
            400: OpenApiResponse(description="Invalid token or password"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            ip_address = get_client_ip(request)
            
            log_auth_event('password_reset_confirm', user.email, ip_address, success=True)
            
            return Response({
                'message': 'Password reset successful. You can now login with your new password.'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for retrieving and updating user profile.
    Requires authentication.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        logger.info(f"Profile updated for user: {request.user.email}")
        return response


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Token refresh that keeps UserSession in step with refresh-token rotation:
    the session's key moves from the old token's JTI to the new one, so a
    revoked session cannot be resurrected with a rotated token.
    """

    def validate(self, attrs):
        from django.utils import timezone

        old_token = self.token_class(attrs['refresh'])
        session_id = old_token.get(SESSION_CLAIM)
        if session_id is not None and not UserSession.objects.filter(pk=session_id).exists():
            raise InvalidToken({'detail': 'This session has been signed out.', 'code': 'session_revoked'})
        old_jti = str(old_token['jti'])
        data = super().validate(attrs)
        new_jti = str(self.token_class(data['refresh'])['jti']) if 'refresh' in data else old_jti
        UserSession.objects.filter(session_key=old_jti).update(
            session_key=new_jti, last_activity=timezone.now()
        )
        return data


@method_decorator(never_cache, name='dispatch')
class SessionTokenRefreshView(TokenRefreshView):
    """Refresh an access token (and rotate the refresh token)."""
    serializer_class = SessionTokenRefreshSerializer
