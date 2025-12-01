from PIL import Image, ImageDraw, ImageFont
import os

def wrap_text(text, max_chars_per_line=28):
    """Wrap text to fit within image width"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        
        if len(test_line) <= max_chars_per_line:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    # VALIDATION RULE 1: Only 2 lines allowed
    if len(lines) > 2:
        raise ValueError(f"❌ Title too long! Got {len(lines)} lines, max is 2")
    
    # VALIDATION RULE 2: Max 28 chars per line
    for i, line in enumerate(lines, 1):
        if len(line) > max_chars_per_line:
            raise ValueError(f"❌ Line {i} too long! '{line}' ({len(line)} chars, max {max_chars_per_line})")
    
    # SMART WRAP: Balance lines better
    if len(lines) == 2:
        line1_words = lines[0].split()
        line2_words = lines[1].split()
        
        # Try moving last 1-2 words from line 1 to line 2 if it balances better
        for num_words_to_move in [2, 1]:
            if len(line1_words) > num_words_to_move:
                words_to_move = line1_words[-num_words_to_move:]
                new_line1 = ' '.join(line1_words[:-num_words_to_move])
                new_line2 = ' '.join(words_to_move + line2_words)
                
                # Check if both lines still fit
                if len(new_line1) <= max_chars_per_line and len(new_line2) <= max_chars_per_line:
                    # Check if this creates better balance (lines closer in length)
                    old_diff = abs(len(lines[0]) - len(lines[1]))
                    new_diff = abs(len(new_line1) - len(new_line2))
                    
                    if new_diff < old_diff:
                        lines[0] = new_line1
                        lines[1] = new_line2
                        break
    
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
    print(f"✅ Wrapped title:\n{wrapped_title}\n")
    
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
    TITLE = "BulkForm Guide for HR Teams"
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