import os
import json

# Ensure FAL_KEY is present before importing modules that read it
os.environ['FAL_KEY'] = 'test_dummy_key'

# Import the target function
import importlib.machinery, importlib.util, sys

# Load main.py by path to avoid module resolution issues
MAIN_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'main.py'))
# Ensure project root is on sys.path so `services` package imports resolve
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

loader = importlib.machinery.SourceFileLoader('main', MAIN_PATH)
spec = importlib.util.spec_from_loader(loader.name, loader)
main = importlib.util.module_from_spec(spec)
sys.modules['main'] = main
loader.exec_module(main)

# Patch the call_img2img_editor imported into main to avoid external network
# This was imported as a name in main at import time, so patch main.call_img2img_editor

def fake_call_img2img_editor(editor_key, prompt, image_urls, aspect, project_id, state=None):
    print('[TEST] fake_call_img2img_editor called')
    print('  editor_key=', editor_key)
    print('  prompt=', prompt[:200])
    print('  image_urls=', image_urls)
    return 'https://example.com/fake_result.png'

main.call_img2img_editor = fake_call_img2img_editor

# Now call the API function directly
payload1 = {'edit_prompt': 'Make the hat bright red and remove logo'}
payload2 = {'edit_prompt': 'Slightly soften the shadow on the left cheek'}

try:
    print('\n[TEST] First rerender (should create/store canonical ref)')
    res1 = main.api_cast_rerender_single_ref('testproj', 'lead_1', 'a', payload1)
    print('Result 1:', res1)

    print('\n[TEST] Second rerender (should prefer stored canonical ref)')
    res2 = main.api_cast_rerender_single_ref('testproj', 'lead_1', 'a', payload2)
    print('Result 2:', res2)
except Exception as e:
    print('Exception:', e)
    raise
