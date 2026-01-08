# BulkForm Repeated Templates Manual 📚

## The Problem We're Solving

You have a W-2 form with 6 copies (Copy A, Copy B, Copy C, Copy D, Employee Copy, etc.). Each copy is identical - same fields in the same positions. Do you want to map the same fields 6 times? **Hell no.** That's what Repeated Templates solve.

---

## Template Types

### 1️⃣ **Standard Template** (Default)
**What it is:** Normal template. Each page is unique.

**When to use:**
- Single-page forms (I-485, passport application)
- Multi-page forms where EACH page has DIFFERENT fields

**Example:** I-485 immigration form
- Page 1: Personal info
- Page 2: Employment history  
- Page 3: Address history
- Each page is DIFFERENT → Use Standard

---

### 2️⃣ **Repeated Template: Apply to Pages (Stamp Mode)** ⭐

**What it is:** Map once, stamp to multiple pages. Same fields appear in the same position on multiple pages.

**When to use:**
- W-2 copies (Copy A, B, C, D all identical)
- Tax forms with duplicate copies
- Certificates where you print multiple identical copies

**How it works:**
1. Select "Repeated" template kind
2. Choose "Apply to pages (stamp)" mode
3. Set Source Page (e.g., Page 1)
4. Select which pages to stamp to (e.g., Pages 1, 2, 3, 4, 5, 6)
5. Map your fields ONCE on the Source Page
6. When you save, those fields stamp onto ALL selected pages

**Example: W-2 Form**

```
PDF Structure:
- Page 1: Copy A (Federal)
- Page 2: Copy B (Federal)
- Page 3: Copy C (State)
- Page 4: Copy D (Employer)
- Page 5: Employee Copy
- Page 6: Employee State Copy

Your Setup:
✅ Template Kind: Repeated
✅ Repeat Mode: Apply to pages (stamp)
✅ Source Page: 1
✅ Repeat Pages: 1, 2, 3, 4, 5, 6 (check all)

You Map ONCE on Page 1:
- employer_name → Grid (50, 10)
- employee_name → Grid (50, 20)
- wages → Grid (100, 30)
- ssn → Grid (120, 15)

Result:
When you bulk-fill with 100 employees, each employee gets a 6-page PDF:
- Page 1: Copy A with their data
- Page 2: Copy B with their data
- Page 3: Copy C with their data
- Page 4: Copy D with their data
- Page 5: Employee Copy with their data
- Page 6: Employee State Copy with their data
```

**Special Feature: Per-Field Repeat Toggle**

Sometimes ONE field should NOT repeat. Example: "COPY A - VOID" text that only appears on Page 1.

When mapping on Source Page, you'll see a **Repeat checkbox** for each field:
- ✅ **Checked (default):** Field stamps to all selected pages
- ❌ **Unchecked:** Field ONLY appears on Source Page

**Example:**
```
employer_name → Repeat: ✅ (appears on all pages)
employee_name → Repeat: ✅ (appears on all pages)
"COPY A" label → Repeat: ❌ (only on Page 1)
```

---

### 3️⃣ **Repeated Template: Pages (Row → Page Cloning)**

**What it is:** Each CSV row creates MULTIPLE pages. Used for multi-page itemized forms.

**When to use:**
- Invoice with line items (each item = new page)
- Medical claims (each procedure = new page)
- Insurance forms where each dependent gets their own page

**How it works:**
1. Select "Repeated" template kind
2. Choose "Pages (row → page cloning)" mode
3. Map fields on Source Page
4. Each row in your CSV creates a NEW PAGE using that template

**Example: Multi-Page Invoice**

```
CSV:
item_name, item_price, item_description
Widget A, $50, Blue widget
Widget B, $75, Red widget  
Widget C, $100, Green widget

Your Setup:
✅ Template Kind: Repeated
✅ Repeat Mode: Pages
✅ Source Page: 1

Map on Page 1:
- item_name → Grid (50, 10)
- item_price → Grid (100, 10)
- item_description → Grid (50, 20)

Result:
Final PDF has 3 pages:
- Page 1: Widget A, $50, Blue widget
- Page 2: Widget B, $75, Red widget
- Page 3: Widget C, $100, Green widget
```

