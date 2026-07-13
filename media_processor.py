import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)

def prepare_image_for_story(local_path: str) -> str:
    """
    Prepares an image for Meta Stories by:
    1. Converting it to JPEG format.
    2. Padding/letterboxing it to exactly 9:16 aspect ratio with a black background.
    
    Returns the absolute path to the processed JPEG image.
    """
    logger.info(f"Processing image for Story API compatibility: {local_path}")
    
    try:
        with Image.open(local_path) as img:
            original_w, original_h = img.size
            current_ratio = original_w / original_h
            target_ratio = 9 / 16  # 0.5625
            
            # 1. Determine target canvas dimensions
            if abs(current_ratio - target_ratio) < 1e-4:
                # Already 9:16
                new_w, new_h = original_w, original_h
                offset_x, offset_y = 0, 0
            elif current_ratio > target_ratio:
                # Wider than 9:16 (e.g. square, landscape). Height needs to increase.
                new_w = original_w
                new_h = int(original_w * 16 / 9)
                offset_x = 0
                offset_y = (new_h - original_h) // 2
            else:
                # Taller than 9:16 (rare). Width needs to increase.
                new_h = original_h
                new_w = int(original_h * 9 / 16)
                offset_x = (new_w - original_w) // 2
                offset_y = 0
                
            logger.info(f"Resizing/Padding from ({original_w}x{original_h}) to target 9:16 ({new_w}x{new_h})")
            
            # Create a black background RGB canvas
            canvas = Image.new("RGB", (new_w, new_h), (0, 0, 0))
            
            # Handle alpha transparency safely if pasting PNG/WebP onto JPEG background
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba_img = img.convert("RGBA")
                canvas.paste(rgba_img, (offset_x, offset_y), mask=rgba_img)
            else:
                canvas.paste(img.convert("RGB"), (offset_x, offset_y))
                
            # Create the path for the processed JPEG image
            base_dir = os.path.dirname(local_path)
            base_name = os.path.basename(local_path)
            name_part, _ = os.path.splitext(base_name)
            processed_filename = f"processed_{name_part}.jpg"
            processed_path = os.path.join(base_dir, processed_filename)
            
            # Save as JPEG
            canvas.save(processed_path, "JPEG", quality=90)
            logger.info(f"Processed image saved to: {processed_path}")
            return processed_path
            
    except Exception as e:
        logger.error(f"Error preparing image for story: {e}")
        # If it fails, fallback to returning the original path so the pipeline can still try to post it
        return local_path
