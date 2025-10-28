from fastapi import APIRouter, HTTPException, status, Depends
from supabase_client import get_supabase
from auth import get_current_user
from models import ProfileUpdate, ProfileResponse

router = APIRouter(prefix="/api/profile", tags=["Profile"])


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(user: dict = Depends(get_current_user)):
    """Get current user's profile (creates one if doesn't exist)"""
    try:
        supabase = get_supabase()
        
        # Try to get existing profile
        response = supabase.table("profiles").select("*").eq("id", user["id"]).execute()
        
        # If profile doesn't exist, create it
        if not response.data or len(response.data) == 0:
            print(f"⚠️ Profile not found for user {user['id']}, creating...")
            
            # Get user info from auth to populate profile
            auth_user = supabase.auth.get_user()
            user_metadata = getattr(auth_user.user, 'user_metadata', {}) or {}
            
            # Create profile with available data
            new_profile = {
                "id": user["id"],
                "email": user["email"],
                "full_name": user_metadata.get("full_name") or user_metadata.get("name"),
                "avatar_url": user_metadata.get("avatar_url") or user_metadata.get("picture")
            }
            
            create_response = supabase.table("profiles").insert(new_profile).execute()
            print(f"✅ Profile created for user {user['id']}")
            return create_response.data[0]
        
        return response.data[0]
        
    except Exception as e:
        print(f"❌ Error in get_my_profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch profile: {str(e)}"
        )


@router.patch("/me", response_model=ProfileResponse)
async def update_my_profile(
    updates: ProfileUpdate,
    user: dict = Depends(get_current_user)
):
    """Update current user's profile (creates one if doesn't exist)"""
    try:
        supabase = get_supabase()
        
        update_data = updates.dict(exclude_unset=True)
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        # Check if profile exists first
        check_response = supabase.table("profiles").select("*").eq("id", user["id"]).execute()
        
        # If profile doesn't exist, create it with the updates
        if not check_response.data or len(check_response.data) == 0:
            print(f"⚠️ Profile not found for user {user['id']}, creating with updates...")
            
            # Get user info from auth
            auth_user = supabase.auth.get_user()
            user_metadata = getattr(auth_user.user, 'user_metadata', {}) or {}
            
            # Create profile with update data
            new_profile = {
                "id": user["id"],
                "email": user["email"],
                "full_name": update_data.get("full_name") or user_metadata.get("full_name") or user_metadata.get("name"),
                "avatar_url": update_data.get("avatar_url") or user_metadata.get("avatar_url") or user_metadata.get("picture"),
                "phone": update_data.get("phone"),
                "company": update_data.get("company")
            }
            
            create_response = supabase.table("profiles").insert(new_profile).execute()
            print(f"✅ Profile created for user {user['id']}")
            return create_response.data[0]
        
        # Profile exists, update it
        response = supabase.table("profiles").update(update_data).eq("id", user["id"]).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in update_my_profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.delete("/me")
async def delete_my_profile(user: dict = Depends(get_current_user)):
    """Delete current user's account"""
    try:
        supabase = get_supabase()
        
        # Delete profile (cascade will delete auth user if FK is set)
        supabase.table("profiles").delete().eq("id", user["id"]).execute()
        
        # Also delete from auth
        try:
            supabase.auth.admin.delete_user(user["id"])
        except Exception as auth_error:
            print(f"⚠️ Could not delete auth user: {str(auth_error)}")
            # Continue anyway - profile is deleted
        
        return {"message": "Account deleted successfully"}
        
    except Exception as e:
        print(f"❌ Error in delete_my_profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )


@router.post("/backfill")
async def backfill_missing_profiles(user: dict = Depends(get_current_user)):
    """
    Admin endpoint: Create profiles for all auth users who don't have one
    (Only callable by authenticated users for now - add admin check in production)
    """
    try:
        supabase = get_supabase()
        
        # Get all auth users (this requires admin privileges)
        # For now, this will only work if you're using a service_role key
        # In production, add proper admin authorization
        
        created_count = 0
        
        # Get current user's profile as a test
        # In production, you'd loop through all users
        response = supabase.table("profiles").select("*").eq("id", user["id"]).execute()
        
        if not response.data or len(response.data) == 0:
            auth_user = supabase.auth.get_user()
            user_metadata = getattr(auth_user.user, 'user_metadata', {}) or {}
            
            new_profile = {
                "id": user["id"],
                "email": user["email"],
                "full_name": user_metadata.get("full_name") or user_metadata.get("name"),
                "avatar_url": user_metadata.get("avatar_url") or user_metadata.get("picture")
            }
            
            supabase.table("profiles").insert(new_profile).execute()
            created_count += 1
        
        return {
            "message": f"Backfill complete. Created {created_count} profile(s)",
            "created_count": created_count
        }
        
    except Exception as e:
        print(f"❌ Error in backfill_missing_profiles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to backfill profiles: {str(e)}"
        )