---

## Quick Decision Tree

```
Do you need multiple pages per record?
│
├─ NO → Use Standard Template
│
└─ YES → Use Repeated Template
    │
    ├─ Same fields in same positions on multiple pages?
    │  (W-2 copies, duplicate certificates)
    │  └─ Use "Apply to pages (stamp)"
    │
    └─ Each CSV row creates a new page?
       (Line items, dependents, procedures)
       └─ Use "Pages"
```

---

## Step-by-Step: Creating a W-2 Stamp Template

### Step 1: Upload & Choose Template Kind
1. Upload W-2 PDF (6 pages)
2. In sidebar, select **Template Kind: Repeated**
3. Panel expands with more options

### Step 2: Configure Repeat Settings
1. **Repeat Mode:** Select "Apply to pages (stamp)"
2. **Source Page:** Set to 1 (or click "Use Current Page")
3. **Repeat Pages:** Check pages 1, 2, 3, 4, 5, 6

### Step 3: Map Fields (ONLY on Source Page)
1. Navigate to Page 1 (your Source Page)
2. Click on PDF to add fields
3. Map: employer_name, employee_name, wages, ssn, etc.

💡 **Important:** If you're on Page 2-6, you'll see a tip:
> "Stamp template tip: map fields on Source Page 1 (you are on Page 2)"

### Step 4: Handle One-Off Fields (Optional)
If a field should ONLY appear on Source Page:
1. Find field in sidebar
2. Uncheck **"Repeat"** toggle
3. Field will NOT stamp to other pages

Example: "COPY A - FOR SOCIAL SECURITY ADMINISTRATION" label

### Step 5: Save Template
1. Click "Continue to Pricing"
2. Set template name, price
3. Click "Create Template & Stripe Product"

### Step 6: Bulk Fill
When users bulk-fill:
```
CSV with 100 employees →
100 PDFs × 6 pages each = 
600 total pages, all properly filled
```

---

## Common Questions

**Q: Why do I only see the Repeat toggle on Page 1?**  
A: The toggle only appears on the Source Page in stamp mode. Other pages automatically get the stamped fields.

**Q: Can I map fields on Page 2-6?**  
A: You CAN, but don't. In stamp mode, only map on the Source Page. Fields on other pages won't stamp.

**Q: What if Copy B needs one extra field that Copy A doesn't have?**  
A: Use Standard template instead. Stamp mode is for IDENTICAL pages only.

**Q: Can I change which pages to stamp to after creating the template?**  
A: No, you'd need to create a new template. Choose your pages carefully.

**Q: Difference between "apply_to_pages" and "pages"?**  
A: 
- **apply_to_pages (stamp):** 1 CSV row = multiple pages with SAME data
- **pages (clone):** Multiple CSV rows = multiple pages with DIFFERENT data

---

## Real-World Use Cases

### ✅ Use "Apply to Pages (Stamp)"
- W-2 tax forms (6 copies)
- 1099 forms (3 copies)
- Birth certificates (duplicate for records)
- Diploma copies (original + file copy)
- Insurance cards (member copy, provider copy)

### ✅ Use "Pages (Clone)"
- Invoices with line items
- Medical claim forms (multiple procedures)
- Expense reports (multiple receipts)
- Insurance policies (multiple dependents)
- Inventory lists (multiple items)

### ❌ Use Standard
- I-485 (each page unique)
- Passport application (each page different)
- Most single-page forms
- Any form where pages have different fields

---

## Pro Tips 💡

1. **Test with 2 records first** - Don't bulk-fill 1000 until you verify the template works

2. **Source Page = Page 1 usually** - Unless your PDF has a cover page you want to skip

3. **Check ALL pages** - After mapping, manually check a few pages to ensure fields align

4. **Use Refresh Canvas** - If the grid looks misaligned, click the Refresh button

5. **Repeat toggle is your friend** - Use it for page-specific labels like "COPY A", "COPY B", etc.

---

Need help? Drop a message and I'll guide you through your specific form! 🚀