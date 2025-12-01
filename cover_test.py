from PIL import Image, ImageDraw, ImageFont
import os

def wrap_text(text, max_chars_per_line=28):
    """
    Wrap text with specific word count rules:
    - Line 1: Max 4 words
    - Line 2: Max 5 words (gets remaining words)
    - If last word on line 1 is >6 chars, move it to line 2
    """
    words = text.split()
    
    # Force split if more than 4 words
    if len(words) <= 4:
        # Single line case
        lines = [' '.join(words)]
    else:
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
    
    # VALIDATION: Check word count
    if len(lines) == 2:
        line1_word_count = len(lines[0].split())
        line2_word_count = len(lines[1].split())
        
        if line1_word_count > 4:
            raise ValueError(f"❌ Line 1 has {line1_word_count} words, max is 4")
        
        if line2_word_count > 5:
            raise ValueError(f"❌ Line 2 has {line2_word_count} words, max is 5")
    
    # VALIDATION: Max chars per line
    for i, line in enumerate(lines, 1):
        if len(line) > max_chars_per_line:
            raise ValueError(f"❌ Line {i} too long! '{line}' ({len(line)} chars, max {max_chars_per_line})")
    
    # VALIDATION: Only 2 lines allowed
    if len(lines) > 2:
        raise ValueError(f"❌ Title too long! Got {len(lines)} lines, max is 2")
    
    return '\n'.join(lines)


def generate_blog_cover(title, base_image_path, font_path, output_path):
    """
    Overlay title text on base cover image
    """
    # Load base image
    if not os.path.exists(base_image_path):
        print(f"❌ Error: Base image not found at {base_image_path}")
        return False
    
    image = Image.open(base_image_path)
    print(f"✅ Loaded base image: {image.size}")
    
    # Resize to standard OG dimensions if needed
    if image.size != (1200, 630):
        image = image.resize((1200, 630), Image.Resampling.LANCZOS)
        print(f"✅ Resized to 1200x630")
    
    draw = ImageDraw.Draw(image)
    
    # Wrap title text
    wrapped_title = wrap_text(title, max_chars_per_line=28)
    lines = wrapped_title.split('\n')
    print(f"✅ Wrapped title into {len(lines)} line(s):")
    for i, line in enumerate(lines, 1):
        word_count = len(line.split())
        print(f"   Line {i}: '{line}' ({len(line)} chars, {word_count} words)")
    print()
    
    # Load font
    if not os.path.exists(font_path):
        print(f"❌ Error: Font not found at {font_path}")
        return False
    
    try:
        font = ImageFont.truetype(font_path, 72)
        print(f"✅ Loaded font: {font_path} at size 72")
    except Exception as e:
        print(f"❌ Error loading font: {e}")
        return False
    
    # Fixed left margin position
    text_x = 150
    text_y = 130
    
    print(f"✅ Text position: ({text_x}, {text_y})")
    
    # Draw text shadow
    shadow_offset = 4
    draw.text(
        (text_x + shadow_offset, text_y + shadow_offset), 
        wrapped_title, 
        font=font, 
        fill=(0, 0, 0, 150)
    )
    
    # Draw main title text in white
    draw.text((text_x, text_y), wrapped_title, font=font, fill='white')
    print(f"✅ Drew text on image")
    
    # Save output
    image.save(output_path, format='PNG', optimize=True, quality=95)
    print(f"✅ Saved to: {output_path}")
    
    return True


if __name__ == "__main__":
    # Configuration
    TITLE = "Automate Your PDF Workflow Today"
    BASE_IMAGE = "images/cover.jpg"
    FONT_FILE = "fonts/inter.ttf"
    OUTPUT_FILE = "output_cover.png"
    
    print("=" * 60)
    print("🎨 BulkForm Blog Cover Generator")
    print("=" * 60)
    print(f"Title: {TITLE}")
    print(f"Base: {BASE_IMAGE}")
    print(f"Font: {FONT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 60)
    print()
    
    # Generate cover
    success = generate_blog_cover(
        title=TITLE,
        base_image_path=BASE_IMAGE,
        font_path=FONT_FILE,
        output_path=OUTPUT_FILE
    )
    
    if success:
        print()
        print("=" * 60)
        print("✅ SUCCESS! Check output_cover.png")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("❌ FAILED - See errors above")
        print("=" * 60)