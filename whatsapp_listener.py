import sys
import os
import json
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from neonize.client import NewClient
from neonize.events import MessageEv, ConnectedEv, StreamReplacedEv, DisconnectedEv
from neonize.utils.jid import Jid2String
from media_processor import prepare_image_for_story
from supabase_uploader import SupabaseUploader
from meta_publisher import MetaPublisher
import db_monitor
from db_monitor import resolve_phone

# Load environment variables
load_dotenv()

# Configure logging — write to both console AND a persistent log file.
# Uses force=True so our FileHandler is always registered even if neonize
# already configured the root logger during import.
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s %(levelname)s] - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ],
    force=True,   # override any handlers already set by neonize
)

# Ensure downloads directory exists
DOWNLOADS_DIR = "downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Cache for channel metadata to avoid repetitive API requests
channel_cache = {}

def parse_message_content(msg_proto):
    """
    Parses the Message protobuf structure to extract text and identify media fields.
    """
    text = ""
    media_type = None
    media_data = None
    
    # ListFields returns only fields that are explicitly set in the message
    for field_desc, field_val in msg_proto.ListFields():
        name = field_desc.name
        
        if name == "conversation":
            text = field_val
        elif name == "extendedTextMessage":
            text = field_val.text
        elif name in ("imageMessage", "videoMessage", "documentMessage", "audioMessage", "stickerMessage"):
            # Set media type
            media_type = name.replace("Message", "")
            media_data = field_val
            # Extract caption if available
            if hasattr(field_val, "caption") and field_val.caption:
                text = field_val.caption
        elif name == "documentWithCaptionMessage":
            # Some documents are wrapped in documentWithCaptionMessage
            if hasattr(field_val, "message") and field_val.message.documentMessage:
                doc_msg = field_val.message.documentMessage
                media_type = "document"
                media_data = doc_msg
                if doc_msg.caption:
                    text = doc_msg.caption
                    
    return text, media_type, media_data

# Initialize NewClient with SQLite session database
client = NewClient("session.sqlite3")

@client.event(ConnectedEv)
def on_connected(_: NewClient, __: ConnectedEv):
    logging.info("Successfully connected to WhatsApp!")

@client.event(StreamReplacedEv)
def on_stream_replaced(_: NewClient, __: StreamReplacedEv):
    """
    Fired when another WhatsApp session replaces this one.
    Exit immediately so the bat restart loop spawns a clean new instance.
    """
    logging.warning("StreamReplaced: another session took over. Exiting to trigger auto-restart...")
    sys.exit(1)

@client.event(DisconnectedEv)
def on_disconnected(_: NewClient, __: DisconnectedEv):
    """
    Fired on clean disconnection. Exit so bat loop restarts the bot.
    """
    logging.warning("Disconnected from WhatsApp. Exiting to trigger auto-restart...")
    sys.exit(1)


