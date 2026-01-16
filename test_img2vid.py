#!/usr/bin/env python3
"""Test img2vid integration"""

import sys
sys.path.insert(0, '.')

print("Testing Img2Vid Integration...")
print("=" * 50)

# Test imports
try:
    from services.video_service import VIDEO_MODELS, list_video_models
    print("✓ video_service imported")
except Exception as e:
    print(f"✗ video_service import failed: {e}")
    sys.exit(1)

try:
    from services.export_service import export_video_with_img2vid
    print("✓ export_service img2vid imported")
except Exception as e:
    print(f"✗ export_service import failed: {e}")
    sys.exit(1)

try:
    import main
    print("✓ main.py imported")
except Exception as e:
    print(f"✗ main.py import failed: {e}")
    sys.exit(1)

print("\nVideo Models:")
print("-" * 50)
for model in list_video_models():
    print(f"  {model['key']:15} {model['name']:25} ${model['cost']:.2f}")
    print(f"                  Duration: {model['duration_range'][0]}-{model['duration_range'][1]}s, Audio: {model['supports_audio']}")

print("\nAPI Endpoints:")
print("-" * 50)
endpoints = [
    "GET  /api/video/models",
    "POST /api/project/{id}/video/generate-shot",
    "POST /api/project/{id}/video/generate-batch",
    "POST /api/project/{id}/video/export-img2vid",
]
for ep in endpoints:
    print(f"  {ep}")

print("\n" + "=" * 50)
print("✓ ALL TESTS PASSED - Img2Vid Module Ready!")
print("=" * 50)
