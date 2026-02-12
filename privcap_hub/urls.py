"""
URL configuration for privcap_hub project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from core.views import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Health check for Railway
    path('api/health/', health_check, name='health-check'),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # API Endpoints
    path('api/accounts/', include('accounts.urls')),
    path('api/', include('investments.urls')),
    path('api/marketplace/', include('marketplace.urls')),
]

# Serve media files (both development and production)
# NOTE: In production, ideally use cloud storage (S3, Cloudinary, etc.)
# This is a temporary solution for Railway's ephemeral filesystem
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Serve static files only in development (production uses WhiteNoise)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
