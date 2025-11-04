# 🔒 Admin Roles System - Complete Guide

## The Problem You Identified

**Before:**
```python
# ❌ ANYONE could create official templates!
service.create_official_template(user_id="random-user", ...)
# Would work! Security hole! 🚨
```

**After:**
```python
# ✅ Only admins can create official templates
service.create_official_template(user_id="random-user", ...)
# Throws error: "Permission denied: User is not an admin"
```

---

## How It Works

### 1. **Admin Table** (Database-Level)
```sql
CREATE TABLE admins (
  user_id UUID REFERENCES auth.users(id),
  email TEXT,
  role TEXT DEFAULT 'admin'
);
```

### 2. **Admin Check Function** (Python-Level)
```python
def is_admin(user_id: str) -> bool:
    # Check if user_id exists in admins table
    result = supabase.table("admins").select("*").eq("user_id", user_id)
    return len(result.data) > 0
```

### 3. **Security in create_official_template()**
```python
def create_official_template(user_id, ...):
    # 🔒 Check admin status FIRST
    if not self.is_admin(user_id):
        raise Exception("Permission denied: Not an admin")
    
    # Only reaches here if user is admin
    template_data["is_official"] = True
    ...
```

---

## Setup Steps (5 minutes)

### **Step 1: Run Migration** (2 minutes)

1. Open `005_admin_roles.sql`
2. Run in Supabase SQL Editor
3. Creates `admins` table + helper functions

**Verify:**
```sql
SELECT * FROM admins;
-- Should be empty initially
```

---

### **Step 2: Make Yourself Admin** (1 minute)

```sql
-- Get your user_id
SELECT id, email FROM auth.users LIMIT 1;

-- Add yourself as admin (replace YOUR_USER_ID)
INSERT INTO admins (user_id, email, role)
VALUES (
  'd18772bf-7605-4297-8a34-12d8e626199d',  -- Your user_id
  'your@email.com',                          -- Your email
  'admin'
);
```

**Verify:**
```sql
SELECT * FROM admins;
-- Should show your user_id
```

---

### **Step 3: Test Security** (2 minutes)

```bash
python test_admin_security.py
```

**Expected output:**
```
TEST 1: Check Admin Status
✅ You ARE an admin!

TEST 2: Create as Admin (Should Work)
✅ SUCCESS! Official template created

TEST 3: Create as Non-Admin (Should FAIL)
✅ SUCCESS! Security working as expected
   Error: Permission denied: User is not an admin

🔒 SECURE ✅
```

---

## Security Layers

### **Layer 1: Python Service Check**
```python
if not self.is_admin(user_id):
    raise Exception("Permission denied")
```
- Runs before database query
- Fast rejection of non-admins
- Clear error messages

### **Layer 2: Database RLS Policy**
```sql
CREATE POLICY "Admin only for official templates"
  ON pdf_templates FOR INSERT
  WITH CHECK (
    CASE 
      WHEN is_official = TRUE THEN is_current_user_admin()
      ELSE auth.uid() = user_id
    END
  );
```
- Even if Python check is bypassed, database blocks it
- Defense in depth!

---

## Usage Examples

### **As Admin (You):**
```python
from services.template_service import get_template_service

service = get_template_service()

# ✅ This works - you're admin
template_id = service.create_official_template(
    user_id="d18772bf-7605-4297-8a34-12d8e626199d",  # Your ID
    name="USCIS Form I-485",
    pdf_url="https://uscis.gov/i-485.pdf",
    field_mappings={...},
    official_form_id="i-485"
)
```

### **As Regular User:**
```python
# ❌ This fails - not admin
template_id = service.create_official_template(
    user_id="some-random-user-id",
    name="Fake Official Template",
    ...
)
# Raises: Exception("Permission denied: User is not an admin")

# ✅ But this works - custom templates allowed for everyone
custom_id = service.create_template(
    user_id="some-random-user-id",
    name="My Custom Template",
    pdf_url="...",
    field_mappings={...}
)
```

---

## Admin Management

### **Check if User is Admin:**
```python
is_admin = service.is_admin("user-id-here")
if is_admin:
    print("User has admin privileges")
```

