"""
PDF Processing Service with Supabase Storage
Core logic for PDF manipulation
"""
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
import img2pdf
import os
from pathlib import Path
import shutil
from typing import List, Dict, Optional
from services.supabase_client import get_supabase


def scan_available_fonts():
    """
    Auto-scan fonts directory and return available fonts
    Looks for .ttf files in fonts/ directory
    """
    fonts = {}
    fonts_dir = Path("fonts")
    
    if not fonts_dir.exists():
        fonts_dir.mkdir(exist_ok=True)
        print("⚠️  Created fonts/ directory. Add .ttf files here.")
        return fonts
    
    for font_file in fonts_dir.glob("*.ttf"):
        font_name = font_file.stem  # Filename without extension
        fonts[font_name] = str(font_file)
    
    return fonts


# Configuration
GRID_SIZE = 150
DPI = 300
TEMP_FOLDER = "temp_pdf_uploads"
GRIDDED_FOLDER = "gridded_pages"
OUTPUT_FOLDER = "filled_pages"
STORAGE_BUCKET = "pdfs"  # Supabase bucket name
AVAILABLE_FONTS = scan_available_fonts()

if not AVAILABLE_FONTS:
    print("⚠️  No fonts found in fonts/ directory!")
    print("📁 Add .ttf files to fonts/ folder")
else:
    print(f"✅ Loaded {len(AVAILABLE_FONTS)} fonts: {', '.join(AVAILABLE_FONTS.keys())}")


