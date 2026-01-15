# Fré Pathé Services - Settings Management
# v1.8.0: User-configurable workspace location

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .config import BASE, VERSION

# ========= Settings File =========
SETTINGS_FILE = BASE / "settings.json"


def load_settings() -> Dict[str, Any]:
    """
    Load user settings from disk.
    Returns default settings if file doesn't exist.
    """
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                print(f"[INFO] Loaded settings from {SETTINGS_FILE}")
                return settings
        except Exception as e:
            print(f"[WARNING] Failed to load settings: {e}, using defaults")
            return get_default_settings()
    return get_default_settings()


def save_settings(settings: Dict[str, Any]) -> bool:
    """
    Save user settings to disk.
    
    Args:
        settings: Dictionary with settings to save
    
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        print(f"[INFO] Saved settings to {SETTINGS_FILE}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save settings: {e}")
        return False


def get_default_settings() -> Dict[str, Any]:
    """
    Get default settings.
    
    Returns:
        Dictionary with default settings
    """
    return {
        "workspace_root": None,  # None = use DATA folder (backwards compatible)
        "auto_cleanup_temp": True,
        "temp_retention_hours": 24,
        "version": VERSION
    }


def get_workspace_root() -> Optional[Path]:
    """
    Get the configured workspace root path.
    
    Returns:
        Path object if configured, None if using default DATA folder
    """
    settings = load_settings()
    workspace_root = settings.get("workspace_root")
    
    if workspace_root:
        path = Path(workspace_root)
        if path.exists() and path.is_dir():
            return path
        else:
            print(f"[WARNING] Configured workspace root doesn't exist: {workspace_root}")
            return None
    
    return None


def update_workspace_root(new_path: str) -> bool:
    """
    Update the workspace root setting.
    
    Args:
        new_path: New workspace root path as string
    
    Returns:
        True if successful, False otherwise
    """
    path = Path(new_path)
    
    # Validate path
    if not path.exists():
        print(f"[ERROR] Path doesn't exist: {new_path}")
        return False
    
    if not path.is_dir():
        print(f"[ERROR] Path is not a directory: {new_path}")
        return False
    
    # Update settings
    settings = load_settings()
    settings["workspace_root"] = str(path)
    
    return save_settings(settings)


def validate_workspace_path(path: str) -> Dict[str, Any]:
    """
    Validate a workspace path without saving it.
    
    Args:
        path: Path to validate
    
    Returns:
        Dictionary with validation result:
        - valid: bool
        - error: str (if invalid)
        - writable: bool
    """
    try:
        p = Path(path)
        
        if not p.exists():
            return {
                "valid": False,
                "error": "Path doesn't exist",
                "writable": False
            }
        
        if not p.is_dir():
            return {
                "valid": False,
                "error": "Path is not a directory",
                "writable": False
            }
        
        # Test if writable
        test_file = p / ".frepathe_test"
        try:
            test_file.touch()
            test_file.unlink()
            writable = True
        except:
            writable = False
        
        return {
            "valid": True,
            "error": None,
            "writable": writable
        }
    
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "writable": False
        }
