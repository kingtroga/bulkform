# 🚀 BulkForm Frontend Integration Guide: Public Form Portals & Live Spreadsheet Sync

This guide is for the **Frontend Gemini CLI** working on `Bulkform-frontend` (Django app). It contains everything needed to implement public, login-free intake portals for clients like **AA Rescue** (e.g. for the Lagos State Driver's Licence Application Form).

---

## 1. What This Feature Does

1. **Anonymous Applicants:** Students visit `https://bulkform.app/forms/aa-rescue-lagos-license` (or scan a QR code at AA Rescue).
   - **No login / no account required**.
   - Directly upload a **Passport Photo** (file picker or mobile camera).
   - Draw or upload a **Signature** using the existing signature modal engine.
   - Fill in personal info (NIN, Phone, Address, Blood Group, License Class, etc.).
   - Click **Submit & Generate** → Instantly download their completed, pixel-perfect Lagos State Driver's License PDF.
2. **AA Rescue Dashboard & Google Sheets:**
   - Every submission automatically saves in the backend database.
   - AA Rescue can paste `=IMPORTDATA("https://api.bulkform.app/api/public/portals/aa-rescue-lagos-license/live-feed.csv?token=...")` directly into their Google Sheet so new applicant rows appear in real time.
   - AA Rescue can also download full CSV/Excel reports from their BulkForm dashboard.

---

## 2. Backend API Contract (Already Live & Tested)

### A. Fetch Portal & Form Schema (Public, No Auth)
- **URL:** `GET https://api.bulkform.app/api/public/portals/{slug}`
- **Headers:** None (no `Authorization` required)
- **Response Format:**
```json
{
  "id": "uuid-portal-id",
  "name": "Lagos State Drivers Licence Application Form",
  "slug": "aa-rescue-lagos-license",
  "description": "Fill out the Lagos State Drivers Licence Application Form online. Complete it fast and print it.",
  "template_id": "uuid-template-id",
  "field_mappings": {
    "title_surname": { "page": 1, "x": 20, "y": 30, "type": "text" },
    "first_name": { "page": 1, "x": 50, "y": 30, "type": "text" },
    "opus_passport": { "page": 1, "x": 120, "y": 15, "type": "image", "width": 150, "height": 180 },
    "my_signature_png": { "page": 1, "x": 80, "y": 90, "type": "signature", "width": 200, "height": 60 }
  },
  "field_order": [
    "title_surname",
    "first_name",
    "other_names",
    "date_of_birth__dd_mm_yy_",
    "national_identity_number__nin_",
    "phone_number",
    "blood_group",
    "license_class",
    "opus_passport",
    "my_signature_png"
  ],
  "has_image_fields": true,
  "image_fields": ["opus_passport", "my_signature_png"]
}
```

### B. Submit Public Form & Generate PDF (Public, No Auth)
- **URL:** `POST https://api.bulkform.app/api/public/portals/{slug}/submit`
- **Supported Enctypes:** 
  - `multipart/form-data` (Recommended: text fields + direct image file uploads)
  - `application/json` (With base64 data URLs for signatures)
- **Multipart Form Payload:**
  - Standard text fields: `title_surname="Adeleke"`, `first_name="Tari"`, etc.
  - Image / Signature files:
    - Attach file with the field name, e.g. field `opus_passport` -> file `passport.jpg`
    - Attach file with the field name, e.g. field `my_signature_png` -> file `signature.png` (or pass as base64 string `data:image/png;base64,...`)
- **Response (200 OK):**
```json
{
  "status": "success",
  "message": "Your form has been processed successfully.",
  "submission_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "pdf_url": "https://storage.supabase.co/pdfs/filled_pdfs/...",
  "download_url": "https://storage.supabase.co/pdfs/filled_pdfs/...",
  "created_at": "2026-06-29T10:15:30Z"
}
```

---

## 3. Frontend Implementation Steps (In `Bulkform-frontend`)

### Step 1: Add Route in `core/urls.py`
Add the public portal route:
```python
path('forms/<slug:slug>/', views.public_form_portal, name='public_form_portal'),
```

### Step 2: Add View in `core/views.py`
```python
@require_http_methods(["GET"])
def public_form_portal(request, slug):
    """
    Public form portal for anonymous applicant submission
    No login required.
    """
    context = {
        'slug': str(slug),
    }
    return render(request, 'public_form_portal.html', context)
```

### Step 3: Create Template `core/templates/public_form_portal.html`
Create `core/templates/public_form_portal.html` extending `base.html`:
- Include `components/signature_modal.html`.
- Load `js/signature_engine.js`.
- Do NOT perform any `localStorage.getItem('access_token')` redirects.
- Provide a clean file/camera upload for `opus_passport` (or any image field).
- Connect the signature trigger to the signature modal.
- On submit, show a progress bar and display an immediate success screen with:
  - **"✅ Application PDF Ready!"**
  - A prominent green **"Download Completed Application PDF"** button.
  - An option to start another application.

### Step 4: Create JavaScript `static/js/public_form_portal.js`
See complete starter JS snippet below:
```javascript
// public_form_portal.js
const API_BASE = 'https://api.bulkform.app/api';
let portalData = null;
const signatureFiles = {}; // field_name -> File or Blob

document.addEventListener('DOMContentLoaded', async () => {
  await loadPortal();
});

async function loadPortal() {
  const loadingEl = document.getElementById('form-loading');
  const formCard = document.getElementById('form-card');
  const errorEl = document.getElementById('form-error');

  try {
    const res = await fetch(`${API_BASE}/public/portals/${PORTAL_SLUG}`);
    if (!res.ok) throw new Error('Form portal not found or inactive.');
    portalData = await res.json();

    document.getElementById('portal-title').textContent = portalData.name;
    if (portalData.description) {
      document.getElementById('portal-description').textContent = portalData.description;
    }

    renderFormFields(portalData.field_mappings, portalData.field_order);

    loadingEl.classList.add('hidden');
    formCard.classList.remove('hidden');

    document.getElementById('portal-form').addEventListener('submit', handlePublicSubmit);
  } catch (err) {
    loadingEl.classList.add('hidden');
    errorEl.classList.remove('hidden');
    document.getElementById('error-message').textContent = err.message;
  }
}

function renderFormFields(mappings, order) {
  const container = document.getElementById('fields-container');
  container.innerHTML = '';
  const fields = order && order.length ? order : Object.keys(mappings);

  fields.forEach(fieldName => {
    const cfg = mappings[fieldName];
    if (!cfg) return;

    const div = document.createElement('div');
    div.className = 'space-y-1.5';

    // Format human readable label
    const labelText = fieldName.replace(/__/g, ' - ').replace(/_/g, ' ');

    if (cfg.type === 'image' || cfg.type === 'signature' || cfg.type === 'stamp') {
      if (fieldName.toLowerCase().includes('sign')) {
        // Signature input with modal trigger
        div.innerHTML = `
          <label class="block text-sm font-semibold text-ink dark:text-dark-ink-inv capitalize">
            ${labelText} <span class="text-xs text-primary font-normal">(Draw or Upload Signature)</span>
          </label>
          <div class="flex items-center gap-3 p-3 rounded-xl border border-divider dark:border-dark-divider bg-bg-surface dark:bg-dark-bg-surface">
            <button type="button" class="btn-sig-trigger px-4 py-2 text-sm font-medium bg-primary text-white rounded-lg hover:bg-primary-600 transition" data-field="${fieldName}">
              ✍️ Add Signature
            </button>
            <span class="sig-status text-xs text-muted" id="status-${fieldName}">No signature added yet</span>
            <input type="hidden" name="${fieldName}" id="input-${fieldName}" />
          </div>
        `;
      } else {
        // Passport photo / document image upload
        div.innerHTML = `
          <label class="block text-sm font-semibold text-ink dark:text-dark-ink-inv capitalize">
            ${labelText} <span class="text-xs text-primary font-normal">(Passport Photo - JPG/PNG)</span>
          </label>
          <input type="file" accept="image/*" name="${fieldName}" id="file-${fieldName}"
                 class="w-full text-sm p-2 rounded-xl border border-divider dark:border-dark-divider bg-white dark:bg-dark-bg-surface" />
        `;
      }
    } else {
      // Regular text field
      div.innerHTML = `
        <label for="${fieldName}" class="block text-sm font-semibold text-ink dark:text-dark-ink-inv capitalize">
          ${labelText}
        </label>
        <input type="text" id="${fieldName}" name="${fieldName}" placeholder="Enter ${labelText}"
               class="w-full px-4 py-3 rounded-xl border border-divider dark:border-dark-divider bg-white dark:bg-dark-bg-surface text-ink dark:text-dark-ink-inv focus:ring-2 focus:ring-primary/50" />
      `;
    }

    container.appendChild(div);
  });

  // Attach signature modal events
  setupSignatureHooks();
}

async function handlePublicSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const submitBtn = document.getElementById('submit-btn');
  const submitText = document.getElementById('submit-btn-text');

  submitBtn.disabled = true;
  submitText.textContent = 'Generating Driver\\'s License PDF...';

  try {
    const formData = new FormData(form);

    // Append signature blobs if drawn in modal
    for (const [field, blobOrFile] of Object.entries(signatureFiles)) {
      formData.set(field, blobOrFile);
    }

    const res = await fetch(`${API_BASE}/public/portals/${PORTAL_SLUG}/submit`, {
      method: 'POST',
      body: formData // multipart/form-data
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to submit form');
    }

    const result = await res.json();

    // Show success view with direct PDF download button
    document.getElementById('form-card').classList.add('hidden');
    const successCard = document.getElementById('success-card');
    document.getElementById('download-pdf-btn').href = result.pdf_url;
    successCard.classList.remove('hidden');

  } catch (err) {
    alert('Error: ' + err.message);
    submitBtn.disabled = false;
    submitText.textContent = 'Submit Application';
  }
}
```

---

## 4. Live Spreadsheet Link for AA Rescue

AA Rescue can paste this formula directly into cell `A1` of any Google Sheet:
```excel
=IMPORTDATA("https://api.bulkform.app/api/public/portals/aa-rescue-lagos-license/live-feed.csv?token=PORTAL_ACCESS_TOKEN")
```
Every time a student submits an application on the web, their row (NIN, Phone, Address, Blood Group, License Class, and PDF link) will automatically appear in AA Rescue's spreadsheet!
