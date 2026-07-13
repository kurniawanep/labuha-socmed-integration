import os
import time
import logging
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class MetaPublisher:
    def __init__(self):
        # Facebook configuration (Page Stories)
        self.fb_page_id = os.getenv("FB_PAGE_ID")
        self.fb_access_token = os.getenv("FB_ACCESS_TOKEN")
        
        # Instagram configuration (Instagram Stories)
        self.ig_user_id = os.getenv("IG_USER_ID")
        self.ig_access_token = os.getenv("IG_ACCESS_TOKEN") or os.getenv("FB_ACCESS_TOKEN")
        
        # Threads configuration (Threads Posts)
        self.threads_user_id = os.getenv("THREADS_USER_ID")
        self.threads_access_token = os.getenv("THREADS_ACCESS_TOKEN")

    def publish_to_all(self, text: str, media_url: str = None, media_type: str = None, local_media_path: str = None) -> dict:
        """
        Publishes text and media to Instagram Stories, Facebook Page Stories, and Threads.
        
        Args:
            text (str): Caption or post text content.
            media_url (str, optional): The public URL of the media (required for IG/FB Stories).
            media_type (str, optional): 'image' or 'video'.
            local_media_path (str, optional): Local file path (required for FB video uploads).
            
        Returns:
            dict: Status results for each platform.
        """
        results = {}
        
        # --- 1. INSTAGRAM STORY ---
        if media_url and media_type in ["image", "video"]:
            if self.ig_user_id and self.ig_access_token:
                try:
                    logger.info("Initiating Instagram Story publication...")
                    ig_post_id = self.post_instagram_story(media_url, media_type)
                    results["instagram"] = {"success": True, "id": ig_post_id}
                except Exception as e:
                    logger.error(f"Instagram Story publication failed: {e}")
                    results["instagram"] = {"success": False, "error": str(e)}
            else:
                logger.warning("Instagram credentials missing. Skipping Instagram Story.")
        else:
            logger.warning("Instagram Story requires image/video media. Skipping.")

        # --- 2. FACEBOOK PAGE STORY ---
        if media_type in ["image", "video"]:
            if self.fb_page_id and self.fb_access_token:
                try:
                    logger.info("Initiating Facebook Page Story publication...")
                    fb_post_id = self.post_facebook_page_story(media_url, media_type, local_media_path)
                    results["facebook"] = {"success": True, "id": fb_post_id}
                except Exception as e:
                    logger.error(f"Facebook Page Story publication failed: {e}")
                    results["facebook"] = {"success": False, "error": str(e)}
            else:
                logger.warning("Facebook Page credentials missing. Skipping Facebook Story.")
        else:
            logger.warning("Facebook Page Story requires image/video media. Skipping.")

        # --- 3. THREADS POST ---
        if self.threads_user_id and self.threads_access_token:
            try:
                logger.info("Initiating Threads publication...")
                threads_post_id = self.post_to_threads(text, media_url, media_type)
                results["threads"] = {"success": True, "id": threads_post_id}
            except Exception as e:
                logger.error(f"Threads publication failed: {e}")
                results["threads"] = {"success": False, "error": str(e)}
        else:
            logger.warning("Threads credentials missing. Skipping Threads.")

        return results

    def post_instagram_story(self, media_url: str, media_type: str) -> str:
        """
        Publishes a story image or video to Instagram.
        """
        # Step 1: Create Container
        url = f"https://graph.facebook.com/v21.0/{self.ig_user_id}/media"
        payload = {
            "media_type": "STORIES",
            "access_token": self.ig_access_token
        }
        if media_type == "image":
            payload["image_url"] = media_url
        else:
            payload["video_url"] = media_url
            
        r = requests.post(url, data=payload)
        res = r.json()
        if "id" not in res:
            raise Exception(f"Failed to create IG media container: {res}")
            
        container_id = res["id"]
        logger.info(f"Created IG Story container: {container_id}. Waiting for processing...")
        
        # Step 2: Poll Container Status
        self._wait_for_container(container_id, self.ig_access_token, is_threads=False)
        
        # Step 3: Publish Story
        publish_url = f"https://graph.facebook.com/v21.0/{self.ig_user_id}/media_publish"
        publish_payload = {
            "creation_id": container_id,
            "access_token": self.ig_access_token
        }
        r_pub = requests.post(publish_url, data=publish_payload)
        res_pub = r_pub.json()
        if "id" not in res_pub:
            raise Exception(f"Failed to publish IG Story container: {res_pub}")
            
        logger.info(f"Successfully published IG Story. Post ID: {res_pub['id']}")
        return res_pub["id"]

    def post_facebook_page_story(self, media_url: str, media_type: str, local_path: str = None) -> str:
        """
        Publishes a story image or video to a Facebook Page.
        """
        if media_type == "image":
            # For photos: Use /photos to upload unreleased photo, then publish to /photo_stories
            url = f"https://graph.facebook.com/v21.0/{self.fb_page_id}/photos"
            payload = {
                "url": media_url,
                "published": "false",
                "access_token": self.fb_access_token
            }
            r = requests.post(url, data=payload)
            res = r.json()
            if "id" not in res:
                raise Exception(f"Failed to upload FB Page temporary photo: {res}")
            photo_id = res["id"]
            
            story_url = f"https://graph.facebook.com/v21.0/{self.fb_page_id}/photo_stories"
            story_payload = {
                "photo_id": photo_id,
                "access_token": self.fb_access_token
            }
            r_story = requests.post(story_url, data=story_payload)
            res_story = r_story.json()
            if "id" not in res_story and "post_id" not in res_story and not res_story.get("success"):
                raise Exception(f"Failed to publish photo to Facebook Page Stories: {res_story}")
                
            story_id = res_story.get("post_id") or res_story.get("id") or "success"
            logger.info(f"Successfully published Facebook Page Photo Story. Story ID: {story_id}")
            return story_id
            
        elif media_type == "video":
            # For videos: Resumable upload workflow to /video_stories
            if not local_path or not os.path.exists(local_path):
                raise ValueError("Local video path is required for Facebook video story uploads.")
                
            # Step 1: Start Session
            url = f"https://graph.facebook.com/v21.0/{self.fb_page_id}/video_stories"
            payload = {
                "upload_phase": "start",
                "access_token": self.fb_access_token
            }
            r = requests.post(url, data=payload)
            res = r.json()
            if "video_id" not in res or "upload_url" not in res:
                raise Exception(f"Failed to initialize FB video story upload: {res}")
                
            video_id = res["video_id"]
            upload_url = res["upload_url"]
            
            # Step 2: Upload Video Bytes
            headers = {
                "Authorization": f"OAuth {self.fb_access_token}",
                "offset": "0",
                "Content-Type": "application/octet-stream"
            }
            logger.info(f"Uploading video bytes ({os.path.getsize(local_path)} bytes) to FB endpoint...")
            with open(local_path, "rb") as f:
                r_up = requests.post(upload_url, data=f, headers=headers)
                
            if r_up.status_code != 200:
                raise Exception(f"Failed to upload FB video bytes: {r_up.text}")
                
            # Step 3: Finish Session
            finish_payload = {
                "upload_phase": "finish",
                "video_id": video_id,
                "access_token": self.fb_access_token
            }
            r_fin = requests.post(url, data=finish_payload)
            res_fin = r_fin.json()
            if not res_fin.get("success"):
                raise Exception(f"Failed to finalize FB video story upload: {res_fin}")
                
            logger.info(f"Successfully published Facebook Page Video Story. Video ID: {video_id}")
            return video_id
        else:
            raise ValueError(f"Unsupported media type for Facebook Stories: {media_type}")

    def post_to_threads(self, text: str, media_url: str = None, media_type: str = None) -> str:
        """
        Publishes a post (text and optional image/video) to Threads.
        Note: Threads API enforces a 500-character limit on text.
        """
        THREADS_TEXT_LIMIT = 500

        # Truncate text if it exceeds Threads' character limit
        if text and len(text) > THREADS_TEXT_LIMIT:
            text = text[:THREADS_TEXT_LIMIT - 3] + "..."
            logger.warning(f"Text truncated to {THREADS_TEXT_LIMIT} characters for Threads API.")

        url = f"https://graph.threads.net/v1.0/{self.threads_user_id}/threads"
        payload = {
            "text": text,
            "access_token": self.threads_access_token
        }
        
        if media_url:
            if media_type == "image":
                payload["media_type"] = "IMAGE"
                payload["image_url"] = media_url
            elif media_type == "video":
                payload["media_type"] = "VIDEO"
                payload["video_url"] = media_url
        else:
            payload["media_type"] = "TEXT"
            
        # Step 1: Create Container
        r = requests.post(url, data=payload)
        res = r.json()
        if "id" not in res:
            raise Exception(f"Failed to create Threads container: {res}")
            
        container_id = res["id"]
        logger.info(f"Created Threads container: {container_id}. Waiting for processing...")
        
        # Step 2: Poll Container Status (only if it has media)
        if media_url:
            self._wait_for_container(container_id, self.threads_access_token, is_threads=True)
            
        # Step 3: Publish Container
        publish_url = f"https://graph.threads.net/v1.0/{self.threads_user_id}/threads_publish"
        publish_payload = {
            "creation_id": container_id,
            "access_token": self.threads_access_token
        }
        r_pub = requests.post(publish_url, data=publish_payload)
        res_pub = r_pub.json()
        if "id" not in res_pub:
            raise Exception(f"Failed to publish Threads container: {res_pub}")
            
        logger.info(f"Successfully published to Threads. Post ID: {res_pub['id']}")
        return res_pub["id"]

    def _wait_for_container(self, container_id: str, access_token: str, is_threads: bool = False, max_retries: int = 15, delay: int = 5):
        """
        Polls a Meta media container status until it transitions to 'FINISHED'.
        """
        if is_threads:
            url = f"https://graph.threads.net/v1.0/{container_id}"
        else:
            url = f"https://graph.facebook.com/v21.0/{container_id}"
            
        field_name = "status" if is_threads else "status_code"
        params = {
            "fields": field_name,
            "access_token": access_token
        }
        
        for i in range(max_retries):
            logger.info(f"Checking container {container_id} status (attempt {i+1}/{max_retries})...")
            try:
                r = requests.get(url, params=params)
                res = r.json()
                status = res.get(field_name)
                logger.info(f"Container {container_id} status: {status}")
                
                if status == "FINISHED":
                    return
                elif status in ["ERROR", "EXPIRED"]:
                    raise Exception(f"Container processing failed: {res}")
            except Exception as e:
                logger.warning(f"Error while checking container status: {e}")
                
            time.sleep(delay)
            
        raise Exception(f"Container {container_id} did not transition to FINISHED within the timeout period.")
