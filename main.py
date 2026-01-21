"""
PDF Form Filler - Single Script Version
Simple CLI tool to fill PDF forms using grid coordinates
"""

from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
import img2pdf
import os
import shutil

# Configuration
GRID_SIZE = 150
DPI = 150
TEMP_FOLDER = "temp_pages"
GRIDDED_FOLDER = "gridded_pages"
OUTPUT_FOLDER = "filled_pages"

def setup_folders():
    """Create necessary folders"""
    for folder in [TEMP_FOLDER, GRIDDED_FOLDER, OUTPUT_FOLDER]:
        os.makedirs(folder, exist_ok=True)

def cleanup_folders():
    """Delete temporary folders"""
    for folder in [TEMP_FOLDER, GRIDDED_FOLDER]:
        if os.path.exists(folder):
            shutil.rmtree(folder)

def pdf_to_images(pdf_path):
    """Convert PDF pages to images"""
    print(f"\nConverting PDF to images...")
    images = convert_from_path(pdf_path, dpi=DPI)
    
    for idx, img in enumerate(images, 1):
        img.save(f"{TEMP_FOLDER}/page_{idx}.png")
    
    print(f"Converted {len(images)} page(s)")
    return len(images)

def apply_grid(image_path, output_path):
    """Apply grid overlay to image with ADAPTIVE grid size"""
    img = Image.open(image_path)
    width, height = img.size
    
    # 🚀 ADAPTIVE GRID SIZE
    min_cell_size = 3
    max_grid_size = min(width // min_cell_size, height // min_cell_size, 150)
    grid_size = (max_grid_size // 10) * 10
    
    print(f"📐 Page: {width}x{height}px → Grid: {grid_size}x{grid_size} (cell: {width/grid_size:.1f}x{height/grid_size:.1f}px)")
    
    cell_width = width / grid_size
    cell_height = height / grid_size
    
    draw = ImageDraw.Draw(img)
    
    # ✨ ADAPTIVE LINE WIDTH - THIN VERSION
    # Smaller grids = thinner lines to avoid chunky look
    if grid_size >= 120:
        major_width = 2
        minor_width = 1
    elif grid_size >= 80:
        major_width = 1
        minor_width = 1
    else:
        major_width = 1
        minor_width = 1
    
    # Draw grid lines with FLOAT coordinates
    for i in range(grid_size + 1):
        x = i * cell_width
        y = i * cell_height
        
        # Use adaptive widths
        line_width = major_width if i % 10 == 0 else minor_width
        line_color = (150, 150, 150) if i % 10 == 0 else (220, 220, 220)
        
        draw.line([(x, 0), (x, height)], fill=line_color, width=line_width)
        draw.line([(0, y), (width, y)], fill=line_color, width=line_width)
    
    # Labels - only every 10th line
    try:
        font_size = max(8, int(width / 100))
        font = ImageFont.truetype(r"fonts\arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    for i in range(0, grid_size + 1, 10):
        x = i * cell_width
        y = i * cell_height
        draw.text((x + 2, 2), f"{i}", fill=(255, 0, 0), font=font)
        draw.text((2, y + 2), f"{i}", fill=(0, 0, 255), font=font)
    
    img.save(output_path)
    return grid_size

def write_text_on_image(page_num, text_data, grid_size=150):
    """Write text - now accepts dynamic grid_size"""
    input_path = f"{TEMP_FOLDER}/page_{page_num}.png"
    output_path = f"{OUTPUT_FOLDER}/page_{page_num}_filled.png"
    
    img = Image.open(input_path)
    width, height = img.size
    
    # ✅ FLOAT PRECISION
    cell_width = width / grid_size
    cell_height = height / grid_size
    
    draw = ImageDraw.Draw(img)
    
    for item in text_data:
        grid_x = item['x']
        grid_y = item['y']
        text = item['text']
        font_size = item.get('size', 20)
        alignment = item.get('align', 'top')
        
        # ✅ FLOAT PRECISION - Only round at final pixel placement
        pixel_x = grid_x * cell_width
        pixel_y = grid_y * cell_height
        
        try:
            font = ImageFont.truetype("fonts/arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # Adjust Y based on alignment
        if alignment == 'bottom':
            adjusted_y = pixel_y - font_size
        elif alignment == 'center':
            adjusted_y = pixel_y - (font_size // 2)
        else:
            adjusted_y = pixel_y
        
        draw.text((pixel_x, adjusted_y), text, fill=(0, 0, 0), font=font)
        print(f"  ✅ '{text}' at grid ({grid_x}, {grid_y}) → pixel ({pixel_x:.1f}, {adjusted_y:.1f})")
    
    img.save(output_path)
    """Apply grid overlay to image"""
    img = Image.open(image_path)
    width, height = img.size
    
    cell_width = width / GRID_SIZE
    cell_height = height / GRID_SIZE
    
    draw = ImageDraw.Draw(img)
    
    # Draw grid lines
    for i in range(GRID_SIZE + 1):
        x = int(i * cell_width)
        y = int(i * cell_height)
        
        line_width = 3 if i % 10 == 0 else 1
        line_color = (150, 150, 150) if i % 10 == 0 else (220, 220, 220)
        
        draw.line([(x, 0), (x, height)], fill=line_color, width=line_width)
        draw.line([(0, y), (width, y)], fill=line_color, width=line_width)
    
    # Add labels
    try:
        font_size = max(8, int(width / 150))
        font = ImageFont.truetype(r"fonts\arial.ttf", font_size)
        print("worked")
    except:
        font = ImageFont.load_default()
    
    for i in range(GRID_SIZE + 1):
        x = int(i * cell_width)
        y = int(i * cell_height)
        draw.text((x + 2, 2), f"{i}", fill=(255, 0, 0), font=font)
        draw.text((2, y + 2), f"{i}", fill=(0, 0, 255), font=font)
    
    img.save(output_path)

def grid_all_pages(num_pages):
    """Apply grid to all pages"""
    print(f"\nApplying grid to {num_pages} page(s)...")
    for i in range(1, num_pages + 1):
        input_path = f"{TEMP_FOLDER}/page_{i}.png"
        output_path = f"{GRIDDED_FOLDER}/page_{i}_gridded.png"
        apply_grid(input_path, output_path)
    print("Grid applied to all pages")

def display_image(image_path):
    """Display image using system default viewer"""
    img = Image.open(image_path)
    img.show()

def create_output_pdf(num_pages, single_page=None):
    """Create final PDF from filled pages"""
    if single_page:
        # Single page PDF
        filled_path = f"{OUTPUT_FOLDER}/page_{single_page}_filled.png"
        output_pdf = f"output_page_{single_page}.pdf"
        
        with open(output_pdf, "wb") as f:
            f.write(img2pdf.convert(filled_path))
        
        print(f"\nCreated: {output_pdf}")
    else:
        # Multi-page PDF
        image_list = []
        for i in range(1, num_pages + 1):
            filled_path = f"{OUTPUT_FOLDER}/page_{i}_filled.png"
            if os.path.exists(filled_path):
                image_list.append(filled_path)
            else:
                # Use original if not filled
                image_list.append(f"{TEMP_FOLDER}/page_{i}.png")
        
        output_pdf = "output_complete.pdf"
        with open(output_pdf, "wb") as f:
            f.write(img2pdf.convert(image_list))
        
        print(f"\nCreated: {output_pdf}")

def main():
    print("="*60)
    print("PDF FORM FILLER")
    print("="*60)
    
    setup_folders()
    
    # Step 1: Load PDF
    pdf_path = input("\nEnter PDF path: ").strip()
    if not os.path.exists(pdf_path):
        print("PDF not found!")
        return
    
    # Step 2 & 3: Convert and grid
    num_pages = pdf_to_images(pdf_path)
    grid_all_pages(num_pages)
    
    while True:
        print("\n" + "="*60)
        print("MENU")
        print("="*60)
        print("1. View gridded page")
        print("2. Fill page with text")
        print("3. Create output PDF (single page)")
        print("4. Create output PDF (all pages)")
        print("5. Exit")
        
        choice = input("\nChoice: ").strip()
        
        if choice == "1":
            # Step 4: Display gridded page
            page = int(input(f"Page number (1-{num_pages}): "))
            gridded_path = f"{GRIDDED_FOLDER}/page_{page}_gridded.png"
            display_image(gridded_path)
            input("Press Enter after closing image...")
        
        elif choice == "2":
            # Step 5 & 6: Fill page
            page = int(input(f"Page number (1-{num_pages}): "))
            
            text_data = []
            print("\nEnter text data (empty text to finish):")
            print("Alignment options: 'top' (default), 'center', 'bottom'")
            while True:
                text = input("  Text: ").strip()
                if not text:
                    break
                x = int(input("  Grid X: "))
                y = int(input("  Grid Y: "))
                size = int(input("  Font size (default 20): ") or "20")
                align = input("  Alignment (top/center/bottom, default 'top'): ").strip().lower() or "top"
                
                # Validate alignment
                if align not in ['top', 'center', 'bottom']:
                    print(f"  ⚠️  Invalid alignment '{align}', using 'top'")
                    align = 'top'
                
                text_data.append({
                    'x': x, 
                    'y': y, 
                    'text': text, 
                    'size': size,
                    'align': align
                })
            
            if text_data:
                write_text_on_image(page, text_data)
        
        elif choice == "3":
            # Step 7: Single page PDF
            page = int(input(f"Page number (1-{num_pages}): "))
            create_output_pdf(num_pages, single_page=page)
        
        elif choice == "4":
            # Step 7: All pages PDF
            create_output_pdf(num_pages)
        
        elif choice == "5":
            # Step 8: Exit
            cleanup = input("Delete temp folders? (y/n): ").lower()
            if cleanup == 'y':
                cleanup_folders()
            print("Goodbye!")
            break

if __name__ == "__main__":
    main()