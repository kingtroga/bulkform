from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class ProfileBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    
class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None

class ProfileResponse(ProfileBase):
    id: str
    role: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True