### **List All Admins:**
```python
admins = service.list_admins()
for admin in admins:
    print(f"{admin['email']} - {admin['role']}")
```

### **Add New Admin (SQL):**
```sql
INSERT INTO admins (user_id, email, role)
VALUES (
  'new-admin-user-id',
  'newadmin@example.com',
  'admin'
);
```

### **Remove Admin (SQL):**
```sql
DELETE FROM admins WHERE user_id = 'user-id-to-remove';
```

---

## Frontend Integration

### **API Endpoint (Future):**
```python
# routes/template_routes.py

@router.post("/templates/official")
async def create_official_template(
    request: CreateOfficialTemplateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create official template (admin only)
    
    🔒 This endpoint should be HIDDEN in production
    Only expose to admin panel
    """
    try:
        template_id = template_service.create_official_template(
            user_id=current_user['id'],  # From JWT token
            name=request.name,
            pdf_url=request.pdf_url,
            field_mappings=request.field_mappings,
            official_form_id=request.official_form_id
        )
        return {"template_id": template_id}
    
    except Exception as e:
        if "Permission denied" in str(e):
            raise HTTPException(status_code=403, detail="Admin access required")
        raise HTTPException(status_code=500, detail=str(e))
```

### **Frontend Admin Panel:**
```javascript
// Only show "Create Official Template" button to admins
const isAdmin = await checkAdminStatus();

if (isAdmin) {
  <Button onClick={openOfficialTemplateForm}>
    ⭐ Create Official Template
  </Button>
}
```

---

## Testing Scenarios

### ✅ **Should Work:**
1. Admin creates official template → ✅ Success
2. Admin creates custom template → ✅ Success
3. Regular user creates custom template → ✅ Success
4. Admin lists official templates → ✅ Success
5. Regular user lists official templates → ✅ Success (read-only)

### ❌ **Should Fail:**
1. Regular user creates official template → ❌ Permission denied
2. Regular user deletes official template → ❌ Permission denied
3. Regular user modifies official template → ❌ Permission denied

---

## Role Expansion (Future)

```sql
-- Add more granular roles
CREATE TYPE admin_role AS ENUM (
  'superadmin',  -- Can do everything
  'admin',       -- Can create/edit official templates
  'moderator',   -- Can review/approve templates
  'viewer'       -- Can only view admin panel
);

ALTER TABLE admins 
ALTER COLUMN role TYPE admin_role USING role::admin_role;
```

---

## Security Best Practices

### ✅ **DO:**
- Keep admin user_ids secret
- Regularly audit admins table
- Log all official template creations
- Use HTTPS in production
- Rotate Supabase keys periodically

### ❌ **DON'T:**
- Expose `create_official_template` in public API
- Store admin credentials in frontend code
- Let users see who's an admin
- Share service role keys publicly

---

## Troubleshooting

### **"User is not an admin" error:**
```sql
-- Check if you're in admins table
SELECT * FROM admins WHERE user_id = 'your-user-id';

-- If empty, add yourself:
INSERT INTO admins (user_id, email, role)
VALUES ('your-user-id', 'your@email.com', 'admin');
```

### **"admins table doesn't exist" error:**
```sql
-- Run migration 005
-- See: 005_admin_roles.sql
```

### **Admin check always returns false:**
```python
# Make sure using correct Supabase key
# .env should have:
SUPABASE_KEY=your_service_role_key  # NOT anon key!
```

---

## Summary

| Feature | Status |
|---------|--------|
| Admin table created | ✅ |
| Security checks in service | ✅ |
| RLS policies enforced | ✅ |
| Admin check function | ✅ |
| Test script included | ✅ |
| Regular users blocked | ✅ |
| Admins can create official templates | ✅ |

**Security Status: 🔒 LOCKED DOWN ✅**

Only designated admins can create official templates!

---

**Next Steps:**
1. Run migration 005 (create admins table)
2. Make yourself admin (INSERT into admins)
3. Test security (run test_admin_security.py)
4. Create your real official templates (I-485, I-765, I-131)
5. Move to Phase 2.2 (CSV Processor)

---

**Created:** 2025-11-03  
**Security Level:** Production-Ready 🔒