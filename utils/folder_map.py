"""
folder_map.py - Quick folder structure visualizer
Run from any directory to see its layout
"""
import os
from pathlib import Path
from collections import defaultdict

# Folders/files to ignore (common noise)
IGNORE = {
    'node_modules', '.git', '__pycache__', '.next', 
    'venv', 'env', '.venv', 'dist', 'build',
    '.pytest_cache', '.mypy_cache', 'coverage'
}

def get_folder_structure(root_path, max_depth=4, show_files=True):
    """
    Walk through directory and build a visual tree
    
    Args:
        root_path: Starting directory
        max_depth: How many levels deep to go
        show_files: Whether to show individual files or just folders
    """
    root = Path(root_path).resolve()
    
    print(f"\n📁 {root.name}/")
    print("=" * 60)
    
    def _walk(path, prefix="", depth=0):
        if depth >= max_depth:
            return
            
        try:
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        except PermissionError:
            return
            
        # Separate folders and files
        folders = [i for i in items if i.is_dir() and i.name not in IGNORE]
        files = [i for i in items if i.is_file()] if show_files else []
        
        # Draw folders first
        for i, folder in enumerate(folders):
            is_last_folder = (i == len(folders) - 1) and not files
            connector = "└── " if is_last_folder else "├── "
            print(f"{prefix}{connector}📁 {folder.name}/")
            
            extension = "    " if is_last_folder else "│   "
            _walk(folder, prefix + extension, depth + 1)
        
        # Then files
        for i, file in enumerate(files):
            is_last = i == len(files) - 1
            connector = "└── " if is_last else "├── "
            
            # File size
            size = file.stat().st_size
            size_str = _format_size(size)
            
            # File extension for quick scanning
            ext = file.suffix or "no ext"
            
            print(f"{prefix}{connector}📄 {file.name} ({size_str}, {ext})")
    
    _walk(root)
    
    # Summary stats
    print("\n" + "=" * 60)
    _print_summary(root)

def _format_size(bytes):
    """Human-readable file size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.1f}{unit}"
        bytes /= 1024
    return f"{bytes:.1f}TB"

def _print_summary(root):
    """Count files by type"""
    stats = defaultdict(int)
    total_size = 0
    
    for path in root.rglob("*"):
        if any(ignored in path.parts for ignored in IGNORE):
            continue
        if path.is_file():
            ext = path.suffix or "no_extension"
            stats[ext] += 1
            total_size += path.stat().st_size
    
    print(f"Total size: {_format_size(total_size)}")
    print(f"\nFile types found:")
    for ext, count in sorted(stats.items(), key=lambda x: -x[1])[:10]:
        print(f"  {ext}: {count} files")

if __name__ == "__main__":
    import sys
    
    # Run from current directory or specified path
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    
    print("\n🔍 Folder Structure Analyzer")
    print("Add more folders to IGNORE list if needed\n")
    
    get_folder_structure(
        path,
        max_depth=4,      # Adjust depth
        show_files=True   # Set False to only see folders
    )