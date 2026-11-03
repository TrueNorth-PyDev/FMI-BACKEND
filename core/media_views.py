"""
Custom view to serve media files in production on Railway.
This bypasses Django's static() limitation with WSGI servers.
"""

from django.http import FileResponse, Http404
from django.conf import settings
from pathlib import Path
import mimetypes

# Upload folders holding private documents. These are only downloadable through
# authenticated API endpoints, never through the public /media/ URL.
PRIVATE_MEDIA_PREFIXES = ('user_documents/', 'transfers/')


def serve_media(request, path):
    """
    Serve public media files (profile photos, marketplace documents) from MEDIA_ROOT.
    Works in both development and production.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    try:
        file_path = (media_root / path).resolve()
    except (ValueError, OSError):
        raise Http404("File not found")

    # Security check: the resolved file must live inside MEDIA_ROOT
    if not file_path.is_relative_to(media_root):
        raise Http404("Invalid file path")

    relative_path = file_path.relative_to(media_root).as_posix()
    if relative_path.startswith(PRIVATE_MEDIA_PREFIXES):
        raise Http404("File not found")

    if not file_path.is_file():
        raise Http404("File not found")

    content_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(open(file_path, 'rb'), content_type=content_type or 'application/octet-stream')
