# Fré Pathé Services - Path Management
# v1.8.5: User-controlled project locations - NO MORE /data/projects chaos
#
# NEW STRUCTURE:
# {USER_LOCATION}/{ProjectTitle}/
# ├── project.json      ← SINGLE source of truth
# ├── renders/          ← All stills
# ├── video/            ← All video clips  
# ├── audio/            ← Source + processed audio
# ├── exports/          ← Final exports
# └── llm/              ← ALL LLM logs (no separate director/)

import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DATA, VERSION


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Sanitize a string for use as a filename.
    Duplicated here to avoid circular import with project_service.
    """
    safe = re.sub(r'[^\w\s\-_.]', '', name)
    safe = re.sub(r'[\s]+', '_', safe)
    safe = safe.strip('_')
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip('_')
    return safe or "unnamed"


class PathManager:
    """
    v1.8.5: Centralized path management with USER-CONTROLLED project locations.
    
    KEY CHANGES from v1.8.0:
    - Projects live where USER chooses (not forced into /data/projects)
    - Single project.json per project (no UUID duplicates)
    - LLM logs consolidated (no separate director/ folder)
    - workspace_root is for GLOBAL temp/cache only, not project storage
    
    Project structure:
    {project_location}/{ProjectTitle}/
    ├── project.json
    ├── renders/
    ├── video/
    ├── audio/
    ├── exports/
    └── llm/
    """
    
    def __init__(self, workspace_root: Optional[Path] = None):
        """
        Initialize PathManager.
        
        Args:
            workspace_root: Root for GLOBAL temp/cache/debug only.
                          Projects use their own project_location.
        """
        self.workspace_root = workspace_root if workspace_root else DATA
        self._ensure_structure()
        print(f"[INFO] PathManager v1.8.5 initialized. Global workspace: {self.workspace_root}")
    
    # ========= Directory Structure =========
    
    @property
    def projects_dir(self) -> Path:
        """Get projects directory: workspace_root/projects"""
        return self._ensure_dir(self.workspace_root / "projects")
    
    @property
    def temp_dir(self) -> Path:
        """Get global temp directory: workspace_root/temp"""
        return self._ensure_dir(self.workspace_root / "temp")
    
    @property
    def cache_dir(self) -> Path:
        """Get cache directory: workspace_root/cache"""
        return self._ensure_dir(self.workspace_root / "cache")
    
    @property
    def debug_dir(self) -> Path:
        """Get debug directory: workspace_root/debug"""
        return self._ensure_dir(self.workspace_root / "debug")
    
    # Legacy compatibility properties
    @property
    def uploads_dir(self) -> Path:
        """Legacy: Get temp directory (uploads are now in temp)"""
        return self.temp_dir
    
    @property
    def renders_dir(self) -> Path:
        """Legacy: Get projects directory (renders are now per-project)"""
        return self.projects_dir
    
    # ========= Project-Specific Paths =========
    
    def get_project_folder(self, state: Dict[str, Any]) -> Path:
        """
        v1.8.5: Get project root folder from project_location.
        
        NEW BEHAVIOR:
        - project_location is REQUIRED for new projects
        - project_location points DIRECTLY to the project folder
        - NO version suffix in folder name (user controls naming)
        - Fallback to legacy behavior only for old projects
        
        Args:
            state: Project state dictionary
        
        Returns:
            Path to project folder
        """
        project = state.get("project", {})
        
        # v1.8.5: project_location IS the project folder (direct path)
        project_location = project.get("project_location")
        if project_location:
            folder_path = Path(project_location)
            return self._ensure_dir(folder_path)
        
        # LEGACY FALLBACK: Old projects without project_location
        # This should only trigger for pre-1.8.5 projects
        title = project.get("title", "Untitled")
        created_version = project.get("created_version", VERSION)
        pid = project.get("id", "unknown")
        
        safe_title = sanitize_filename(title, 30)
        folder_name = f"{safe_title}_v{created_version}"
        
        folder_path = self.projects_dir / folder_name
        print(f"[WARN] Project {pid} has no project_location - using legacy path: {folder_path}")
        return self._ensure_dir(folder_path)
    
    def get_project_renders_dir(self, state: Dict[str, Any]) -> Path:
        """Get renders subdirectory for project."""
        return self._ensure_dir(self.get_project_folder(state) / "renders")
    
    def get_project_audio_dir(self, state: Dict[str, Any]) -> Path:
        """Get audio subdirectory for project."""
        return self._ensure_dir(self.get_project_folder(state) / "audio")
    
    def get_project_video_dir(self, state: Dict[str, Any]) -> Path:
        """Get video subdirectory for project."""
        return self._ensure_dir(self.get_project_folder(state) / "video")
    
    def get_project_exports_dir(self, state: Dict[str, Any]) -> Path:
        """v1.8.5: Get exports subdirectory for project (final renders)."""
        return self._ensure_dir(self.get_project_folder(state) / "exports")
    
    def get_project_temp_dir(self, state: Dict[str, Any]) -> Path:
        """Get temp subdirectory for project (auto-cleanup candidate)."""
        return self._ensure_dir(self.get_project_folder(state) / "temp")
    
    def get_project_llm_dir(self, state: Dict[str, Any]) -> Path:
        """Get LLM responses subdirectory for project (includes director logs)."""
        return self._ensure_dir(self.get_project_folder(state) / "llm")
    
    def get_project_director_dir(self, state: Dict[str, Any]) -> Path:
        """
        DEPRECATED v1.8.5: Director logs now go to llm/ folder.
        This method returns llm/ for backwards compatibility.
        """
        # Redirect to llm folder - no more separate director folder
        return self.get_project_llm_dir(state)
    
    # ========= URL Conversion =========
    
    def to_url(self, filesystem_path: Path) -> str:
        """
        Convert filesystem path to URL path.
        
        Example:
            C:\\Workspace\\projects\\Movie_v1.8.0\\renders\\cast_1.png
            -> /files/projects/Movie_v1.8.0/renders/cast_1.png
        
        Args:
            filesystem_path: Absolute filesystem path
        
        Returns:
            URL path string starting with /files/
        """
        try:
            rel_path = filesystem_path.relative_to(self.workspace_root)
            return f"/files/{rel_path.as_posix()}"
        except ValueError:
            # Not relative to workspace - might be external URL
            path_str = str(filesystem_path)
            if path_str.startswith("http://") or path_str.startswith("https://"):
                return path_str
            # Return as /files/ anyway
            return f"/files/{filesystem_path.name}"
    
    def from_url(self, url: str, state: Optional[Dict[str, Any]] = None) -> Path:
        """
        Convert URL path back to filesystem path.
        
        v1.8.5: Now accepts optional state to check project folder for migrated projects.
        
        Example:
            /files/projects/Movie_v1.8.0/renders/cast_1.png
            -> C:\\Workspace\\projects\\Movie_v1.8.0\\renders\\cast_1.png
        
        Args:
            url: URL path string
            state: Optional project state - if provided, also checks project folder
        
        Returns:
            Absolute filesystem path
        
        Raises:
            ValueError: If URL format is invalid
        """
        if url.startswith("/files/"):
            rel_path = url.replace("/files/", "", 1)
            workspace_path = self.workspace_root / rel_path
            
            # v1.8.5: If not found at workspace_root and state provided, check project folder
            if not workspace_path.exists() and state:
                project_path = self._find_in_project(rel_path, state)
                if project_path:
                    return project_path
            
            return workspace_path
        elif url.startswith("/renders/"):
            # Legacy support - /renders/filename.png maps to workspace_root/renders/filename.png
            rel_path = url.replace("/renders/", "", 1)
            # First try as direct path (for /renders/projects/... format)
            direct_path = self.workspace_root / rel_path
            if direct_path.exists():
                return direct_path
            # Then try in renders subdir (for /renders/filename.png format)
            renders_path = self.workspace_root / "renders" / rel_path
            if renders_path.exists():
                return renders_path
            
            # v1.8.5: Also check project folder for migrated projects
            if state:
                project_path = self._find_in_project(rel_path, state)
                if project_path:
                    return project_path
            
            # Return direct path as default (will 404 if not found)
            return direct_path
        elif url.startswith("http://") or url.startswith("https://"):
            # External URL - return as-is
            raise ValueError(f"Cannot convert external URL to filesystem path: {url}")
        else:
            raise ValueError(f"Invalid URL format: {url}")
    
    def _find_in_project(self, rel_path: str, state: Dict[str, Any]) -> Optional[Path]:
        """
        v1.8.5: Try to find a file in the project folder.
        Checks multiple locations: exact path, renders/, video/, audio/, root.
        
        Args:
            rel_path: Relative path or filename to find
            state: Project state with project_location
        
        Returns:
            Path if found, None otherwise
        """
        project_folder = self.get_project_folder(state)
        filename = Path(rel_path).name
        
        # Try exact relative path first
        exact_path = project_folder / rel_path
        if exact_path.exists():
            return exact_path
        
        # Try in common subdirectories
        for subdir in ["renders", "video", "audio", ""]:
            check_path = project_folder / subdir / filename if subdir else project_folder / filename
            if check_path.exists():
                return check_path
        
        return None
    
    # ========= Temp File Management =========
    
    def create_temp_file(self, prefix: str, suffix: str = "") -> Path:
        """
        Create a unique temp file path.
        
        Args:
            prefix: Prefix for temp filename
            suffix: File extension (e.g., ".png")
        
        Returns:
            Path to temp file (not created yet)
        """
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}{suffix}"
        return self.temp_dir / filename
    
    def create_project_temp_file(self, state: Dict[str, Any], prefix: str, suffix: str = "") -> Path:
        """
        Create a unique temp file path in project's temp folder.
        
        Args:
            state: Project state dictionary
            prefix: Prefix for temp filename
            suffix: File extension (e.g., ".png")
        
        Returns:
            Path to temp file (not created yet)
        """
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}{suffix}"
        return self.get_project_temp_dir(state) / filename
    
    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """
        Remove temp files older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours before cleanup
        
        Returns:
            Number of files removed
        """
        cutoff = time.time() - (max_age_hours * 3600)
        removed = 0
        
        for temp_file in self.temp_dir.glob("*"):
            if temp_file.is_file():
                try:
                    if temp_file.stat().st_mtime < cutoff:
                        temp_file.unlink(missing_ok=True)
                        removed += 1
                except Exception as e:
                    print(f"[WARNING] Failed to remove temp file {temp_file}: {e}")
        
        if removed > 0:
            print(f"[INFO] Cleaned up {removed} temp files")
        
        return removed
    
    def cleanup_project_temp(self, state: Dict[str, Any]) -> int:
        """
        Clean up temp folder for specific project.
        
        Args:
            state: Project state dictionary
        
        Returns:
            Number of files removed
        """
        temp_dir = self.get_project_temp_dir(state)
        removed = 0
        
        for temp_file in temp_dir.glob("*"):
            if temp_file.is_file():
                try:
                    temp_file.unlink(missing_ok=True)
                    removed += 1
                except Exception as e:
                    print(f"[WARNING] Failed to remove temp file {temp_file}: {e}")
        
        if removed > 0:
            print(f"[INFO] Cleaned up {removed} project temp files")
        
        return removed
    
    # ========= Helpers =========
    
    def _ensure_dir(self, path: Path) -> Path:
        """Create directory if it doesn't exist."""
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def _ensure_structure(self):
        """Ensure basic directory structure exists."""
        self.projects_dir
        self.temp_dir
        self.cache_dir
        self.debug_dir
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get information about current workspace configuration.
        
        Returns:
            Dictionary with workspace info
        """
        return {
            "workspace_root": str(self.workspace_root),
            "projects_dir": str(self.projects_dir),
            "temp_dir": str(self.temp_dir),
            "cache_dir": str(self.cache_dir),
            "is_default": self.workspace_root == DATA
        }
