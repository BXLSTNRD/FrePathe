"""
Fix video structure in migrated projects.
Moves video data from shot.video to shot.render.video for frontend compatibility.
"""
import json
import sys
from pathlib import Path

def fix_video_structure(project_path: Path) -> int:
    """Fix video structure in project JSON. Returns number of fixed shots."""
    with open(project_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    fixed = 0
    for shot in state.get('storyboard', {}).get('shots', []):
        # Check if video is in legacy location
        if shot.get('video') and shot['video'].get('video_url'):
            video_data = shot['video']
            
            # Ensure render exists
            if 'render' not in shot:
                shot['render'] = {}
            
            # Move video to render.video
            shot['render']['video'] = video_data
            
            # Remove legacy location
            del shot['video']
            
            fixed += 1
            print(f"Fixed {shot.get('shot_id')}: {video_data.get('video_url')}")
    
    # Save
    with open(project_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
    
    return fixed

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python fix_video_structure.py <project.json>")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    
    fixed = fix_video_structure(path)
    print(f"\nFixed {fixed} shots")
