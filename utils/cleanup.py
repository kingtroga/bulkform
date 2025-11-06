import shutil
from pathlib import Path

def clear_folder(path: str):
    """Delete all files/subfolders in a directory and recreate it."""
    folder = Path(path)
    if folder.exists():
        for item in folder.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                print(f"⚠️ Error deleting {item}: {e}")
    folder.mkdir(parents=True, exist_ok=True)
    print(f"🧹 Cleared: {folder}")