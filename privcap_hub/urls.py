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

# Serve media files using custom view (works in production with WSGI)
from django.urls import re_path
from core.media_views import serve_media

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve_media, name='media'),
]

# Serve static files only in development (production uses WhiteNoise)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
