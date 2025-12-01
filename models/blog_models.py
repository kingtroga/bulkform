from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re


class BlogCreate(BaseModel):
    """Schema for creating a new blog post"""
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    youtube_url: Optional[str] = None
    published: bool = False

    @field_validator('youtube_url')
    @classmethod
    def validate_youtube_url(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip():
            # Accept various YouTube URL formats
            youtube_pattern = r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+'
            if not re.match(youtube_pattern, v):
                raise ValueError('Invalid YouTube URL format')
        return v


class BlogUpdate(BaseModel):
    """Schema for updating an existing blog post"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    summary: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = None
    youtube_url: Optional[str] = None
    published: Optional[bool] = None
    custom_cover_image: Optional[str] = None  # Base64 or URL

    @field_validator('youtube_url')
    @classmethod
    def validate_youtube_url(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip():
            youtube_pattern = r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+'
            if not re.match(youtube_pattern, v):
                raise ValueError('Invalid YouTube URL format')
        return v


class BlogResponse(BaseModel):
    """Schema for blog post response"""
    id: str
    title: str
    slug: str
    summary: str
    content: str
    author_id: Optional[str]
    youtube_url: Optional[str]
    cover_image_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    published: bool
    view_count: int
    is_active: bool

    class Config:
        from_attributes = True


class BlogListItem(BaseModel):
    """Lightweight schema for blog listing (without full content)"""
    id: str
    title: str
    slug: str
    summary: str
    content: str 
    author_id: Optional[str]
    youtube_url: Optional[str]
    cover_image_url: Optional[str]
    created_at: datetime
    published: bool
    view_count: int
    is_active: bool

    class Config:
        from_attributes = True


class BlogViewIncrement(BaseModel):
    """Schema for incrementing view count"""
    blog_id: str