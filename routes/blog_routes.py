from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from models.blog_models import (
    BlogCreate, 
    BlogUpdate, 
    BlogResponse, 
    BlogListItem,
    BlogViewIncrement
)
from services.blog_service import BlogService
from services.auth import get_current_user


router = APIRouter(prefix="/api/blogs", tags=["blogs"])


def get_blog_service() -> BlogService:
    """Dependency to get blog service instance"""
    return BlogService()


def is_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Check if user is admin by querying the admins table.
    Uses the Supabase is_current_user_admin() function.
    """
    blog_service = BlogService()
    
    try:
        # Use Supabase RPC to call is_current_user_admin() function
        result = blog_service.supabase.rpc('is_current_user_admin').execute()
        
        # Check if the function returned True
        is_admin_user = result.data if result.data is not None else False
        
        if not is_admin_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required. Only admins can create blogs."
            )
        
        return current_user
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Fallback: Query admins table directly if RPC fails
        try:
            admin_check = blog_service.supabase.table('admins').select('user_id').eq('user_id', current_user['id']).execute()
            
            if not admin_check.data:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin access required. Only admins can create blogs."
                )
            
            return current_user
        except HTTPException:
            raise
        except Exception as fallback_error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Admin verification failed: {str(fallback_error)}"
            )


@router.post("/", response_model=BlogResponse, status_code=status.HTTP_201_CREATED)
async def create_blog(
    blog_data: BlogCreate,
    current_user: dict = Depends(is_admin),
    blog_service: BlogService = Depends(get_blog_service)
):
    """
    Create a new blog post (admin only).
    Auto-generates slug and cover image.
    """
    try:
        blog = blog_service.create_blog(
            blog_data=blog_data.dict(),
            author_id=current_user['id']
        )
        return blog
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create blog: {str(e)}"
        )


@router.get("/", response_model=List[BlogListItem])
async def list_blogs(
    published_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    blog_service: BlogService = Depends(get_blog_service)
):
    """
    List blog posts.
    - Public (unauthenticated) users see only published & active blogs
    - Authenticated users can see all their blogs (including drafts)
    """
    try:
        # Always show published blogs for public access
        blogs = blog_service.list_published_blogs(limit=limit, offset=offset)
        return blogs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch blogs: {str(e)}"
        )


@router.get("/{slug}", response_model=BlogResponse)
async def get_blog(
    slug: str,
    blog_service: BlogService = Depends(get_blog_service)
):
    """
    Get a single blog post by slug.
    Returns full content including markdown.
    """
    blog = blog_service.get_blog_by_slug(slug)
    
    if not blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog post not found"
        )
    
    # Only return published AND active blogs to non-authenticated users
    if not blog['published'] or not blog['is_active']:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog post not found"
        )
    
    return blog


@router.put("/{blog_id}", response_model=BlogResponse)
async def update_blog(
    blog_id: str,
    blog_data: BlogUpdate,
    current_user: dict = Depends(get_current_user),
    blog_service: BlogService = Depends(get_blog_service)
):
    """
    Update an existing blog post.
    Only the author can update their blog.
    """
    # Check if blog exists and user is the author
    existing_blog = blog_service.get_blog_by_id(blog_id)
    
    if not existing_blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog post not found"
        )
    
    if existing_blog['author_id'] != current_user['id']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own blog posts"
        )
    
    try:
        # Filter out None values
        update_dict = {k: v for k, v in blog_data.dict().items() if v is not None}
        
        updated_blog = blog_service.update_blog(blog_id, update_dict)
        return updated_blog
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update blog: {str(e)}"
        )


@router.delete("/{blog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog(
    blog_id: str,
    current_user: dict = Depends(get_current_user),
    blog_service: BlogService = Depends(get_blog_service)
):
    """
    Soft delete a blog post (sets is_active = false).
    Only the author can delete their blog.
    """
    # Check if blog exists and user is the author
    existing_blog = blog_service.get_blog_by_id(blog_id)
    
    if not existing_blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog post not found"
        )
    
    if existing_blog['author_id'] != current_user['id']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own blog posts"
        )
    
    try:
        blog_service.delete_blog(blog_id)
        return None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete blog: {str(e)}"
        )


@router.post("/{blog_id}/restore", response_model=BlogResponse)
async def restore_blog(
    blog_id: str,
    current_user: dict = Depends(get_current_user),
    blog_service: BlogService = Depends(get_blog_service)
):
    """
    Restore a soft-deleted blog (sets is_active = true).
    Only the author can restore their blog.
    """
    existing_blog = blog_service.get_blog_by_id(blog_id)
    
    if not existing_blog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog post not found"
        )
    
    if existing_blog['author_id'] != current_user['id']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only restore your own blog posts"
        )
    
    try:
        restored_blog = blog_service.restore_blog(blog_id)
        return restored_blog
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore blog: {str(e)}"
        )


@router.post("/{blog_id}/view", response_model=BlogResponse)
async def increment_view_count(
    blog_id: str,
    blog_service: BlogService = Depends(get_blog_service)
):
    """
    Increment view count for a blog post.
    Called when someone views the blog detail page.
    """
    try:
        updated_blog = blog_service.increment_view_count(blog_id)
        if not updated_blog:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Blog post not found"
            )
        return updated_blog
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to increment view count: {str(e)}"
        )