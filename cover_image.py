# main.py - Standalone Blog Cover Generator
from PIL import Image, ImageDraw, ImageFont
import uuid
import re

def wrap_text(text: str, max_chars_per_line: int = 40, manual_breaks: bool = False) -> str:
    """
    Wrap text with specific word count rules:
    - If manual_breaks=True, use user's \n breaks (no auto-wrapping)
    - Otherwise: Auto wrap with max 4 words line 1, 5 words lines 2-3
    """
    
    # Check if user provided manual line breaks
    if '\n' in text or manual_breaks:
        lines = text.split('\n')
        
        # VALIDATION: Only 4 lines allowed
        if len(lines) > 4:
            raise ValueError(f"Too many lines! Got {len(lines)} lines, max is 4")
        
        # VALIDATION: Max chars per line
        for i, line in enumerate(lines, 1):
            if len(line) > max_chars_per_line:
                raise ValueError(f"Line {i} too long! '{line}' ({len(line)} chars, max {max_chars_per_line})")
        
        return '\n'.join(lines)
    
    # AUTO-WRAP MODE (original logic)
    words = text.split()
    
    # Single line case
    if len(words) <= 4:
        lines = [' '.join(words)]
    
    # Two line case
    elif len(words) <= 9:  # 4 + 5 = 9 words max for 2 lines
        # Split at 4 words
        line1_words = words[:4]
        line2_words = words[4:]
        
        # Check if last word of line 1 is too long (>6 chars)
        if line1_words and len(line1_words[-1]) > 6:
            # Move last word to line 2
            line2_words.insert(0, line1_words.pop())
        
        line1 = ' '.join(line1_words)
        line2 = ' '.join(line2_words)
        lines = [line1, line2]
    
    # Three line case
    else:
        # Line 1: First 4 words
        line1_words = words[:4]
        remaining = words[4:]
        
        # Check if last word of line 1 is too long (>6 chars)
        if line1_words and len(line1_words[-1]) > 6:
            # Move last word to remaining
            remaining.insert(0, line1_words.pop())
        
        # Line 2: Next 5 words
        line2_words = remaining[:5]
        line3_words = remaining[5:]
        
        line1 = ' '.join(line1_words)
        line2 = ' '.join(line2_words)
        line3 = ' '.join(line3_words)
        lines = [line1, line2, line3]
    
    # VALIDATION: Check word count (only for auto-wrap)
    if len(lines) >= 2:
        line1_word_count = len(lines[0].split())
        if line1_word_count > 4:
            raise ValueError(f"Line 1 has {line1_word_count} words, max is 4")
    
    if len(lines) >= 2:
        line2_word_count = len(lines[1].split())
        if line2_word_count > 5:
            raise ValueError(f"Line 2 has {line2_word_count} words, max is 5")
    
    if len(lines) >= 3:
        line3_word_count = len(lines[2].split())
        if line3_word_count > 5:
            raise ValueError(f"Line 3 has {line3_word_count} words, max is 5")
    
    # VALIDATION: Max chars per line
    for i, line in enumerate(lines, 1):
        if len(line) > max_chars_per_line:
            raise ValueError(f"Line {i} too long! '{line}' ({len(line)} chars, max {max_chars_per_line})")
    
    # VALIDATION: Only 4 lines allowed
    if len(lines) > 4:
        raise ValueError(f"Title too long! Got {len(lines)} lines, max is 4")
    
    return '\n'.join(lines)


def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title"""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = slug.strip('-')
    return slug


def generate_cover_image(title: str, output_folder: str = "output", base_image_path: str = "images/blog-cover-base.jpg"):
    """
    Generate cover image by overlaying title on existing base template.
    Saves to output folder.
    """
    # Load your base template image
    try:
        image = Image.open(base_image_path)
    except FileNotFoundError:
        raise Exception(f"Base image not found at {base_image_path}. Please upload your base template.")
    
    # Ensure image is 1200x630 (OG standard)
    image = image.resize((1200, 630), Image.Resampling.LANCZOS)
    
    draw = ImageDraw.Draw(image)
    
    # Wrap title text for better fit
    wrapped_title = wrap_text(title, max_chars_per_line=40)
    
    # Load Inter font
    try:
        font_title = ImageFont.truetype("fonts/inter.ttf", 72)
    except:
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/inter/Inter-Bold.ttf", 72)
        except:
            try:
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
            except:
                # Fallback to default font
                font_title = ImageFont.load_default()
                print("⚠️ Warning: Using default font. For best results, install Inter font.")
    
    # SHIFTED LEFT: 80px from left edge
    text_x = 80
    text_y = 130
    
    # Add text shadow for better readability
    shadow_offset = 4
    draw.text((text_x + shadow_offset, text_y + shadow_offset), 
            wrapped_title, font=font_title, fill=(200, 205, 210, 90))
    
    # Main title text in #0058FF
    draw.text((text_x, text_y), wrapped_title, font=font_title, fill=(0, 88, 255))
    
    # Save to output folder
    slug = generate_slug(title)
    output_path = f"{output_folder}/{slug}.png"
    
    # Create output folder if it doesn't exist
    import os
    os.makedirs(output_folder, exist_ok=True)
    
    image.save(output_path, format='PNG', optimize=True, quality=95)
    
    print(f"✅ Cover image generated: {output_path}")
    return output_path


if __name__ == "__main__":
    print("🎨 BulkForm Blog Cover Generator")
    print("=" * 50)
    print()
    
    # Get text from user
    title = input("Enter blog title/summary (use \\n for manual line breaks): ").strip()
    
    if not title:
        print("❌ Error: Title cannot be empty")
        exit(1)
    
    # Replace literal \n with actual newlines
    title = title.replace('\\n', '\n')
    
    try:
        # Generate the cover
        output_path = generate_cover_image(title)
        print()
        print(f"📁 Saved to: {output_path}")
        print("🎉 Done!")
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        print()
        print("💡 Tips:")
        print("   - Use \\n to manually control line breaks")
        print("   - Max 4 lines")
        print("   - Each line max 40 characters")
        print()
        print("   Example: One mistake could cost\\nsomeone their life.\\n- Immigration Lawyer, 2026")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")