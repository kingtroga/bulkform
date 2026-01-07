# Template Routes Architecture (UPDATED for Repeated Templates)

## Module Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI App                            │
│                           │                                 │
│                           ▼                                 │
│                 routes/templates/router                     │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Custom Templates │ │ Official         │ │ Utility          │
│ (User-Created)   │ │ Templates        │ │ Endpoints        │
│                  │ │ (BulkForm)       │ │                  │
│ • Create (upload)│ │                  │ │ • Search         │
│ • List           │ │ • List           │ │ • Categories     │
│ • Get            │ │ • Get by form_id │ │ • Stats          │
│ • Update         │ │ • Create (admin) │ │ • Health         │
│ • Delete         │ │ • Public access  │ │                  │
└────────┬─────────┘ └────────┬─────────┘ └──────────────────┘
         │                    │
         ▼                    ▼
    ┌─────────────────────────────────┐
    │  services/template_service.py   │
    │                                 │
    │ ✨ WITH CACHING (NEW!)          │
    │                                 │
    │ • create_template()             │  ◀─ UPDATED: stores template_kind + repeat_config
    │ • @cache_template               │
    │   get_template()                │
    │ • list_templates()              │
    │ • update_template()             │  ◀─ UPDATED: can update template_kind + repeat_config
    │   └─▶ invalidate_template_cache │
    │ • delete_template()             │
    │   └─▶ invalidate_template_cache │
    │ • validate_field_mappings()     │  ◀─ UPDATED: supports repeat (per-field opt-out)
    │ • count_user_templates()        │
    │ • is_admin()                    │
    │ • list_official_templates()     │
    │ • get_official_template_*()     │
    │ • create_official_template()    │  ◀─ UPDATED: stores template_kind + repeat_config
    │ • get_template_categories()     │
    └────────────┬────────────────────┘
                 │
                 ├─────────────────────────┐
                 │                         │
                 ▼                         ▼
        ┌──────────────────┐    ┌──────────────────┐
        │ Redis Cache      │    │ Supabase         │
        │ (NEW!)           │    │                  │
        │                  │    │ • Database       │
        │ template:uid:tid │    │ • Storage (PDFs) │
        │ (1 hour TTL)     │    │ • RLS Policies   │
        │                  │    │                  │
        │ Benefits:        │    │                  │
        │ ✓ Template reuse │    │                  │
        │   across batches │    │                  │
        │ ✓ ~1ms response  │    │                  │
        │ ✓ Reduced DB     │    │                  │
        │   load           │    │                  │
        └──────────────────┘    └──────────────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │ PDF Storage      │
                                  │                  │
                                  │ templates/       │
                                  │   {uid}/         │
                                  │   {template_id}  │
                                  │   .pdf           │
                                  │                  │
                                  │ official_        │
                                  │ templates/       │
                                  │   {form_id}/     │
                                  │   {template_id}  │
                                  │   .pdf           │
                                  └──────────────────┘
```

---

## Request Flow (UPDATED where needed)

### 1. Create Custom Template (Upload PDF)

```
POST /api/templates
   ├─ Validate file (must be PDF)
   ├─ Parse field_mappings JSON
   ├─ Validate field structure (including optional repeat flags)
   ├─ OPTIONAL: accept template_kind + repeat_config
   ├─ Upload PDF to Supabase Storage
   │   └─ Path: templates/{user_id}/{template_id}.pdf
   └─ Create DB record via template_service.create_template()
       └─ Returns: template_id
```

### 2. Get Template (WITH CACHING)

*(unchanged — repeated templates are retrieved the same way; caching still applies)*

### 3. Update Template

```
PUT /api/templates/{template_id}
   │
   ├─ Validate updates (name, description, field_mappings)
   ├─ OPTIONAL: update template_kind + repeat_config
   ├─ Merge field_mappings (update only changed fields)
   ├─ Update in database via template_service.update_template()
   └─ 🗑️ invalidate_template_cache(template_id, user_id)
```

### 6. Create Official Template (Admin Only)

```
POST /api/templates/official
   │
   ├─ Check is_admin(user_id) - 403 if not admin
   ├─ Validate PDF + field_mappings (including optional repeat flags)
   ├─ OPTIONAL: accept template_kind + repeat_config
   ├─ Upload to: official_templates/{form_id}/{template_id}.pdf
   ├─ Create DB record with:
   │   ├─ is_official = true
   │   ├─ official_form_id = form_id (e.g., "i-485")
   │   ├─ category = category
   │   ├─ template_kind = standard|repeated
   │   └─ repeat_config = { ... } (nullable)
   └─ Returns: template_id
```

---

## Data Model (UPDATED)

### Template Record

```python
{
    "id": "41eb78c1-23a2-4f6d-8aed-0ca8d5cfe410",
    "user_id": "a6c3a93a-b1a4-4592-ac53-dba3cf88ae20",
    "name": "BulkForm NDA",
    "pdf_url": "templates/a6c3a93a.../41eb78c1.pdf",
    "field_mappings": {
        "Name": {"page": 1, "x": 43, "y": 36, "size": 30, "font": "arial"},
        "address": {"page": 1, "x": 20, "y": 39, "size": 30, "font": "arial"},
        "date": {"page": 1, "x": 20, "y": 27, "size": 30, "font": "arial"}
    },
    "template_kind": "standard",          # ✅ exists in DB
    "repeat_config": null,                # ✅ exists in DB
    "description": "Optional description",
    "is_official": false,
    "official_form_id": null,
    "category": null,
    "price": null,
    "downloads": 0,
    "created_at": "2025-11-08T10:00:00Z",
    "updated_at": "2025-11-08T10:00:00Z"
}
```

### Repeated Template Record (Apply-to-pages)

```python
{
    "id": "...",
    "template_kind": "repeated",
    "repeat_config": {
        "mode": "apply_to_pages",
        "source_page": 2,
        "repeat_pages": [2, 3, 4, 6, 8, 10]
    },
    "field_mappings": {
        "state_tax_box_1": {"page": 2, "x": 71, "y": 57, "size": 20, "font": "arial", "type": "text"},
        "copy_a_void":     {"page": 2, "x": 33, "y": 9,  "size": 23, "font": "arial", "type": "text", "repeat": false}
    }
}
```

---

## Field Mappings Validation (UPDATED)

### Required fields per mapping:

* `page: int (>= 1)`
* `x: float`
* `y: float`

### Optional fields (existing):

* `size: int`
* `font: str`
* `align: str`
* `type: str` (text/image/checkbox/signature/stamp)

### Optional fields (NEW):

* `repeat: bool`

  * Only meaningful for `template_kind="repeated"` + `repeat_config.mode="apply_to_pages"`
  * Default behavior: repeats/stamps
  * If `repeat: false` → stays only on `source_page` (not stamped to other pages)

---

## Endpoint Categories (UPDATED)

No new endpoints required — repeated templates are created/updated using the same endpoints.

### Custom Templates

```
POST   /api/templates              Create (standard or repeated)
GET    /api/templates              List user's templates
GET    /api/templates/{id}         Get specific template
PUT    /api/templates/{id}         Update template + invalidate cache
DELETE /api/templates/{id}         Delete template + invalidate cache
```

### Official Templates

```
GET    /api/templates/official/list           List all official
GET    /api/templates/official/{form_id}      Get by form ID
POST   /api/templates/official                Create (standard or repeated)
```

---

## Integration with Batch Processing (UPDATED NOTE)

Template retrieval is unchanged (cache works the same). What changes is **PDF generation**, which now branches by:

* `template_kind`
* `repeat_config.mode`

This branching logic lives in **Celery/PDF processing**, not template routes.
