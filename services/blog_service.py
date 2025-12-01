from PIL import Image, ImageDraw, ImageFont
import io
import re
import uuid
from typing import Optional, List
from services.supabase_client import get_supabase


class BlogService:
    def __init__(self):
        self.supabase = get_supabase()
        self.storage_bucket = "blog-covers"
    
    def generate_slug(self, title: str) -> str:
        """Generate URL-friendly slug from title"""
        slug = title.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = slug.strip('-')
        
        # Ensure uniqueness by checking database
        base_slug = slug
        counter = 1
        while self._slug_exists(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        return slug
    
    def _slug_exists(self, slug: str) -> bool:
        """Check if slug already exists in database"""
        result = self.supabase.table('blogs').select('id').eq('slug', slug).execute()
        return len(result.data) > 0
    
    def generate_cover_image(self, title: str, blog_id: str, base_image_path: str = "images/blog-cover-base.jpg") -> str:
        """
        Generate cover image by overlaying title on existing base template.
        Uses your uploaded base image instead of generating from scratch.
        Returns Supabase storage URL.
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
        wrapped_title = self._wrap_text(title, max_chars_per_line=28)
        
        # Load Inter font
        try:
            font_title = ImageFont.truetype("fonts/inter.ttf", 72)
        except:
            try:
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/inter/Inter-Bold.ttf", 72)
            except:
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        
        # Fixed left margin position
        text_x = 150
        text_y = 130
        
        # Add text shadow for better readability
        shadow_offset = 4
        draw.text((text_x + shadow_offset, text_y + shadow_offset), 
                wrapped_title, font=font_title, fill=(200, 205, 210, 90))
        
        # Main title text in #0058FF
        draw.text((text_x, text_y), wrapped_title, font=font_title, fill=(0, 88, 255))
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        image.save(buffer, format='PNG', optimize=True, quality=95)
        buffer.seek(0)
        
        # Upload to Supabase Storage
        file_name = f"{blog_id}.png"
        file_path = f"covers/{file_name}"
        
        self.supabase.storage.from_(self.storage_bucket).upload(
            path=file_path,
            file=buffer.getvalue(),
            file_options={"content-type": "image/png"}
        )
        
        # Get public URL
        public_url = self.supabase.storage.from_(self.storage_bucket).get_public_url(file_path)
        
        return public_url

    def _wrap_text(self, text: str, max_chars_per_line: int = 28) -> str:
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
                raise ValueError(f"Line 1 has {line1_word_count} words, max is 4")
            
            if line2_word_count > 5:
                raise ValueError(f"Line 2 has {line2_word_count} words, max is 5")
        
        # VALIDATION: Max chars per line
        for i, line in enumerate(lines, 1):
            if len(line) > max_chars_per_line:
                raise ValueError(f"Line {i} too long! '{line}' ({len(line)} chars, max {max_chars_per_line})")
        
        # VALIDATION: Only 2 lines allowed
        if len(lines) > 2:
            raise ValueError(f"Title too long! Got {len(lines)} lines, max is 2")
        
        return '\n'.join(lines)
    
    def upload_custom_cover(self, image_data: bytes, blog_id: str) -> str:
        """Upload custom user-provided cover image"""
        file_name = f"{blog_id}-custom.png"
        file_path = f"covers/{file_name}"
        
        self.supabase.storage.from_(self.storage_bucket).upload(
            path=file_path,
            file=image_data,
            file_options={"content-type": "image/png", "upsert": "true"}
        )
        
        public_url = self.supabase.storage.from_(self.storage_bucket).get_public_url(file_path)
        return public_url
    
    def create_blog(self, blog_data: dict, author_id: str) -> dict:
        """Create new blog post with auto-generated cover"""
        # Generate slug
        slug = self.generate_slug(blog_data['title'])
        
        # Create blog record
        blog_id = str(uuid.uuid4())
        
        blog_record = {
            'id': blog_id,
            'title': blog_data['title'],
            'slug': slug,
            'summary': blog_data['summary'],
            'content': blog_data['content'],
            'author_id': author_id,
            'youtube_url': blog_data.get('youtube_url'),
            'published': blog_data.get('published', False),
            'view_count': 0,
            'is_active': True,
            'cover_image_url': ''  # Placeholder, will update after upload
        }
        
        # Insert into database FIRST
        result = self.supabase.table('blogs').insert(blog_record).execute()
        
        # Generate and upload cover image AFTER database insert succeeds
        try:
            cover_url = self.generate_cover_image(blog_data['summary'], blog_id)
            
            # Update the blog record with cover image URL
            self.supabase.table('blogs').update({'cover_image_url': cover_url}).eq('id', blog_id).execute()
            
            # Update the returned result
            result.data[0]['cover_image_url'] = cover_url
        except Exception as e:
            # If cover generation fails, blog still exists but without cover
            print(f"Warning: Cover image generation failed: {e}")
        
        return result.data[0]

    def get_blog_by_slug(self, slug: str) -> Optional[dict]:
        """Retrieve blog post by slug"""
        result = self.supabase.table('blogs').select('*').eq('slug', slug).execute()
        
        if result.data:
            return result.data[0]
        return None
    
    def get_blog_by_id(self, blog_id: str) -> Optional[dict]:
        """Retrieve blog post by ID"""
        result = self.supabase.table('blogs').select('*').eq('id', blog_id).execute()
        
        if result.data:
            return result.data[0]
        return None
    
    def list_published_blogs(self, limit: int = 50, offset: int = 0) -> List[dict]:
        """List all published AND active blogs (for public view)"""
        result = (
            self.supabase.table('blogs')
            .select('id, title, slug, summary, content, author_id, youtube_url, cover_image_url, created_at, published, view_count, is_active')
            .eq('published', True)
            .eq('is_active', True)
            .order('created_at', desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        
        return result.data
    
    def list_all_blogs(self, author_id: Optional[str] = None, include_inactive: bool = False, limit: int = 50, offset: int = 0) -> List[dict]:
        """
        List all blogs (admin view, includes drafts).
        Set include_inactive=True to see soft-deleted blogs.
        """
        query = (
            self.supabase.table('blogs')
            .select('id, title, slug, summary, author_id, youtube_url, cover_image_url, created_at, published, view_count, is_active')
            .order('created_at', desc=True)
            .range(offset, offset + limit - 1)
        )
        
        if author_id:
            query = query.eq('author_id', author_id)
        
        if not include_inactive:
            query = query.eq('is_active', True)
        
        result = query.execute()
        return result.data
    
    def update_blog(self, blog_id: str, update_data: dict) -> dict:
        """Update existing blog post"""
        # If title changed, regenerate slug
        if 'title' in update_data:
            current_blog = self.get_blog_by_id(blog_id)
            if current_blog and update_data['title'] != current_blog['title']:
                update_data['slug'] = self.generate_slug(update_data['title'])
                # Regenerate cover image with new title
                update_data['cover_image_url'] = self.generate_cover_image(
                    update_data['title'], blog_id
                )
        
        # Handle custom cover image upload
        if 'custom_cover_image' in update_data and update_data['custom_cover_image']:
            # Assuming base64 or bytes provided
            custom_url = self.upload_custom_cover(update_data['custom_cover_image'], blog_id)
            update_data['cover_image_url'] = custom_url
            del update_data['custom_cover_image']
        
        result = (
            self.supabase.table('blogs')
            .update(update_data)
            .eq('id', blog_id)
            .execute()
        )
        
        return result.data[0]
    
    def delete_blog(self, blog_id: str) -> bool:
        """
        Soft delete blog post (sets is_active = false).
        Cover images remain in storage for potential restoration.
        """
        self.supabase.table('blogs').update({'is_active': False}).eq('id', blog_id).execute()
        return True
    
    def hard_delete_blog(self, blog_id: str) -> bool:
        """
        Permanently delete blog post and associated cover image.
        Use with caution - this cannot be undone!
        """
        # Delete cover image from storage
        try:
            self.supabase.storage.from_(self.storage_bucket).remove([f"covers/{blog_id}.png"])
            self.supabase.storage.from_(self.storage_bucket).remove([f"covers/{blog_id}-custom.png"])
        except:
            pass  # Image might not exist
        
        # Delete blog record
        self.supabase.table('blogs').delete().eq('id', blog_id).execute()
        return True
    
    def restore_blog(self, blog_id: str) -> dict:
        """Restore a soft-deleted blog (sets is_active = true)"""
        result = (
            self.supabase.table('blogs')
            .update({'is_active': True})
            .eq('id', blog_id)
            .execute()
        )
        return result.data[0] if result.data else {}
    
    def increment_view_count(self, blog_id: str) -> dict:
        """Increment view count for a blog post"""
        # Use Supabase RPC or manual increment
        current_blog = self.get_blog_by_id(blog_id)
        if current_blog:
            new_count = current_blog['view_count'] + 1
            result = (
                self.supabase.table('blogs')
                .update({'view_count': new_count})
                .eq('id', blog_id)
                .execute()
            )
            return result.data[0]
        return {}