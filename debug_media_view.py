"""
Debug view to check media file serving on Railway.
Add this to marketplace/views.py temporarily to diagnose the issue.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from pathlib import Path
import os

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def debug_media_config(request):
    """Debug endpoint to check media configuration"""
    
    media_root = Path(settings.MEDIA_ROOT)
    
    # Collect all files in media directory
    files_found = []
    if media_root.exists():
        for file_path in media_root.rglob('*'):
            if file_path.is_file():
                rel_path = file_path.relative_to(media_root)
                files_found.append({
                    'path': str(rel_path),
                    'size': file_path.stat().st_size,
                    'url': f"{settings.MEDIA_URL}{rel_path}".replace('\\', '/')
                })
    
    return Response({
        'settings': {
            'MEDIA_ROOT': str(settings.MEDIA_ROOT),
            'MEDIA_URL': settings.MEDIA_URL,
            'DEBUG': settings.DEBUG,
            'BASE_DIR': str(settings.BASE_DIR),
        },
        'filesystem': {
            'media_root_exists': media_root.exists(),
            'media_root_is_dir': media_root.is_dir() if media_root.exists() else False,
            'media_root_writable': os.access(media_root, os.W_OK) if media_root.exists() else False,
        },
        'files_count': len(files_found),
        'files': files_found[:20],  # Limit to first 20 files
    })