@client.event(MessageEv)
def on_message(client: NewClient, message: MessageEv):
    # Retrieve the source chat JID
    chat_jid = message.Info.MessageSource.Chat
    chat_id = Jid2String(chat_jid)
    
    # Check message sender
    sender_jid = message.Info.MessageSource.Sender
    sender_id = Jid2String(sender_jid) if sender_jid else chat_id
    sender_name = message.Info.Pushname or "Unknown Sender"

    # Resolve the real WA phone number from either @lid or @s.whatsapp.net JID.
    # resolve_phone() queries whatsmeow_lid_map in session.sqlite3 for @lid JIDs.
    sender_id = resolve_phone(sender_id) or resolve_phone(chat_id)
    
    # Convert timestamp safely
    timestamp = message.Info.Timestamp
    try:
        if timestamp > 1e14:  # Microseconds
            ts_sec = timestamp / 1000000.0
        elif timestamp > 1e11:  # Milliseconds
            ts_sec = timestamp / 1000.0
        elif timestamp <= 0:
            ts_sec = datetime.now().timestamp()
        else:
            ts_sec = float(timestamp)
        dt_object = datetime.fromtimestamp(ts_sec)
        formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        dt_object = datetime.now()
        formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
    
    # Parse text content and media properties
    text_content, media_type, media_data = parse_message_content(message.Message)
    
    # Log everything to the terminal
    if chat_jid.Server == "newsletter":
        # Resolve channel name (caching results to be polite to WhatsApp servers)
        if chat_id not in channel_cache:
            try:
                meta = client.get_newsletter_info(chat_jid)
                channel_name = meta.ThreadMeta.Name
                channel_cache[chat_id] = channel_name
            except Exception as e:
                channel_name = "Unknown Channel"
        else:
            channel_name = channel_cache[chat_id]
            
        print("\n" + "="*50)
        print(f"📢 NEW CHANNEL MESSAGE RECEIVED")
        print(f"Channel Name: {channel_name}")
        print(f"Channel ID:   {chat_id}")
        print(f"Time:         {formatted_time}")
        print(f"Text Content: {text_content if text_content else '[No Text]'}")
    else:
        # Check if group or direct chat
        chat_type = "GROUP" if message.Info.MessageSource.IsGroup else "DIRECT CHAT"
        print("\n" + "-"*50)
        print(f"💬 NEW {chat_type} MESSAGE RECEIVED")
        print(f"From (Name):  {sender_name}")
        print(f"From (JID):   {sender_id}")
        if message.Info.MessageSource.IsGroup:
            print(f"Group ID:     {chat_id}")
        print(f"Time:         {formatted_time}")
        print(f"Text Content: {text_content if text_content else '[No Text]'}")
        
    media_path = None
    
    # Download media if present
    if media_type and media_data:
        print(f"Attachment:   ({media_type}) [Downloading...]")
        try:
            # download_any downloads content based on the parent Message object
            media_bytes = client.download_any(message.Message)
            if media_bytes:
                # Resolve file extension
                ext = {
                    "image": ".jpg",
                    "video": ".mp4",
                    "audio": ".mp3",
                    "sticker": ".webp"
                }.get(media_type, ".bin")
                
                # Check for document filenames
                if media_type == "document" and hasattr(media_data, "fileName") and media_data.fileName:
                    filename = media_data.fileName
                else:
                    prefix = "channel" if chat_jid.Server == "newsletter" else "chat"
                    filename = f"{prefix}_{message.Info.ID}{ext}"
                    
                media_path = os.path.join(DOWNLOADS_DIR, filename)
                with open(media_path, "wb") as f:
                    f.write(media_bytes)
                print(f"Saved media to: {media_path}")
            else:
                logging.warning("No media data returned by the downloader.")
        except Exception as e:
            logging.error(f"Failed to download media: {e}")
            
    if chat_jid.Server == "newsletter":
        print("="*50 + "\n")
        
        # Log channel messages to a persistent JSON store
        log_entry = {
            "channel_name": channel_name,
            "channel_id": chat_id,
            "message_id": message.Info.ID,
            "timestamp": timestamp,
            "formatted_time": formatted_time,
            "text": text_content,
            "media_type": media_type,
            "media_path": media_path
        }
        
        try:
            log_file = "channel_messages.json"
            messages = []
            if os.path.exists(log_file):
                with open(log_file, "r", encoding="utf-8") as rf:
                    messages = json.load(rf)
                    
            messages.append(log_entry)
            with open(log_file, "w", encoding="utf-8") as wf:
                json.dump(messages, wf, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to write to channel_messages.json: {e}")
    else:
        print("-"*50 + "\n")

    # --- ONE GATE DISSEMINATION PIPELINE ---
    
    # 0. Filter: Process ONLY personal (direct) chats
    is_group = message.Info.MessageSource.IsGroup
    is_newsletter = chat_jid.Server == "newsletter"
    if is_group or is_newsletter:
        logging.info("Skipping dissemination: Message is not from a personal/direct chat (group or channel ignored).")
        return
    # 1. Filter by Sender if ALLOWED_SENDERS is configured
    allowed_senders_str = os.getenv("ALLOWED_SENDERS", "")
    allowed_senders = [s.strip() for s in allowed_senders_str.split(",") if s.strip()]
    if allowed_senders:
        match_found = False
        for allowed in allowed_senders:
            if allowed in sender_id or allowed in chat_id:
                match_found = True
                break
        if not match_found:
            logging.info(f"Skipping dissemination: Message from {sender_id} in {chat_id} is not in ALLOWED_SENDERS.")
            return

    # 2. Filter by Prefix if COMMAND_PREFIX is configured
    command_prefix = os.getenv("COMMAND_PREFIX", "").strip()
    if command_prefix:
        if not text_content or not text_content.startswith(command_prefix):
            logging.info("Skipping dissemination: Message does not start with command prefix.")
            return
        else:
            # Strip command prefix from the caption/text
            text_content = text_content[len(command_prefix):].strip()

    # 3. Only disseminate if there is image/video media — text-only messages are ignored
    if not media_path or media_type not in ["image", "video"]:
        logging.info("Skipping: no image/video media found in message.")
        return

    media_url = None
    story_media_url = None  # Processed media specifically for IG/FB Stories

    try:
        # Initialize Supabase uploader
        uploader = SupabaseUploader()

        # Unique name prefix for remote files
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.basename(media_path)

        # Track local paths to delete after successful upload
        local_files_to_delete = []

        if media_type == "image":
            # Step 3a: Prepare image for Stories (convert to JPEG, pad to 9:16)
            print(f"Preparing image for Stories (auto-conversion & 9:16 padding)...")
            processed_path = prepare_image_for_story(media_path)

            # Step 3b: Upload processed image for IG/FB Stories
            story_filename = os.path.basename(processed_path)
            remote_story_path = f"stories/{timestamp_str}_{story_filename}"
            print(f"Uploading processed story image to Supabase...")
            story_media_url = uploader.upload_file(processed_path, remote_story_path)
            local_files_to_delete.append(processed_path)

            # Step 3c: Upload original image for Threads (if different)
            if processed_path != media_path:
                remote_orig_path = f"originals/{timestamp_str}_{filename}"
                print(f"Uploading original image to Supabase...")
                media_url = uploader.upload_file(media_path, remote_orig_path)
                local_files_to_delete.append(media_path)
            else:
                media_url = story_media_url
        else:
            # For video, upload directly
            remote_video_path = f"videos/{timestamp_str}_{filename}"
            print(f"Uploading video to Supabase...")
            media_url = uploader.upload_file(media_path, remote_video_path)
            story_media_url = media_url
            local_files_to_delete.append(media_path)

        # Delete local files after successful upload
        for local_file in local_files_to_delete:
            try:
                if os.path.exists(local_file):
                    os.remove(local_file)
                    logging.info(f"Deleted local file: {local_file}")
            except Exception as del_err:
                logging.warning(f"Could not delete local file {local_file}: {del_err}")

    except Exception as e:
        logging.error(f"Media upload pipeline failed: {e}")


    # 4. Publish to all Meta platforms
    if story_media_url or media_url:
        print("\n" + "*"*50)
        print("MEDIA MESSAGE → Posting to Instagram + Facebook + Threads")
        print("*"*50)
        try:
            publisher = MetaPublisher()
            results = publisher.publish_to_all(
                text=text_content,
                media_url=story_media_url or media_url,
                media_type=media_type,
                local_media_path=media_path
            )
            print(f"Dissemination Complete. Results: {results}")
            print("*"*50 + "\n")

            # ── Staff Monitoring Log ──────────────────────────────────
            try:
                published_platforms = [
                    p for p, v in (results or {}).items()
                    if v and str(v).lower() not in ("false", "none", "error", "")
                ]
                log_status = "success" if published_platforms else "failed"
                db_monitor.log_dissemination(
                    sender_wa=sender_id,
                    sender_name=sender_name,
                    media_type=media_type,
                    text_content=text_content,
                    platforms=published_platforms,
                    status=log_status,
                )
            except Exception as log_err:
                logging.warning(f"Monitoring log failed (non-critical): {log_err}")
            # ─────────────────────────────────────────────────────────

        except Exception as e:
            logging.error(f"Dissemination execution failed: {e}")

def auto_refresh_threads_token():
    """
    Checks the last refresh date of the Threads token in .env and refreshes it
    automatically if more than 30 days have passed.
    """
    token = os.getenv("THREADS_ACCESS_TOKEN")
    if not token or token.startswith("your-") or len(token) < 50:
        # Not a long-lived token yet
        return

    # Check the refresh date
    refresh_date_str = os.getenv("THREADS_TOKEN_REFRESH_DATE")
    today = datetime.now().date()
    
    should_refresh = False
    if not refresh_date_str:
        # No refresh date, let's set it to today and refresh it just in case
        should_refresh = True
    else:
        try:
            refresh_date = datetime.strptime(refresh_date_str, "%Y-%m-%d").date()
            days_passed = (today - refresh_date).days
            if days_passed >= 30:
                should_refresh = True
        except ValueError:
            should_refresh = True
            
    if should_refresh:
        logging.info("Checking Threads token expiration and refreshing automatically...")
        url = "https://graph.threads.net/refresh_access_token"
        params = {
            "grant_type": "th_refresh_token",
            "access_token": token
        }
        try:
            r = requests.get(url, params=params)
            res = r.json()
            if "access_token" in res:
                new_token = res["access_token"]
                
                # Update .env
                env_path = ".env"
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    token_updated = False
                    date_updated = False
                    
                    for i, line in enumerate(lines):
                        if line.startswith("THREADS_ACCESS_TOKEN="):
                            lines[i] = f"THREADS_ACCESS_TOKEN={new_token}\n"
                            token_updated = True
                        elif line.startswith("THREADS_TOKEN_REFRESH_DATE="):
                            lines[i] = f"THREADS_TOKEN_REFRESH_DATE={today.strftime('%Y-%m-%d')}\n"
                            date_updated = True
                            
                    if not token_updated:
                        lines.append(f"\nTHREADS_ACCESS_TOKEN={new_token}\n")
                    if not date_updated:
                        lines.append(f"THREADS_TOKEN_REFRESH_DATE={today.strftime('%Y-%m-%d')}\n")
                        
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                        
                    # Re-load env vars
                    os.environ["THREADS_ACCESS_TOKEN"] = new_token
                    os.environ["THREADS_TOKEN_REFRESH_DATE"] = today.strftime('%Y-%m-%d')
                    logging.info("✅ Threads token successfully refreshed and saved to .env automatically!")
            else:
                logging.warning(f"Failed to auto-refresh Threads token: {res}")
        except Exception as e:
            logging.error(f"Error while refreshing Threads token: {e}")

def run():
    # Auto-refresh Threads token if needed
    auto_refresh_threads_token()
    
    logging.info("Starting WhatsApp Channel Listener...")
    logging.info("If this is the first run, a QR code will be generated in your terminal shortly. Scan it using Link a Device in WhatsApp.")
    client.connect()

if __name__ == "__main__":
    run()
