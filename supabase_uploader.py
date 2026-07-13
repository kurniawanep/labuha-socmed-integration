import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class SupabaseUploader:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.bucket = os.getenv("SUPABASE_BUCKET", "disseminator-media")
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in the environment or .env file.")
        
        # Initialize the Supabase client
        self.client: Client = create_client(self.url, self.key)
        logger.info(f"Initialized Supabase client targeting bucket: '{self.bucket}'")

    def upload_file(self, local_path: str, remote_path: str) -> str:
        """
        Uploads a local file to the configured Supabase storage bucket.
        
        Args:
            local_path (str): Path to the local file.
            remote_path (str): Destination path within the bucket.
            
        Returns:
            str: Public URL of the uploaded file.
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found at: {local_path}")
            
        # Determine content type based on extension
        _, ext = os.path.splitext(local_path.lower())
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".webp": "image/webp"
        }
        content_type = content_types.get(ext, "application/octet-stream")
        
        logger.info(f"Uploading file '{local_path}' to remote path '{remote_path}' (Type: {content_type})...")
        
        try:
            with open(local_path, "rb") as f:
                # Perform the upload using supabase storage API
                response = self.client.storage.from_(self.bucket).upload(
                    path=remote_path,
                    file=f,
                    file_options={"content-type": content_type}
                )
                
            logger.info(f"Successfully uploaded: {remote_path}")
            
            # Retrieve the public URL
            public_url = self.client.storage.from_(self.bucket).get_public_url(remote_path)
            logger.info(f"Generated public URL: {public_url}")
            return public_url
            
        except Exception as e:
            logger.error(f"Supabase upload error: {e}")
            raise e

    def delete_file(self, remote_path: str) -> bool:
        """
        Delete a single file from Supabase storage.

        Args:
            remote_path: Path within the bucket (e.g. 'stories/20260713_img.jpg')

        Returns:
            True on success, False on error.
        """
        try:
            self.client.storage.from_(self.bucket).remove([remote_path])
            logger.info(f"Deleted from Supabase storage: {remote_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {remote_path}: {e}")
            return False

    def delete_old_files(self, folder: str, older_than_days: int = 7) -> dict:
        """
        Delete all files in a bucket folder that are older than N days.

        Args:
            folder:          Folder prefix in the bucket ('stories', 'originals', 'videos')
            older_than_days: Files older than this many days will be deleted

        Returns:
            dict with keys 'deleted' (list of paths) and 'failed' (list of paths)
        """
        from datetime import datetime, timezone, timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        deleted, failed = [], []

        try:
            items = self.client.storage.from_(self.bucket).list(folder)
        except Exception as e:
            logger.error(f"Failed to list '{folder}' in bucket: {e}")
            return {"deleted": [], "failed": []}

        for item in items:
            # Supabase returns created_at as ISO string
            created_str = item.get("created_at", "")
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except Exception:
                continue

            if created < cutoff:
                remote_path = f"{folder}/{item['name']}"
                if self.delete_file(remote_path):
                    deleted.append(remote_path)
                else:
                    failed.append(remote_path)

        logger.info(f"Cleanup '{folder}': deleted {len(deleted)}, failed {len(failed)}")
        return {"deleted": deleted, "failed": failed}

    def list_storage_usage(self) -> list[dict]:
        """
        List all files across all known folders with their sizes and ages.
        Returns a flat list of dicts: {folder, name, size_kb, age_days, remote_path}
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        results = []

        for folder in ("stories", "originals", "videos"):
            try:
                items = self.client.storage.from_(self.bucket).list(folder)
            except Exception:
                continue
            for item in items:
                created_str = item.get("created_at", "")
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    age_days = (now - created).days
                except Exception:
                    age_days = -1
                results.append({
                    "folder":      folder,
                    "name":        item.get("name", ""),
                    "size_kb":     round(item.get("metadata", {}).get("size", 0) / 1024, 1),
                    "age_days":    age_days,
                    "remote_path": f"{folder}/{item.get('name', '')}",
                })

        return results
