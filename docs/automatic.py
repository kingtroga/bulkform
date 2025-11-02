"""
Automatic form filler - No manual input needed!
Test script for the gotech.pdf form
"""

from main import (
    setup_folders, cleanup_folders, pdf_to_images, 
    grid_all_pages, write_text_on_image, add_images_to_page,
    create_output_pdf
)
import os

def fill_gotech_form():
    """Automatically fill the gotech employment guarantor form"""
    
    print("="*60)
    print("AUTOMATIC PDF FORM FILLER - GOTECH FORM")
    print("="*60)
    
    # Setup
    setup_folders()
    
    # PDF path
    pdf_path = "gotech.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"❌ Error: {pdf_path} not found!")
        print("Make sure gotech.pdf is in the same folder as this script.")
        return
    
    # Convert PDF to images
    num_pages = pdf_to_images(pdf_path)
    grid_all_pages(num_pages)
    
    print("\n" + "="*60)
    print("FILLING PAGE 1 - GUARANTOR DETAILS")
    print("="*60)
    
    # Page 1 data
    page1_text = [
        # Guarantor Details Section
        {'x': 33, 'y': 50, 'text': 'YEKOROGHA, Ayebatariwalate', 'size': 30, 'align': 'center'},
        {'x': 54, 'y': 54, 'text': 'Friend', 'size': 30, 'align': 'center'},
        {'x': 36, 'y': 58, 'text': 'Software Engineer', 'size': 30, 'align': 'center'},
        {'x': 42, 'y': 62, 'text': 'SINGH, Pavittar', 'size': 30, 'align': 'center'},
        {'x': 43, 'y': 66, 'text': 'India', 'size': 30, 'align': 'center'},
        {'x': 57, 'y': 70, 'text': '+2348087422585', 'size': 30, 'align': 'center'},
        {'x': 55, 'y': 74, 'text': 'tariyekorogha@gmail.com', 'size': 30, 'align': 'center'},
        {'x': 46, 'y': 78, 'text': '16, Providence Close, Coker Estate, Shasha, Lagos', 'size': 30, 'align': 'center'},
        
        # Checkbox for International Passport
        {'x': 24, 'y': 89, 'text': '●', 'size': 30, 'align': 'center'},
        
        # Guarantor's Declaration Section
        {'x': 21, 'y': 104, 'text': 'YEKOROGHA, Ayebatariwalate', 'size': 30, 'align': 'center'},
        {'x': 26, 'y': 107, 'text': 'OLUMILUA, Divine Favour', 'size': 30, 'align': 'center'},
    ]
    
    write_text_on_image(1, page1_text)
    
    print("\n" + "="*60)
    print("FILLING PAGE 2 - SIGNATURE & DATE")
    print("="*60)
    
    # Page 2 data
    page2_text = [
        {'x': 27, 'y': 23, 'text': '1st November, 2025', 'size': 36, 'align': 'center'},
    ]
    
    write_text_on_image(2, page2_text)
    
    # Add signature if available
    signature_path = "signature.png"
    if os.path.exists(signature_path):
        print("\n📝 Adding signature...")
        page2_images = [
            {'x': 40, 'y': 18, 'image_path': signature_path, 'width': 200, 'height': 60}
        ]
        add_images_to_page(2, page2_images)
    else:
        print("\n⚠️  No signature.png found - skipping signature")
        print("   (Create a signature.png file to auto-add it)")
    
    # Create final PDF
    print("\n" + "="*60)
    print("CREATING OUTPUT PDF")
    print("="*60)
    
    create_output_pdf(num_pages)
    
    print("\n" + "="*60)
    print("✅ DONE!")
    print("="*60)
    print(f"Output: output_complete.pdf")
    print("\nCleanup temp folders? (they contain intermediate files)")
    cleanup = input("Delete temp folders? (y/n): ").lower()
    if cleanup == 'y':
        cleanup_folders()
        print("🗑️  Temp folders deleted")
    
    print("\n🎉 Form filled successfully! Check output_complete.pdf")

if __name__ == "__main__":
    fill_gotech_form()