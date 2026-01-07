"""
Template Service
Handles CRUD operations for PDF form templates

Templates allow users to:
1. Define field coordinates once (e.g., I-485 form)
2. Reuse for multiple clients
3. Save massive time on repetitive forms
"""
from typing import Optional, List, Dict, Any, Tuple
import uuid
from datetime import datetime
from services.supabase_client import get_supabase
from services.template_cache import cache_template, invalidate_template_cache, invalidate_user_templates
from datetime import datetime, timezone


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
        field_order: list = None,  
        description: Optional[str] = None,
        template_kind: str = "standard",         
        repeat_config: Optional[Dict[str, Any]] = None 
    ) -> str:
        """
        Create a new PDF template
        
        Args:
            user_id: UUID of the user creating template
            name: Template name (e.g., "I-485 Form")
            pdf_url: URL to the blank PDF form
            field_mappings: Dictionary of field names to coordinates
            field_order: List of field names in order (optional)
            description: Optional description of the template
            
        Returns:
            UUID string of created template
        """
        try:
            # If no field_order provided, extract from field_mappings keys
            if field_order is None:
                field_order = list(field_mappings.keys())
            
            # Prepare data
            template_data = {
                "user_id": user_id,
                "name": name,
                "pdf_url": pdf_url,
                "field_mappings": field_mappings,
                "field_order": field_order,
                "description": description,
                "template_kind": template_kind,      
                "repeat_config": repeat_config       
            }
            
            # Insert into database
            result = self.supabase.table(self.table_name).insert(template_data).execute()
            
            if not result.data:
                raise Exception("Failed to create template - no data returned")
            
            template_id = result.data[0]["id"]
            print(f"✅ Template created: {template_id} (name: {name}) with {len(field_order)} fields in order")
            
            return template_id
        
        except Exception as e:
            print(f"❌ Failed to create template: {str(e)}")
            raise Exception(f"Template creation failed: {str(e)}")
        
    @cache_template(ttl=3600)
    def get_template(self, template_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific template by ID (only if active).
        Return None if not found/unauthorized/inactive.
        """
        try:
            # (official & active) OR (owner & active)
            result = (
                self.supabase.table(self.table_name)
                .select("*")
                .eq("id", template_id)
                .or_(f"and(is_official.eq.true,active.eq.true),and(user_id.eq.{user_id},active.eq.true)")
                .single()
                .execute()
            )
            if not result.data:
                print(f"⚠️  Template not found/unauthorized/inactive: {template_id}")
                return None
            print(f"✅ Template retrieved: {result.data['name']}")
            return result.data
        except Exception as e:
            print(f"❌ Failed to get template: {str(e)}")
            return None
    
    def list_templates(self, user_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        try:
            result = (
                self.supabase.table(self.table_name)
                .select("*")
                .eq("user_id", user_id)
                .eq("is_official", False)
                .eq("active", True)
                .order("created_at", desc=True)
                .limit(limit)
                .offset(offset)
                .execute()
            )
            templates = result.data or []
            print(f"✅ Retrieved {len(templates)} active templates for user")
            return templates
        except Exception as e:
            print(f"❌ Failed to list templates: {str(e)}")
            return []

    
    
    def update_template(self, template_id: str, user_id: str, updates: Dict[str, Any]) -> bool:
        try:
            existing = self.get_template(template_id, user_id)
            if not existing:
                print("⚠️  Cannot update - template not found/unauthorized/inactive")
                return False

            allowed_fields = {
                "name", 
                "description", 
                "pdf_url", 
                "field_mappings", 
                "field_order", 
                "category", 
                "template_kind",
                "repeat_config" }
            
            filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
            if not filtered_updates:
                print("⚠️  No valid fields to update")
                return False

            filtered_updates["updated_at"] = datetime.now(timezone.utc).isoformat()

            result = (
                self.supabase.table(self.table_name)
                .update(filtered_updates)
                .eq("id", template_id)
                .eq("user_id", user_id)
                .eq("active", True)
                .execute()
            )

            if not result.data:
                print("❌ Update failed - no data returned")
                return False

            print(f"✅ Template updated: {template_id}")
            invalidate_template_cache(template_id, user_id)
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
            invalidate_template_cache(template_id, user_id)
            return True
        
        except Exception as e:
            print(f"❌ Failed to delete template: {str(e)}")
            return False
    
    
    def get_template_by_name(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        try:
            result = (
                self.supabase.table(self.table_name)
                .select("*")
                .or_(
                    # official & active & name ilike OR owner & active & name ilike
                    f"and(is_official.eq.true,active.eq.true,name.ilike.*{name}*),"
                    f"and(user_id.eq.{user_id},active.eq.true,name.ilike.*{name}*)"
                )
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            return result.data[0]
        except Exception as e:
            print(f"❌ Failed to get template by name: {str(e)}")
            return None
    
    def count_user_templates(self, user_id: str) -> int:
        try:
            result = (
                self.supabase.table(self.table_name)
                .select("id", count="exact")
                .eq("user_id", user_id)
                .eq("is_official", False)
                .eq("active", True)
                .execute()
            )
            return result.count or 0
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
        field_mappings: dict,
        official_form_id: str,
        field_order: list = None,  
        template_kind: str = "standard",                
        repeat_config: Optional[Dict[str, Any]] = None, 
        category: str = "immigration",
        description: str = None,
        price: float = 0.00,
        stripe_price_id: str = None,
        complexity: str = "simple"
    ) -> str:
        """
        Create official BulkForm template with Stripe integration
        
        Args:
            user_id: Admin user ID (must be admin)
            name: Template name
            pdf_url: Storage path to PDF
            field_mappings: Field coordinate mappings
            field_order: List of field names in CSV order (optional)
            official_form_id: Form ID (e.g., 'i-485')
            category: Template category
            description: Optional description
            price: Annual subscription price in dollars
            stripe_price_id: Stripe Price ID (from Stripe API)
            complexity: 'simple', 'medium', or 'complex'
        
        Returns:
            template_id: UUID of created template
        """
        # Check if user is admin
        if not self.is_admin(user_id):
            raise ValueError("Only admins can create official templates")
        
        # If no field_order provided, extract from field_mappings keys
        if field_order is None:
            field_order = list(field_mappings.keys())
            print(f"⚠️ No field_order provided, using field_mappings keys ({len(field_order)} fields)")
        
        template_id = str(uuid.uuid4())
        
        # Insert into database
        self.supabase.table(self.table_name).insert({
            'id': template_id,
            'user_id': user_id,
            'name': name,
            'pdf_url': pdf_url,
            'field_mappings': field_mappings,
            'field_order': field_order, 
            'template_kind': template_kind,
            'repeat_config': repeat_config,
            'is_official': True,
            'official_form_id': official_form_id,
            'category': category,
            'description': description,
            'price': str(price),
            'stripe_price_id': stripe_price_id,
            'complexity': complexity,
            'rental_duration_days': 365,
            'created_at': 'now()'
        }).execute()
        
        print(f"✅ Official template created: {template_id}")
        print(f"   Name: {name}")
        print(f"   Form ID: {official_form_id}")
        print(f"   Fields: {len(field_mappings)} ({len(field_order)} in order)")
        print(f"   Price: ${price}/year")
        print(f"   Stripe Price ID: {stripe_price_id}")
        
        return template_id
  
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
    
    
    def list_official_templates(self, category: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            query = (
                self.supabase.table(self.table_name)
                .select("*")
                .eq("is_official", True)
                .eq("active", True)
            )
            if category:
                query = query.eq("category", category)
            result = query.order("downloads", desc=True).limit(limit).execute()
            templates = result.data or []
            print(f"✅ Retrieved {len(templates)} active official templates")
            return templates
        except Exception as e:
            print(f"❌ Failed to list official templates: {str(e)}")
            return []

    
    
    def get_official_template_by_form_id(self, form_id: str) -> Optional[Dict[str, Any]]:
        try:
            result = (
                self.supabase.table(self.table_name)
                .select("*")
                .eq("is_official", True)
                .eq("active", True)
                .eq("official_form_id", form_id.lower())
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"❌ Failed to get official template: {str(e)}")
            return None    
    
    def get_template_categories(self) -> List[Dict[str, Any]]:
        try:
            result = (
                self.supabase.table(self.table_name)
                .select("category")
                .eq("is_official", True)
                .eq("active", True)
                .execute()
            )
            if not result.data:
                return []
            counts: Dict[str, int] = {}
            for row in result.data:
                cat = row.get("category") or "uncategorized"
                counts[cat] = counts.get(cat, 0) + 1
            categories = [{"category": c, "count": n} for c, n in counts.items()]
            print(f"✅ Found {len(categories)} template categories")
            return categories
        except Exception as e:
            print(f"❌ Failed to get categories: {str(e)}")
            return []

    
    
    def increment_template_downloads(self, template_id: str) -> bool:
        try:
            tpl = (
                self.supabase.table(self.table_name)
                .select("downloads")
                .eq("id", template_id)
                .eq("is_official", True)
                .eq("active", True)
                .single()
                .execute()
            )
            if not tpl.data:
                return False
            current = tpl.data.get("downloads", 0)
            self.supabase.table(self.table_name).update(
                {"downloads": current + 1, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", template_id).execute()
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
    
    def get_template_pdf_url(self, template_id: str) -> Optional[str]:
        try:
            result = (
                self.supabase.table(self.table_name)
                .select("pdf_url,active")
                .eq("id", template_id)
                .eq("active", True)
                .single()
                .execute()
            )
            if result.data and 'pdf_url' in result.data:
                print(f"✅ PDF URL retrieved for template {template_id[:8]}...")
                return result.data['pdf_url']
            print(f"⚠️ Template not found or inactive: {template_id}")
            return None
        except Exception as e:
            print(f"❌ Failed to get template PDF URL: {str(e)}")
            return None

        
    def soft_delete_template(self, template_id: str, user_id: str) -> bool:
        """
        Soft delete a template (active -> false) owned by user_id.
        Returns True if one row was updated.
        """
        try:
            # Only touch records that are still active
            now_iso = datetime.now(timezone.utc).isoformat()

            result = (
                self.supabase.table(self.table_name)
                .update({"active": False, "updated_at": now_iso})
                .eq("id", template_id)
                .eq("user_id", user_id)
                .eq("active", True)
                .execute()
            )

            # supabase-py returns updated rows in .data for UPDATE
            updated = result.data or []
            if len(updated) == 1:
                print(f"✅ Template soft-deleted: {template_id}")
                invalidate_template_cache(template_id, user_id)
                return True

            # If it was already inactive, you can treat as success (idempotent)
            # or return False — choose your policy. Here we treat as success:
            already_inactive = (
                self.supabase.table(self.table_name)
                .select("id,active")
                .eq("id", template_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            ).data
            if already_inactive and already_inactive.get("active") is False:
                print(f"ℹ️  Template already inactive: {template_id}")
                return True

            print("⚠️  Soft delete matched no rows.")
            return False

        except Exception as e:
            print(f"❌ Failed to soft-delete template: {str(e)}")
            return False
        
    def list_templates_paged(
        self, user_id: str, page: int = 1, page_size: int = 24
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Paged custom templates (active only).
        Returns (items, total_count)
        """
        try:
            page = max(1, page)
            page_size = max(1, min(page_size, 100))
            start = (page - 1) * page_size
            end = start + page_size - 1

            q = (
                self.supabase.table(self.table_name)
                .select("*", count="exact")
                .eq("user_id", user_id)
                .eq("is_official", False)
                .eq("active", True)
                .order("created_at", desc=True)
                .range(start, end)
            )
            res = q.execute()
            items = res.data or []
            total = res.count or 0
            return items, total
        except Exception as e:
            print(f"❌ Failed to list custom templates (paged): {e}")
            return [], 0

    def list_official_templates_paged(
        self, page: int = 1, page_size: int = 24, category: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Paged official templates (active only).
        Returns (items, total_count)
        """
        try:
            page = max(1, page)
            page_size = max(1, min(page_size, 100))
            start = (page - 1) * page_size
            end = start + page_size - 1

            q = (
                self.supabase.table(self.table_name)
                .select("*", count="exact")
                .eq("is_official", True)
                .eq("active", True)
            )
            if category:
                q = q.eq("category", category)

            q = q.order("downloads", desc=True).range(start, end)
            res = q.execute()
            items = res.data or []
            total = res.count or 0
            return items, total
        except Exception as e:
            print(f"❌ Failed to list official templates (paged): {e}")
            return [], 0


# ============================================================================
# CONVENIENCE FUNCTION - Easy import
# ============================================================================

def get_template_service() -> TemplateService:
    """Get template service instance"""
    return TemplateService()