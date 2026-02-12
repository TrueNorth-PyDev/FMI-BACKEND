"""
Quick script to check if a file exists and debug Railway media file issues.
Run this in Django shell on Railway to diagnose the problem.
"""

from pathlib import Path
from django.conf import settings
import os

print("="*60)
print("RAILWAY MEDIA FILES DIAGNOSTIC")
print("="*60)

# Check settings
print(f"\n1. SETTINGS CHECK:")
print(f"   MEDIA_ROOT: {settings.MEDIA_ROOT}")
print(f"   MEDIA_URL: {settings.MEDIA_URL}")
print(f"   DEBUG: {settings.DEBUG}")

# Check if media directory exists
media_root = Path(settings.MEDIA_ROOT)
print(f"\n2. MEDIA ROOT EXISTS: {media_root.exists()}")

if media_root.exists():
    # List all subdirectories
    print(f"\n3. SUBDIRECTORIES:")
    for subdir in media_root.iterdir():
        if subdir.is_dir():
            print(f"   - {subdir.name}/")
            # Count files in subdirectory
            file_count = sum(1 for _ in subdir.rglob('*') if _.is_file())
            print(f"     ({file_count} files)")
    
    # Check specific file
    test_file = media_root / "marketplace" / "documents" / "Ephraim_Efevwerhan_-_CV.pdf"
    print(f"\n4. SPECIFIC FILE CHECK:")
    print(f"   Path: {test_file}")
    print(f"   Exists: {test_file.exists()}")
    
    # List all files in marketplace/documents
    marketplace_docs = media_root / "marketplace" / "documents"
    if marketplace_docs.exists():
        print(f"\n5. FILES IN marketplace/documents/:")
        for file in marketplace_docs.iterdir():
            if file.is_file():
                size = file.stat().st_size / 1024  # KB
                print(f"   - {file.name} ({size:.2f} KB)")
    else:
        print(f"\n5. marketplace/documents/ DOES NOT EXIST")
else:
    print("\n❌ MEDIA_ROOT directory does not exist!")
    print("   This is expected on Railway after a fresh deployment.")
    print("   Files need to be re-uploaded.")

print("\n" + "="*60)
print("DIAGNOSIS:")
print("="*60)
if not media_root.exists():
    print("❌ No media directory - files were never uploaded or lost on redeploy")
else:
    print("✓ Media directory exists")
    if not (media_root / "marketplace" / "documents").exists():
        print("❌ Documents directory missing")
    else:
        print("✓ Documents directory exists")
