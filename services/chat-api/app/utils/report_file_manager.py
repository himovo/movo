from __future__ import annotations

import os
import aiofiles
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4


class ReportFileManager:
    """Persist long report files to disk."""
    
    def __init__(self, base_dir: str = "static/reports/markdown"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_path_token(value: str) -> str:
        token = str(value or "").strip()
        if not token:
            return "anonymous"
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in token)
    
    def create_report_file(self, intent: str, task_id: Optional[str] = None) -> tuple[str, Path]:
        """
        Create a report file.

        Args:
            intent: Intent type (e.g., stock_analysis).
            task_id: Optional task ID.

        Returns:
            (file_id, file_path)
            file_id: Relative path, e.g. "2026-01-28/stock_analysis_20260128_233000_abc123.md"
            file_path: Absolute path.
        """
        task_id = task_id or uuid4().hex[:8]
        safe_task_id = self._safe_path_token(task_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        date_dir = self.base_dir / datetime.now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        task_dir = date_dir / safe_task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{intent}_{timestamp}_{safe_task_id}.md"
        file_path = task_dir / filename
        
        # Create an empty file
        file_path.touch()
        
        file_id = f"{datetime.now().strftime('%Y-%m-%d')}/{task_dir.name}/{filename}"
        return file_id, file_path
    
    async def append_content(self, file_path: Path, content: str):
        """
        Append content to a file.

        Args:
            file_path: File path.
            content: Content to append.
        """
        async with aiofiles.open(file_path, mode='a', encoding='utf-8') as f:
            await f.write(content)
    
    async def read_content(self, file_path: Path) -> str:
        """
        Read file content.

        Args:
            file_path: File path.

        Returns:
            File content.
        """
        async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
            return await f.read()
    
    async def overwrite_content(self, file_path: Path, content: str):
        """
        Overwrite file content.

        Args:
            file_path: File path.
            content: New content.
        """
        async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
            await f.write(content)
    
    def get_file_path(self, file_id: str) -> Path:
        """
        Get file path from file_id.

        Args:
            file_id: File ID (relative path).

        Returns:
            Absolute file path.
        """
        return self.base_dir / file_id
    
    def cleanup_old_files(self, max_age_days: int = 7):
        """
        Clean up old files.

        Args:
            max_age_days: Days to keep, default 7.
        """
        import time
        cutoff_time = time.time() - (max_age_days * 86400)
        
        cleaned_count = 0
        for date_dir in self.base_dir.iterdir():
            if not date_dir.is_dir():
                continue
            for file_path in date_dir.rglob("*.md"):
                if file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    cleaned_count += 1
        
        return cleaned_count

    def find_latest_report(self, user_id: str, task_id: Optional[str] = None) -> Optional[tuple[str, Path]]:
        """
        Find the latest report file for a user based on task_id prefix.
        """
        task_id = task_id or (user_id or "anonymous")
        latest_path: Optional[Path] = None
        latest_mtime = 0.0
        for date_dir in self.base_dir.iterdir():
            if not date_dir.is_dir():
                continue
            patterns = [f"*_{task_id}.md"]
            if task_id and len(task_id) > 8:
                patterns.append(f"*_{task_id[:8]}.md")
            for pattern in patterns:
                for file_path in date_dir.rglob(pattern):
                    mtime = file_path.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest_path = file_path
        if not latest_path:
            return None
        rel = latest_path.relative_to(self.base_dir)
        return str(rel), latest_path


# Global instance
report_file_manager = ReportFileManager()
