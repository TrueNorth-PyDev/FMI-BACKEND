"""
Custom view to serve media files in production on Railway.
This bypasses Django's static() limitation with WSGI servers.
"""

from django.http import FileResponse, Http404
from django.conf import settings
from pathlib import Path
import mimetypes

def serve_media(request, path):
    """
    Serve media files from MEDIA_ROOT.
    Works in both development and production.
    """
    # Construct the full file path
    file_path = Path(settings.MEDIA_ROOT) / path
    
    # Security check: ensure the file is within MEDIA_ROOT
    try:
        file_path = file_path.resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if not str(file_path).startswith(str(media_root)):
            raise Http404("Invalid file path")
    except (ValueError, OSError):
        raise Http404("File not found")
    
    # Check if file exists and is a file (not directory)
    if not file_path.exists() or not file_path.is_file():
        raise Http404("File not found")
    
    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    
    # Serve the file
    response = FileResponse(
        open(file_path, 'rb'),
        content_type=content_type or 'application/octet-stream'
    )
    
    return response
