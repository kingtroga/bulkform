"""
Template Service
Handles CRUD operations for PDF form templates

Templates allow users to:
1. Define field coordinates once (e.g., I-485 form)
2. Reuse for multiple clients
3. Save massive time on repetitive forms
"""
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime
from services.supabase_client import get_supabase


class TemplateService:
    """Service for managing PDF form templates"""
    
    def __init__(self):
        """Initialize template service with Supabase client"""
        self.supabase = get_supabase()
        self.table_name = "pdf_templates"
    
    
    def create_template(
        self,
        user_id: str,
        name: str,
        pdf_url: str,
        field_mappings: Dict[str, Any],
        description: Optional[str] = None
    ) -> str:
        """
        Create a new PDF template
        
        Args:
            user_id: UUID of the user creating template
            name: Template name (e.g., "I-485 Form")
            pdf_url: URL to the blank PDF form
            field_mappings: Dictionary of field names to coordinates
                Example: {
                    "first_name": {"page": 1, "x": 25, "y": 30, "size": 30, "font": "arial"},
                    "last_name": {"page": 1, "x": 25, "y": 35, "size": 30, "font": "arial"}
                }
            description: Optional description of the template
            
        Returns:
            UUID string of created template
            
        Raises:
            Exception: If creation fails
        """
        try:
            # Prepare data
            template_data = {
                "user_id": user_id,
                "name": name,
                "pdf_url": pdf_url,
                "field_mappings": field_mappings,
                "description": description
            }
            
            # Insert into database
            result = self.supabase.table(self.table_name).insert(template_data).execute()
            
            if not result.data:
                raise Exception("Failed to create template - no data returned")
            
            template_id = result.data[0]["id"]
            print(f"✅ Template created: {template_id} (name: {name})")
            
            return template_id
        
        except Exception as e:
            print(f"❌ Failed to create template: {str(e)}")
            raise Exception(f"Template creation failed: {str(e)}")
    
    
    def get_template(self, template_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific template by ID
        
        Args:
            template_id: UUID of template to retrieve
            user_id: UUID of user (for ownership verification)
            
        Returns:
            Template dict if found and owned by user, None otherwise
            
        Example return:
            {
                "id": "abc-123",
                "user_id": "user-456",
                "name": "I-485 Template",
                "pdf_url": "https://...",
                "field_mappings": {...},
                "created_at": "2025-11-02T10:00:00Z"
            }
        """
        try:
            # Query with ownership verification (RLS handles this too, but double-check)
            result = (
                self.supabase.table(self.table_name)
                .select("*")
                .eq("id", template_id)
                .or_(f"is_official.eq.true,user_id.eq.{user_id}")
                .execute()
            )
            
            if not result.data:
                print(f"⚠️  Template not found or unauthorized: {template_id}")
                return None
            
            template = result.data[0]
            print(f"✅ Template retrieved: {template['name']}")
            
            return template
        
        except Exception as e:
            print(f"❌ Failed to get template: {str(e)}")
            return None
    
    
    def list_templates(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all templates for a user
        
        Args:
            user_id: UUID of user
            limit: Max number of templates to return (default 100)
            offset: Number of templates to skip (for pagination)
            
        Returns:
            List of template dictionaries, newest first
        """
        try:
            # Query user's templates, ordered by newest first
            result = self.supabase.table(self.table_name).select("*").eq(
                "user_id", user_id
            ).order(
                "created_at", desc=True
            ).limit(limit).offset(offset).execute()
            
            templates = result.data if result.data else []
            
            print(f"✅ Retrieved {len(templates)} templates for user")
            
            return templates
        
        except Exception as e:
            print(f"❌ Failed to list templates: {str(e)}")
            return []
    
    
    def update_template(
        self,
        template_id: str,
        user_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update an existing template
        
        Args:
            template_id: UUID of template to update
            user_id: UUID of user (for ownership verification)
            updates: Dictionary of fields to update
                Allowed fields: name, description, pdf_url, field_mappings
                
        Returns:
            True if successful, False otherwise
            
        Example:
            update_template(
                "abc-123",
                "user-456",
                {"name": "Updated I-485", "description": "New version"}
            )
        """
        try:
            # Verify ownership first
            existing = self.get_template(template_id, user_id)
            if not existing:
                print(f"⚠️  Cannot update - template not found or unauthorized")
                return False
            
            # Filter allowed update fields
            allowed_fields = {"name", "description", "pdf_url", "field_mappings"}
            filtered_updates = {
                key: value for key, value in updates.items()
                if key in allowed_fields
            }
            
            if not filtered_updates:
                print(f"⚠️  No valid fields to update")
                return False
            
            # Update in database
            result = self.supabase.table(self.table_name).update(
                filtered_updates
            ).eq(
                "id", template_id
            ).eq(
                "user_id", user_id
            ).execute()
            
            if not result.data:
                print(f"❌ Update failed - no data returned")
                return False
            
            print(f"✅ Template updated: {template_id}")
            return True
        
        except Exception as e:
            print(f"❌ Failed to update template: {str(e)}")
            return False
    
    
    def delete_template(self, template_id: str, user_id: str) -> bool:
        """
        Delete a template
        
        Args:
            template_id: UUID of template to delete
            user_id: UUID of user (for ownership verification)
            
        Returns:
            True if successful, False otherwise
            
        Note:
            This will also cascade delete any batch_jobs that reference this template
            (set to NULL via ON DELETE SET NULL in migration)
        """
        try:
            # Verify ownership first
            existing = self.get_template(template_id, user_id)
            if not existing:
                print(f"⚠️  Cannot delete - template not found or unauthorized")
                return False
            
            # Delete from database
            result = self.supabase.table(self.table_name).delete().eq(
                "id", template_id
            ).eq(
                "user_id", user_id
            ).execute()
            
            # Note: Supabase delete() returns empty data on success
            # So we can't check result.data, just assume success if no exception
            
            print(f"✅ Template deleted: {template_id}")
            return True
        
        except Exception as e:
            print(f"❌ Failed to delete template: {str(e)}")
            return False
    
    
    def get_template_by_name(
        self,
        user_id: str,
        name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a template by name (case-insensitive)
        
        Args:
            user_id: UUID of user
            name: Name of template to find
            
        Returns:
            Template dict if found, None otherwise
            
        Useful for:
            - Checking if template name already exists
            - Quick lookup by name
        """
        try:
            result = (
                self.supabase.table(self.table_name)
                .select("*")
                .or_(
                    f"and(is_official.eq.true,name.ilike.*{name}*),and(user_id.eq.{user_id},name.ilike.*{name}*)"
                )
                .execute()
            )

            
            if not result.data:
                return None
            
            return result.data[0]
        
        except Exception as e:
            print(f"❌ Failed to get template by name: {str(e)}")
            return None
    
    
    def count_user_templates(self, user_id: str) -> int:
        """
        Count total templates for a user
        
        Args:
            user_id: UUID of user
            
        Returns:
            Number of templates
        """
        try:
            result = self.supabase.table(self.table_name).select(
                "id", count="exact"
            ).eq("user_id", user_id).execute()
            
            return result.count if result.count else 0
        
        except Exception as e:
            print(f"❌ Failed to count templates: {str(e)}")
            return 0
    
    
    def validate_field_mappings(self, field_mappings: Dict[str, Any]) -> bool:
        """
        Validate that field mappings have correct structure
        
        Args:
            field_mappings: Dictionary to validate
            
        Returns:
            True if valid, False otherwise
            
        Expected structure:
            {
                "field_name": {
                    "page": 1,          # Required: page number
                    "x": 25,            # Required: x coordinate
                    "y": 30,            # Required: y coordinate
                    "size": 30,         # Optional: font size
                    "font": "arial",    # Optional: font name
                    "align": "top"      # Optional: alignment
                }
            }
        """
        if not isinstance(field_mappings, dict):
            print(f"❌ field_mappings must be a dictionary")
            return False
        
        if len(field_mappings) == 0:
            print(f"❌ field_mappings cannot be empty")
            return False
        
        for field_name, mapping in field_mappings.items():
            # Check required fields
            if not isinstance(mapping, dict):
                print(f"❌ Mapping for '{field_name}' must be a dictionary")
                return False
            
            required = ["page", "x", "y"]
            for req in required:
                if req not in mapping:
                    print(f"❌ Mapping for '{field_name}' missing required field: {req}")
                    return False
            
            # Validate types
            if not isinstance(mapping["page"], int) or mapping["page"] < 1:
                print(f"❌ '{field_name}' page must be integer >= 1")
                return False
            
            if not isinstance(mapping["x"], (int, float)):
                print(f"❌ '{field_name}' x must be a number")
                return False
            
            if not isinstance(mapping["y"], (int, float)):
                print(f"❌ '{field_name}' y must be a number")
                return False
        
        print(f"✅ field_mappings valid ({len(field_mappings)} fields)")
        return True
    
    
    # ========================================================================
    # OFFICIAL TEMPLATES - Created by BulkForm (YOU!)
    # ========================================================================
    
    def create_official_template(
        self,
        user_id: str,
        name: str,
        pdf_url: str,
        field_mappings: Dict[str, Any],
        official_form_id: str,
        category: str = "immigration",
        description: Optional[str] = None,
        price: float = 0.00
    ) -> str:
        """
        Create an official BulkForm template
        
        🔒 SECURITY: Only admins can create official templates!
        This method checks if user_id is in the admins table.
        
        Args:
            user_id: Your admin user_id
            name: Template name (e.g., "USCIS Form I-485")
            pdf_url: URL to blank PDF
            field_mappings: Field coordinate mappings
            official_form_id: Form identifier (e.g., "i-485")
            category: Template category (default: "immigration")
            description: Optional description
            price: Price in dollars (default: 0.00 = free)
            
        Returns:
            UUID string of created official template
            
        Raises:
            Exception: If user is not an admin
            
        Example:
            template_id = service.create_official_template(
                user_id="your-admin-id",
                name="USCIS Form I-485",
                pdf_url="https://uscis.gov/i-485.pdf",
                field_mappings={...},
                official_form_id="i-485"
            )
        """
        try:
            # 🔒 SECURITY CHECK: Verify user is admin
            if not self.is_admin(user_id):
                raise Exception(
                    f"Permission denied: User {user_id} is not an admin. "
                    "Only admins can create official templates."
                )
            
            # Validate field mappings
            if not self.validate_field_mappings(field_mappings):
                raise Exception("Invalid field mappings")
            
            # Prepare data with official flags
            template_data = {
                "user_id": user_id,
                "name": name,
                "pdf_url": pdf_url,
                "field_mappings": field_mappings,
                "description": description,
                "is_official": True,
                "official_form_id": official_form_id.lower(),
                "category": category,
                "price": price,
                "downloads": 0
            }
            
            # Insert using service role (bypasses RLS)
            result = self.supabase.table(self.table_name).insert(template_data).execute()
            
            if not result.data:
                raise Exception("Failed to create official template - no data returned")
            
            template_id = result.data[0]["id"]
            print(f"⭐ Official template created by admin: {template_id} (form: {official_form_id})")
            
            return template_id
        
        except Exception as e:
            print(f"❌ Failed to create official template: {str(e)}")
            raise Exception(f"Official template creation failed: {str(e)}")
    
    
    def is_admin(self, user_id: str) -> bool:
        """
        Check if user is an admin
        
        Args:
            user_id: UUID of user to check
            
        Returns:
            True if user is admin, False otherwise
            
        Uses the admins table created by migration 005
        """
        try:
            result = self.supabase.table("admins").select("user_id").eq(
                "user_id", user_id
            ).execute()
            
            is_admin = len(result.data) > 0
            
            if is_admin:
                print(f"✅ User {user_id[:8]}... is admin")
            else:
                print(f"❌ User {user_id[:8]}... is NOT admin")
            
            return is_admin
        
        except Exception as e:
            print(f"⚠️  Admin check failed: {str(e)}")
            return False
    
    
    def list_admins(self) -> List[Dict[str, Any]]:
        """
        List all admin users (only callable by admins)
        
        Returns:
            List of admin user records
        """
        try:
            result = self.supabase.table("admins").select("*").execute()
            
            admins = result.data if result.data else []
            print(f"✅ Found {len(admins)} admin(s)")
            
            return admins
        
        except Exception as e:
            print(f"❌ Failed to list admins: {str(e)}")
            return []
    
    
    def list_official_templates(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List official BulkForm templates (publicly available)
        
        Args:
            category: Filter by category (e.g., "immigration", "tax", "hr")
            limit: Max number to return
            
        Returns:
            List of official templates
            
        Use case:
            Show all pre-made templates in marketplace/library
        """
        try:
            query = self.supabase.table(self.table_name).select("*").eq(
                "is_official", True
            )
            
            if category:
                query = query.eq("category", category)
            
            result = query.order("downloads", desc=True).limit(limit).execute()
            
            templates = result.data if result.data else []
            
            print(f"✅ Retrieved {len(templates)} official templates")
            
            return templates
        
        except Exception as e:
            print(f"❌ Failed to list official templates: {str(e)}")
            return []
    
    
    def get_official_template_by_form_id(
        self,
        form_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get official template by form ID (e.g., "i-485")
        
        Args:
            form_id: Official form identifier (lowercase)
            
        Returns:
            Template dict if found
            
        Use case:
            Quick access to common forms
        """
        try:
            result = self.supabase.table(self.table_name).select("*").eq(
                "is_official", True
            ).eq(
                "official_form_id", form_id.lower()
            ).execute()
            
            if not result.data:
                print(f"⚠️  Official template not found: {form_id}")
                return None
            
            return result.data[0]
        
        except Exception as e:
            print(f"❌ Failed to get official template: {str(e)}")
            return None
    
    
    def get_template_categories(self) -> List[Dict[str, Any]]:
        """
        Get all available template categories with counts
        
        Returns:
            List of categories with template counts
            
        Example return:
            [
                {"category": "immigration", "count": 15},
                {"category": "tax", "count": 8},
                {"category": "hr", "count": 5}
            ]
        """
        try:
            # This requires a custom query
            result = self.supabase.table(self.table_name).select(
                "category"
            ).eq("is_official", True).execute()
            
            if not result.data:
                return []
            
            # Count categories manually (Supabase doesn't support GROUP BY easily)
            category_counts = {}
            for row in result.data:
                cat = row.get("category", "uncategorized")
                category_counts[cat] = category_counts.get(cat, 0) + 1
            
            categories = [
                {"category": cat, "count": count}
                for cat, count in category_counts.items()
            ]
            
            print(f"✅ Found {len(categories)} template categories")
            
            return categories
        
        except Exception as e:
            print(f"❌ Failed to get categories: {str(e)}")
            return []
    
    
    def increment_template_downloads(self, template_id: str) -> bool:
        """
        Increment download count for official template
        
        Args:
            template_id: UUID of template
            
        Returns:
            True if successful
            
        Use case:
            Track popularity of official templates
        """
        try:
            # Get current downloads
            template = self.supabase.table(self.table_name).select(
                "downloads"
            ).eq("id", template_id).eq("is_official", True).execute()
            
            if not template.data:
                return False
            
            current = template.data[0].get("downloads", 0)
            
            # Increment
            self.supabase.table(self.table_name).update({
                "downloads": current + 1
            }).eq("id", template_id).execute()
            
            print(f"✅ Downloads incremented: {template_id}")
            return True
        
        except Exception as e:
            print(f"❌ Failed to increment downloads: {str(e)}")
            return False
    
    
    def list_all_templates(
        self,
        user_id: str,
        include_official: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get both official AND user's custom templates
        
        Args:
            user_id: UUID of user
            include_official: Whether to include official templates
            
        Returns:
            Dictionary with "official" and "custom" template lists
            
        Example return:
            {
                "official": [
                    {"id": "...", "name": "I-485", "is_official": True},
                    {"id": "...", "name": "I-765", "is_official": True}
                ],
                "custom": [
                    {"id": "...", "name": "My Custom Form", "is_official": False}
                ]
            }
        """
        result = {
            "official": [],
            "custom": []
        }
        
        # Get user's custom templates
        result["custom"] = self.list_templates(user_id)
        
        # Get official templates if requested
        if include_official:
            result["official"] = self.list_official_templates()
        
        total = len(result["official"]) + len(result["custom"])
        print(f"✅ Retrieved {total} total templates ({len(result['official'])} official, {len(result['custom'])} custom)")
        
        return result


# ============================================================================
# CONVENIENCE FUNCTION - Easy import
# ============================================================================

def get_template_service() -> TemplateService:
    """Get template service instance"""
    return TemplateService()