class PDFProcessor:
    """Handles all PDF processing operations"""
    
    def __init__(self):
        self.GRID_SIZE = GRID_SIZE
        self.DPI = DPI
        self.TEMP_FOLDER = TEMP_FOLDER
        self.GRIDDED_FOLDER = GRIDDED_FOLDER
        self.OUTPUT_FOLDER = OUTPUT_FOLDER
        self.STORAGE_BUCKET = STORAGE_BUCKET
        self.supabase = get_supabase()
        
        self.setup_folders()
    
    def setup_folders(self):
        """Create necessary folders"""
        for folder in [self.TEMP_FOLDER, self.GRIDDED_FOLDER, self.OUTPUT_FOLDER]:
            os.makedirs(folder, exist_ok=True)
    
    def cleanup_folders(self, session_id: str = None):
        """Delete temporary folders for a session"""
        if session_id:
            # Clean specific session
            session_temp = f"{self.TEMP_FOLDER}/{session_id}"
            session_output = f"{self.OUTPUT_FOLDER}/{session_id}"
            for folder in [session_temp, session_output]:
                if os.path.exists(folder):
                    shutil.rmtree(folder)
        else:
            # Clean all (use carefully!)
            for folder in [self.TEMP_FOLDER, self.GRIDDED_FOLDER]:
                if os.path.exists(folder):
                    shutil.rmtree(folder)
    
    def pdf_to_images(
        self, 
        pdf_path: str, 
        session_id: str, 
        page_numbers: Optional[List[int]] = None
    ) -> int:
        """
        Convert PDF pages to images.
        
        Args:
            pdf_path: Path to PDF file.
            session_id: Unique session identifier (used for output folder naming).
            page_numbers: Optional list of pages to convert (1-indexed). Converts all if None.
            
        Returns:
            Number of pages converted.
        """
        
        # Determine conversion parameters
        first_page = page_numbers[0] if page_numbers else 1
        last_page = page_numbers[-1] if page_numbers else None
        
        print(f"Converting PDF to images (session: {session_id}, pages: {page_numbers if page_numbers else 'ALL'})...")
        
        try:
            # Use pdf2image's first_page and last_page parameters for efficiency
            images = convert_from_path(
                pdf_path, 
                dpi=self.DPI,
                first_page=first_page,
                last_page=last_page
            )
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF to image: {e}")
        
        session_folder = f"{self.TEMP_FOLDER}/{session_id}"
        os.makedirs(session_folder, exist_ok=True)
        
        converted_count = 0
        
        # If specific page numbers were requested, we need to map the list index back to the page number
        if page_numbers:
            page_map = page_numbers
        else:
            page_map = list(range(1, len(images) + 1))
            
        for idx, img in enumerate(images):
            page_num = page_map[idx]
            img.save(f"{session_folder}/page_{page_num}.png")
            converted_count += 1
        
        print(f"Converted {converted_count} page(s)")
        return converted_count
    
    def get_page_dimensions(self, session_id: str, page_num: int) -> Dict:
        """Get dimensions for a specific page"""
        image_path = f"{self.TEMP_FOLDER}/{session_id}/page_{page_num}.png"
        img = Image.open(image_path)
        width, height = img.size
        
        cell_width = width / self.GRID_SIZE
        cell_height = height / self.GRID_SIZE
        
        return {
            "page_number": page_num,
            "width": width,
            "height": height,
            "grid_size": self.GRID_SIZE,
            "cell_width": cell_width,
            "cell_height": cell_height
        }
    
    def get_all_page_dimensions(self, session_id: str, num_pages: int) -> List[Dict]:
        """Get dimensions for all pages"""
        return [
            self.get_page_dimensions(session_id, page_num)
            for page_num in range(1, num_pages + 1)
        ]
    
    def write_text_on_page(
        self, 
        session_id: str, 
        page_num: int, 
        text_data: List[Dict]
    ):
        """
        Write text on page - BULLETPROOF with auto-restore from Supabase
        
        Args:
            text_data: [{"x": 10, "y": 20, "text": "...", "size": 30, "align": "top", "font": "arial"}]
        """
        # 1. Ensure input file exists - restore from Supabase if needed
        input_path = f"{self.TEMP_FOLDER}/{session_id}/page_{page_num}.png"
        
        if not os.path.exists(input_path):
            print(f"⚠️  Page {page_num} not found locally - attempting Supabase restore...")
            
            try:
                # Get session info from database
                session_data = self.supabase.table("pdf_sessions").select("*").eq(
                    "session_id", session_id
                ).single().execute()
                
                if not session_data.data:
                    raise FileNotFoundError(f"Session {session_id} not found in database")
                
                session = session_data.data
                user_id = session["user_id"]
                storage_path = session.get("storage_path")
                
                if not storage_path:
                    raise FileNotFoundError(
                        f"Session {session_id} has no storage_path - cannot restore"
                    )
                
                # Restore session from Supabase
                print(f"🔄 Restoring session from: {storage_path}")
                self.restore_session_from_storage(session_id, user_id, storage_path)
                
                # Update session status back to processing
                self.supabase.table("pdf_sessions").update({
                    "status": "processing"
                }).eq("session_id", session_id).execute()
                
                print(f"✅ Session restored successfully")
                
            except Exception as e:
                raise FileNotFoundError(
                    f"Failed to restore session {session_id} from Supabase: {str(e)}"
                )
        
        # 2. Ensure output folder exists
        output_session = f"{self.OUTPUT_FOLDER}/{session_id}"
        os.makedirs(output_session, exist_ok=True)
        output_path = f"{output_session}/page_{page_num}_filled.png"
        
        # 3. Load and process the image
        try:
            img = Image.open(input_path)
            width, height = img.size
            print(f"📄 Base image loaded: {width}x{height}px")
        except Exception as e:
            raise IOError(f"Failed to open page {page_num}: {str(e)}")
        
        cell_width = width / self.GRID_SIZE
        cell_height = height / self.GRID_SIZE
        
        draw = ImageDraw.Draw(img)
        
        # 4. Write all text with error handling
        successful_writes = 0
        
        for idx, item in enumerate(text_data, 1):
            try:
                # Validate required fields
                if 'x' not in item or 'y' not in item or 'text' not in item:
                    print(f"⚠️  Text {idx}: Missing required fields - skipping")
                    continue
                
                grid_x = item['x']
                grid_y = item['y']
                text = item['text']
                font_size = item.get('size', 20)
                alignment = item.get('align', 'top')
                font_name = item.get('font', 'arial')
                
                pixel_x = grid_x * cell_width
                pixel_y = grid_y * cell_height
                
                # Load font with fallback
                try:
                    font = self._load_font(session_id, font_name, font_size)
                except Exception as e:
                    print(f"⚠️  Text {idx}: Font '{font_name}' failed, using default - {e}")
                    font = ImageFont.load_default()
                
                # Adjust Y position based on alignment
                if alignment == 'bottom':
                    adjusted_y = pixel_y - font_size
                elif alignment == 'center':
                    adjusted_y = pixel_y - (font_size // 2)
                else:
                    adjusted_y = pixel_y
                
                draw.text((pixel_x, adjusted_y), text, fill=(0, 0, 0), font=font)
                print(f"  ✅ Text {idx}: '{text}' at ({grid_x}, {grid_y}) [font: {font_name}, size: {font_size}, align: {alignment}]")
                successful_writes += 1
                
            except Exception as e:
                print(f"⚠️  Text {idx}: Failed to write - {e}")
                continue
        
        # 5. Save the result
        try:
            img.save(output_path)
            print(f"✅ Saved: {output_path} ({successful_writes}/{len(text_data)} texts written)")
        except Exception as e:
            raise IOError(f"Failed to save output: {str(e)}")
        
        if successful_writes == 0 and len(text_data) > 0:
            raise RuntimeError(f"Failed to write any of the {len(text_data)} text items")
    
    def write_text_on_image_preview(self, image_path: str, text_items: list):
        """
        Write text directly on PNG image (for live preview)
        
        Similar to write_text_on_page but:
        - Works on existing PNG (not session-based)
        - Modifies image in-place
        - Used for temporary previews
        
        Args:
            image_path: Path to PNG file
            text_items: [{"x": 10, "y": 20, "text": "...", "size": 30, "align": "center", "font": "arial"}]
        
        Returns:
            None (modifies image in-place)
        """   
        try:
            # Load image
            img = Image.open(image_path)
            width, height = img.size
            draw = ImageDraw.Draw(img)
            
            cell_width = width / self.GRID_SIZE
            cell_height = height / self.GRID_SIZE
            
            for item in text_items:
                # Extract field data
                grid_x = item['x']
                grid_y = item['y']
                text = item['text']
                font_size = item.get('size', 20)
                alignment = item.get('align', 'center')
                font_name = item.get('font', 'arial')
                
                # Convert grid to pixel
                pixel_x = grid_x * cell_width
                pixel_y = grid_y * cell_height
                
                # Load font with fallback
                try:
                    font = self._load_font(None, font_name, font_size)
                except Exception as e:
                    print(f"⚠️  Font '{font_name}' failed, using default: {e}")
                    font = ImageFont.load_default()
                
                # Adjust Y position based on alignment
                if alignment == 'bottom':
                    adjusted_y = pixel_y - font_size
                elif alignment == 'center':
                    adjusted_y = pixel_y - (font_size // 2)
                else:  # top
                    adjusted_y = pixel_y
                
                # Draw text
                draw.text((pixel_x, adjusted_y), text, fill=(0, 0, 0), font=font)
                print(f"  ✅ Preview: '{text}' at grid ({grid_x}, {grid_y}) [size: {font_size}, align: {alignment}]")
            
            # Save modified image
            img.save(image_path)
            print(f"✅ Preview image saved: {image_path}")
            
        except Exception as e:
            print(f"❌ Preview rendering failed: {str(e)}")
            raise Exception(f"Failed to render preview: {str(e)}")
        
    def add_images_to_preview(self, preview_path: str, image_data: list):
        """
        Add images to an existing PNG preview (for live preview modal)
        
        Args:
            preview_path: Path to preview PNG
            image_data: List of dicts with 'x', 'y', 'image_path', optional 'width', 'height'
        """
        
        try:
            # Load the preview image
            base_image = Image.open(preview_path).convert('RGBA')
            page_width, page_height = base_image.size
            
            # Process each image
            for img_item in image_data:
                grid_x = img_item['x']
                grid_y = img_item['y']
                image_path = img_item['image_path']
                
                # Convert grid to pixel coordinates
                pixel_x = int((grid_x / self.GRID_SIZE) * page_width)
                pixel_y = int((grid_y / self.GRID_SIZE) * page_height)
                
                # Load and process the image to place
                overlay_img = Image.open(image_path).convert('RGBA')
                
                # Resize if dimensions specified
                if 'width' in img_item and 'height' in img_item and img_item['width'] and img_item['height']:
                    overlay_img = overlay_img.resize(
                        (int(img_item['width']), int(img_item['height'])),
                        Image.Resampling.LANCZOS
                    )
                elif 'width' in img_item and img_item['width']:
                    # Width only - maintain aspect ratio
                    aspect_ratio = overlay_img.height / overlay_img.width
                    new_height = int(img_item['width'] * aspect_ratio)
                    overlay_img = overlay_img.resize(
                        (int(img_item['width']), new_height),
                        Image.Resampling.LANCZOS
                    )
                elif 'height' in img_item and img_item['height']:
                    # Height only - maintain aspect ratio
                    aspect_ratio = overlay_img.width / overlay_img.height
                    new_width = int(img_item['height'] * aspect_ratio)
                    overlay_img = overlay_img.resize(
                        (new_width, int(img_item['height'])),
                        Image.Resampling.LANCZOS
                    )
                
                # Paste the overlay image onto the base
                base_image.paste(overlay_img, (pixel_x, pixel_y), overlay_img)
            
            # Save the modified preview
            base_image.save(preview_path, 'PNG')
            print(f"✅ Preview updated with {len(image_data)} image(s)")
            
        except Exception as e:
            print(f"❌ Failed to add images to preview: {str(e)}")
            raise
    
    def _load_font(self, session_id: str, font_name: str, font_size: int):
        """
        Load font with fallback priority:
        1. Custom uploaded font (session-specific)
        2. Built-in available font
        3. System default
        """
        try:
            # Priority 1: Custom uploaded font
            custom_font_path = f"fonts/{font_name}.ttf"
            if os.path.exists(custom_font_path):
                return ImageFont.truetype(custom_font_path, font_size)
            
            # Priority 2: Built-in font
            if font_name in AVAILABLE_FONTS:
                return ImageFont.truetype(AVAILABLE_FONTS[font_name], font_size)
            
            # Priority 3: Try as direct path
            if os.path.exists(font_name):
                return ImageFont.truetype(font_name, font_size)
            
            # Fallback: Default arial
            return ImageFont.truetype(AVAILABLE_FONTS.get("arial", "fonts/arial.ttf"), font_size)
        
        except Exception as e:
            print(f"⚠️  Font load failed: {e}. Using default.")
            return ImageFont.load_default()
        
    def add_images_to_page(self, session_id: str, page_number: int, image_data: List[Dict]):
        """
        Add images to page - BULLETPROOF with auto-restore from Supabase
        """
        # 1. Check if session exists locally, restore if needed
        session_temp_path = f"{self.TEMP_FOLDER}/{session_id}"
        
        if not os.path.exists(session_temp_path):
            print(f"⚠️  Session not found locally - attempting Supabase restore...")
            
            try:
                # Get session info from database
                session_data = self.supabase.table("pdf_sessions").select("*").eq(
                    "session_id", session_id
                ).single().execute()
                
                if not session_data.data:
                    raise FileNotFoundError(f"Session {session_id} not found in database")
                
                session = session_data.data
                user_id = session["user_id"]
                storage_path = session.get("storage_path")
                
                if not storage_path:
                    raise FileNotFoundError(
                        f"Session {session_id} has no storage_path - cannot restore"
                    )
                
                # Restore session from Supabase
                print(f"🔄 Restoring session from: {storage_path}")
                self.restore_session_from_storage(session_id, user_id, storage_path)
                
                # Update session status back to processing
                self.supabase.table("pdf_sessions").update({
                    "status": "processing"
                }).eq("session_id", session_id).execute()
                
                print(f"✅ Session restored successfully")
                
            except Exception as e:
                raise FileNotFoundError(
                    f"Failed to restore session {session_id} from Supabase: {str(e)}"
                )
        
        # 2. Ensure output folder exists
        output_folder = f"{self.OUTPUT_FOLDER}/{session_id}"
        os.makedirs(output_folder, exist_ok=True)
        
        # 3. Try to load the TEXT-FILLED page first, fallback to original
        filled_path = f"{output_folder}/page_{page_number}_filled.png"
        original_path = f"{self.TEMP_FOLDER}/{session_id}/page_{page_number}.png"
        
        if os.path.exists(filled_path):
            input_path = filled_path
            print(f"✅ Loading TEXT-FILLED page {page_number}")
        elif os.path.exists(original_path):
            input_path = original_path
            print(f"⚠️  Loading ORIGINAL page {page_number} (no text yet)")
        else:
            raise FileNotFoundError(
                f"Neither filled nor original page exists for page {page_number}. "
                f"Session may have failed to restore properly."
            )
        
        output_path = f"{output_folder}/page_{page_number}_filled.png"
        
        # 4. Load the base image with error handling
        try:
            img = Image.open(input_path)
            width, height = img.size
            print(f"📄 Base image loaded: {width}x{height}px")
        except Exception as e:
            raise IOError(f"Failed to open base image {input_path}: {str(e)}")
        
        cell_width = width / self.GRID_SIZE
        cell_height = height / self.GRID_SIZE
        
        # 5. Process each image with comprehensive error handling
        successful_placements = 0
        
        for idx, item in enumerate(image_data, 1):
            try:
                # Validate required fields
                if 'x' not in item or 'y' not in item or 'image_path' not in item:
                    print(f"⚠️  Image {idx}: Missing required fields (x, y, or image_path) - skipping")
                    continue
                
                grid_x = item['x']
                grid_y = item['y']
                image_path = item['image_path']
                
                # Validate image file exists
                if not os.path.exists(image_path):
                    print(f"⚠️  Image {idx}: File not found '{image_path}' - skipping")
                    continue
                
                # Calculate pixel coordinates
                pixel_x = int(grid_x * cell_width)
                pixel_y = int(grid_y * cell_height)
                
                # Validate coordinates are within bounds
                if pixel_x < 0 or pixel_y < 0 or pixel_x > width or pixel_y > height:
                    print(f"⚠️  Image {idx}: Coordinates ({pixel_x}, {pixel_y}) out of bounds - skipping")
                    continue
                
                # Load overlay image
                try:
                    overlay = Image.open(image_path)
                    print(f"  📷 Loaded image: {os.path.basename(image_path)} ({overlay.size[0]}x{overlay.size[1]})")
                except Exception as e:
                    print(f"⚠️  Image {idx}: Failed to open '{image_path}': {e} - skipping")
                    continue
                
                print(f"   🔎 Raw entry: {item}") 
                # Resize if dimensions provided
                if 'width' in item and 'height' in item:
                    try:
                        target_width = int(item['width'])
                        target_height = int(item['height'])
                        
                        if target_width > 0 and target_height > 0:
                            overlay = overlay.resize(
                                (target_width, target_height), 
                                Image.Resampling.LANCZOS
                            )
                            print(f"  🔄 Resized to {target_width}x{target_height}")
                        else:
                            print(f"⚠️  Image {idx}: Invalid dimensions ({target_width}x{target_height}) - using original")
                    except Exception as e:
                        print(f"⚠️  Image {idx}: Resize failed: {e} - using original size")
                
                # Paste with transparency support
                try:
                    if overlay.mode == 'RGBA':
                        img.paste(overlay, (pixel_x, pixel_y), overlay)
                    else:
                        img.paste(overlay, (pixel_x, pixel_y))
                    
                    print(f"  ✅ Image {idx} placed at grid ({grid_x}, {grid_y}) -> pixel ({pixel_x}, {pixel_y})")
                    successful_placements += 1
                    
                except Exception as e:
                    print(f"⚠️  Image {idx}: Paste failed: {e} - skipping")
                    continue
                    
            except KeyError as e:
                print(f"⚠️  Image {idx}: Missing required field: {e} - skipping")
                continue
            except Exception as e:
                print(f"⚠️  Image {idx}: Unexpected error: {e} - skipping")
                continue
        
        # 6. Save the result with error handling
        try:
            img.save(output_path)
            print(f"✅ Saved: {output_path} ({successful_placements}/{len(image_data)} images placed)")
        except Exception as e:
            raise IOError(f"Failed to save output image to {output_path}: {str(e)}")
        
        if successful_placements == 0 and len(image_data) > 0:
            raise RuntimeError(f"Failed to place any of the {len(image_data)} images. Check logs for details.")
    
    def upload_to_storage(self, local_path: str, storage_path: str) -> str:
        """
        Upload to PRIVATE bucket and return signed URL
        Signed URLs expire after 1 hour for security
        """
        with open(local_path, 'rb') as f:
            file_data = f.read()
        
        # Upload to private bucket
        self.supabase.storage.from_(self.STORAGE_BUCKET).upload(
            path=storage_path,
            file=file_data,
            file_options={
                "content-type": "application/pdf",
                "upsert": "true"
                }
        )
        
        # Generate signed URL (expires in 1 hour)
        signed_url_response = self.supabase.storage.from_(self.STORAGE_BUCKET).create_signed_url(
            storage_path,
            3600  # 1 hour expiry
        )
        
        return signed_url_response['signedURL']
    
    def create_pdf(
        self,
        session_id: str,
        num_pages: int,
        output_name: str = "output_complete.pdf"
    ) -> str:
        """
        Create final PDF from filled pages (LOCAL ONLY)
        Use create_pdf_with_upload() to also upload to Supabase
        
        Args:
            session_id: Session identifier
            num_pages: Total number of pages
            output_name: Output PDF filename
            
        Returns:
            Path to generated PDF
        """
        output_session = f"{self.OUTPUT_FOLDER}/{session_id}"
        image_list = []
        
        for i in range(1, num_pages + 1):
            filled_path = f"{output_session}/page_{i}_filled.png"
            if os.path.exists(filled_path):
                image_list.append(filled_path)
            else:
                # Use original if not filled
                image_list.append(f"{self.TEMP_FOLDER}/{session_id}/page_{i}.png")
        
        output_pdf = f"{output_session}/{output_name}"
        with open(output_pdf, "wb") as f:
            f.write(img2pdf.convert(image_list))
        
        print(f"Created local PDF: {output_pdf}")
        return output_pdf
    
    def create_pdf_with_upload(
        self,
        session_id: str,
        user_id: str,
        num_pages: int,
        output_name: str = "output_complete.pdf"
    ) -> Dict:
        """
        Create final PDF and upload to Supabase Storage
        
        Args:
            session_id: Session identifier
            user_id: User ID (for storage path)
            num_pages: Total number of pages
            output_name: Output PDF filename
            
        Returns:
            Dict with local_path, storage_url, and storage_path
        """
        # Create PDF locally first
        local_pdf_path = self.create_pdf(session_id, num_pages, output_name)
        
        # Upload to Supabase Storage
        storage_path = f"{user_id}/{session_id}/{output_name}"
        storage_url = self.upload_to_storage(local_pdf_path, storage_path)
        
        print(f"✅ Uploaded to Supabase Storage: {storage_url}")
        
        return {
            "local_path": local_pdf_path,
            "storage_url": storage_url,
            "storage_path": storage_path
        }
    
    def upload_original_pdf(self, local_path: str, user_id: str, session_id: str) -> str:
        """
        Upload original PDF to Supabase Storage
        This preserves the original in case user wants it later
        """
        storage_path = f"{user_id}/{session_id}/original.pdf"
        
        with open(local_path, 'rb') as f:
            self.supabase.storage.from_(self.STORAGE_BUCKET).upload(
                path=storage_path,
                file=f.read(),
                file_options={
                    "content-type": "application/pdf",
                    "upsert":"true"
                    }
            )
        
        return storage_path

    def restore_session_from_storage(self, session_id: str, user_id: str, storage_path: str) -> int:
        """
        Restore a session from Supabase Storage
        Downloads original PDF and recreates temp files
        
        Args:
            session_id: Session to restore
            user_id: User ID
            storage_path: Path to original PDF in storage (e.g., "user_id/session_id/original.pdf")
            
        Returns:
            Number of pages
        """
        try:
            # Ensure storage_path is the original PDF path
            if not storage_path.endswith("original.pdf"):
                storage_path = f"{user_id}/{session_id}/original.pdf"
            
            print(f"🔄 Restoring session from: {storage_path}")
            
            # Download from Supabase Storage
            response = self.supabase.storage.from_(self.STORAGE_BUCKET).download(
                storage_path
            )
            
            # Save to local temp folder
            session_folder = f"{self.TEMP_FOLDER}/{session_id}"
            os.makedirs(session_folder, exist_ok=True)
            pdf_path = f"{session_folder}/original.pdf"
            
            with open(pdf_path, 'wb') as f:
                f.write(response)
            
            # Convert to images
            num_pages = self.pdf_to_images(pdf_path, session_id)
            
            print(f"✅ Restored session {session_id} from storage ({num_pages} pages)")
            return num_pages
        
        except Exception as e:
            raise Exception(f"Failed to restore session: {str(e)}")
        
    def apply_grid_to_page(self, session_id: str, page_num: int) -> str:
        """
        Apply grid overlay to a page image
        
        Args:
            session_id: Session identifier
            page_num: Page number
            
        Returns:
            Path to gridded image
        """
        input_path = f"{self.TEMP_FOLDER}/{session_id}/page_{page_num}.png"
        
        # Create gridded folder for session
        gridded_folder = f"{self.GRIDDED_FOLDER}/{session_id}"
        os.makedirs(gridded_folder, exist_ok=True)
        output_path = f"{gridded_folder}/page_{page_num}_gridded.png"
        
        img = Image.open(input_path)
        width, height = img.size
        
        cell_width = width / self.GRID_SIZE
        cell_height = height / self.GRID_SIZE
        
        draw = ImageDraw.Draw(img)
        
        # Draw grid lines
        for i in range(self.GRID_SIZE + 1):
            x = int(i * cell_width)
            y = int(i * cell_height)
            
            line_width = 3 if i % 10 == 0 else 1
            line_color = (150, 150, 150) if i % 10 == 0 else (220, 220, 220)
            
            draw.line([(x, 0), (x, height)], fill=line_color, width=line_width)
            draw.line([(0, y), (width, y)], fill=line_color, width=line_width)
        
        # Add grid labels
        try:
            font_size = max(8, int(width / 150))
            font = ImageFont.truetype("fonts/arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        for i in range(self.GRID_SIZE + 1):
            x = int(i * cell_width)
            y = int(i * cell_height)
            
            # X-axis labels (vertical text at top)
            text = f"{i}"
            # Create a temporary image for the text
            txt_img = Image.new('RGBA', (font_size * 3, font_size * len(text) * 2), (255, 255, 255, 0))
            txt_draw = ImageDraw.Draw(txt_img)
            txt_draw.text((0, 0), text, fill=(255, 0, 0), font=font)
            # Rotate 90 degrees counter-clockwise
            txt_img = txt_img.rotate(90, expand=True)
            # Paste at the top (y=0)
            img.paste(txt_img, (x + 2, -5), txt_img)
            
            # Y-axis labels (horizontal at left)
            draw.text((2, y + 2), text, fill=(0, 0, 255), font=font)
        
        img.save(output_path)
        print(f"Applied grid to page {page_num}")
        return output_path

    def download_file_from_storage(self, storage_path: str, local_path: str):
        """
        Downloads a file from the configured Supabase Storage bucket 
        to a specified local path.

        Args:
            storage_path: The path of the file in the Supabase bucket (e.g., 'user_id/session_id/original.pdf').
            local_path: The full path where the file should be saved locally.
        
        Raises:
            Exception: If the download from Supabase fails.
        """
        print(f"⬇️ Downloading from storage: {storage_path} to {local_path}")
        try:
            # 1. Download file content from Supabase
            response = self.supabase.storage.from_(self.STORAGE_BUCKET).download(
                path=storage_path
            )
            
            # 2. Ensure the local directory exists before writing
            local_dir = os.path.dirname(local_path)
            os.makedirs(local_dir, exist_ok=True)
            
            # 3. Write the downloaded content (bytes) to the local file
            with open(local_path, 'wb') as f:
                f.write(response)
            
            print(f"✅ Successfully downloaded {storage_path}")

        except Exception as e:
            # Supabase download often returns an HTTP error within the Exception message
            raise Exception(f"Supabase download failed for {storage_path}: {str(e)}")
        
    def download_pdf_from_storage(self, storage_path: str, local_path: str):
        """
        Downloads a PDF file from the configured Supabase Storage bucket 
        to a specified local path. (This method is correctly named to resolve your AttributeError).

        Args:
            storage_path: The path of the file in the Supabase bucket (e.g., 'templates/user_id/id.pdf').
            local_path: The full path where the file should be saved locally (e.g., '/tmp/temp_file.pdf').
        
        Raises:
            Exception: If the download from Supabase fails.
        """
        print(f"⬇️ Downloading PDF from storage: {storage_path} to {local_path}")
        try:
            # 1. Download file content from Supabase
            # Note: This client respects RLS, so it requires an authenticated token 
            # (or admin client, as discussed) in the request context to succeed.
            response = self.supabase.storage.from_(self.STORAGE_BUCKET).download(
                path=storage_path
            )
            
            # 2. Ensure the local directory exists before writing
            local_dir = os.path.dirname(local_path)
            os.makedirs(local_dir, exist_ok=True)
            
            # 3. Write the downloaded content (bytes) to the local file
            with open(local_path, 'wb') as f:
                f.write(response)
            
            print(f"✅ Successfully downloaded PDF {storage_path}")

        except Exception as e:
            # Re-raise with descriptive error message
            raise Exception(f"Supabase PDF download failed for {storage_path}: {str(e)}")
        
    def pdf_to_images_single_page(
        self, 
        pdf_path: str, 
        session_id: str, 
        page_num: int
    ) -> str:
        """
        Convert SINGLE page to image (memory efficient).
        
        Args:
            pdf_path: Path to PDF file
            session_id: Unique session identifier
            page_num: Page number to convert (1-indexed)
            
        Returns:
            Path to saved image
        """
        print(f"Converting page {page_num} to image (session: {session_id})...")
        
        try:
            # Convert ONLY this one page
            images = convert_from_path(
                pdf_path, 
                dpi=self.DPI,
                first_page=page_num,
                last_page=page_num
            )
            
            session_folder = f"{self.TEMP_FOLDER}/{session_id}"
            os.makedirs(session_folder, exist_ok=True)
            
            image_path = f"{session_folder}/page_{page_num}.png"
            images[0].save(image_path, 'PNG')
            
            print(f"✅ Converted page {page_num}")
            return image_path
            
        except Exception as e:
            raise RuntimeError(f"Failed to convert page {page_num}: {e}")


    def get_pdf_page_count(self, pdf_path: str) -> int:
        """Get number of pages in PDF without loading all pages into memory"""
        from pdf2image.pdf2image import pdfinfo_from_path
        
        try:
            info = pdfinfo_from_path(pdf_path)
            page_count = info.get("Pages", 0)
            print(f"📊 PDF has {page_count} pages")
            return page_count
        except Exception as e:
            # Fallback: Convert first page only to detect pages
            # This is slower but guaranteed to work
            print(f"⚠️  pdfinfo failed ({e}), using fallback method...")
            try:
                images = convert_from_path(pdf_path, dpi=72, last_page=1)
                # Use poppler's page count from conversion
                from pdf2image import convert_from_path as cfp
                # Actually, let's just count by converting at very low quality
                low_res = convert_from_path(pdf_path, dpi=50)  # Fast, low memory
                return len(low_res)
            except Exception as e2:
                raise RuntimeError(f"Failed to get page count: {e2}")