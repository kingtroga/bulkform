"""
PDF Processing Service with Supabase Storage
Core logic for PDF manipulation
"""
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
import img2pdf
import os
import shutil
from typing import List, Dict
from services.supabase_client import get_supabase


# Configuration
GRID_SIZE = 150
DPI = 300
TEMP_FOLDER = "temp_pdf_uploads"
GRIDDED_FOLDER = "gridded_pages"
OUTPUT_FOLDER = "filled_pages"
STORAGE_BUCKET = "pdfs"  # Supabase bucket name


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
    
    def pdf_to_images(self, pdf_path: str, session_id: str) -> int:
        """
        Convert PDF pages to images
        
        Args:
            pdf_path: Path to PDF file
            session_id: Unique session identifier
            
        Returns:
            Number of pages converted
        """
        print(f"Converting PDF to images (session: {session_id})...")
        images = convert_from_path(pdf_path, dpi=self.DPI)
        
        session_folder = f"{self.TEMP_FOLDER}/{session_id}"
        os.makedirs(session_folder, exist_ok=True)
        
        for idx, img in enumerate(images, 1):
            img.save(f"{session_folder}/page_{idx}.png")
        
        print(f"Converted {len(images)} page(s)")
        return len(images)
    
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
        Write text on a PDF page with alignment support
        
        Args:
            session_id: Session identifier
            page_num: Page number
            text_data: List of text items [{"x": 10, "y": 20, "text": "...", "size": 30, "align": "top"}]
        """
        input_path = f"{self.TEMP_FOLDER}/{session_id}/page_{page_num}.png"
        
        # Create output folder for session
        output_session = f"{self.OUTPUT_FOLDER}/{session_id}"
        os.makedirs(output_session, exist_ok=True)
        output_path = f"{output_session}/page_{page_num}_filled.png"
        
        img = Image.open(input_path)
        width, height = img.size
        
        cell_width = width / self.GRID_SIZE
        cell_height = height / self.GRID_SIZE
        
        draw = ImageDraw.Draw(img)
        
        for item in text_data:
            grid_x = item['x']
            grid_y = item['y']
            text = item['text']
            font_size = item.get('size', 20)
            alignment = item.get('align', 'top')
            
            pixel_x = int(grid_x * cell_width)
            pixel_y = int(grid_y * cell_height)
            
            try:
                font = ImageFont.truetype("fonts/arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
            
            # Adjust Y position based on alignment
            if alignment == 'bottom':
                adjusted_y = pixel_y - font_size  # Text ABOVE the line
            elif alignment == 'center':
                adjusted_y = pixel_y - (font_size // 2)  # Text CENTERED on line
            else:  # 'top'
                adjusted_y = pixel_y  # Text BELOW the line
            
            draw.text((pixel_x, adjusted_y), text, fill=(0, 0, 0), font=font)
            print(f"  Wrote '{text}' at ({grid_x}, {grid_y}) [align: {alignment}]")
        
        img.save(output_path)
        print(f"Saved filled page: {output_path}")
    
    def add_images_to_page(
        self,
        session_id: str,
        page_num: int,
        image_data: List[Dict]
    ):
        """
        Add signature/stamp images to a page
        
        Args:
            session_id: Session identifier
            page_num: Page number
            image_data: List of images [{"x": 25, "y": 16, "image_path": "...", "width": 200, "height": 60}]
        """
        # Check if page already has text filled
        output_session = f"{self.OUTPUT_FOLDER}/{session_id}"
        os.makedirs(output_session, exist_ok=True)
        
        input_path = f"{output_session}/page_{page_num}_filled.png"
        if not os.path.exists(input_path):
            input_path = f"{self.TEMP_FOLDER}/{session_id}/page_{page_num}.png"
        
        output_path = f"{output_session}/page_{page_num}_filled.png"
        
        img = Image.open(input_path)
        width, height = img.size
        
        cell_width = width / self.GRID_SIZE
        cell_height = height / self.GRID_SIZE
        
        for item in image_data:
            grid_x = item['x']
            grid_y = item['y']
            image_path = item['image_path']
            
            pixel_x = int(grid_x * cell_width)
            pixel_y = int(grid_y * cell_height)
            
            # Load the image
            overlay = Image.open(image_path)
            
            # Resize if dimensions provided
            if 'width' in item and 'height' in item:
                overlay = overlay.resize(
                    (item['width'], item['height']), 
                    Image.Resampling.LANCZOS
                )
            
            # Paste with transparency support
            if overlay.mode == 'RGBA':
                img.paste(overlay, (pixel_x, pixel_y), overlay)
            else:
                img.paste(overlay, (pixel_x, pixel_y))
            
            print(f"  Placed '{os.path.basename(image_path)}' at ({grid_x}, {grid_y})")
        
        img.save(output_path)
        print(f"Saved page with images: {output_path}")
    
    # services/pdf_processor.py

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
        Restore a completed session from Supabase Storage
        Downloads original PDF and recreates temp files
        
        Args:
            session_id: Session to restore
            user_id: User ID
            storage_path: Path to original PDF in storage
            
        Returns:
            Number of pages
        """
        try:
            # Extract original PDF storage path
            original_storage_path = f"{user_id}/{session_id}/original.pdf"
            
            # Download from Supabase Storage
            response = self.supabase.storage.from_(self.STORAGE_BUCKET).download(
                original_storage_path
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
        
        for i in range(0, self.GRID_SIZE + 1, 10):  # Every 10 lines
            x = int(i * cell_width)
            y = int(i * cell_height)
            draw.text((x + 2, 2), f"{i}", fill=(255, 0, 0), font=font)
            draw.text((2, y + 2), f"{i}", fill=(0, 0, 255), font=font)
        
        img.save(output_path)
        print(f"Applied grid to page {page_num}")
        return output_path