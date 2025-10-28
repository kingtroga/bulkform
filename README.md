# BulkForm
```
██████╗ ██╗   ██╗██╗     ██╗  ██╗███████╗ ██████╗ ██████╗ ██████╗ ███╗   ███╗
██╔══██╗██║   ██║██║     ██║ ██╔╝██╔════╝██╔═══██╗██╔══██╗██╔══██╗████╗ ████║
██████╔╝██║   ██║██║     █████╔╝ █████╗  ██║   ██║██████╔╝██████╔╝██╔████╔██║
██╔══██╗██║   ██║██║     ██╔═██╗ ██╔══╝  ██║   ██║██╔══██╗██╔══██╗██║╚██╔╝██║
██████╔╝╚██████╔╝███████╗██║  ██╗██║     ╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
```

**Automate PDF form filling using grid coordinates.**

---

## What This Does

Takes static PDF forms (like T4s, visa applications, HR docs) and fills them automatically using a grid-based coordinate system.

**No more manual data entry.**

---

## Current Status

**MVP Stage** - Single-file CLI working

- ✅ PDF to image conversion
- ✅ Grid overlay system (100×100)
- ✅ Text placement at coordinates
- ✅ Single page + multi-page output
- 🚧 FastAPI backend (next)
- 🚧 CSV batch processing (next)
- 🚧 Web interface (later)

---

## Tech Stack

**Current:**
- Python 3.11+
- Pillow (image processing)
- pdf2image (PDF conversion)
- img2pdf (image to PDF)

**Planned:**
- FastAPI (backend API)
- Supabase (database + storage)
- Render (deployment)

---

## Quick Start
```bash
# Install dependencies
pip install pillow pdf2image img2pdf

# Run the CLI
python main.py

# Follow prompts to:
# 1. Load PDF
# 2. View gridded pages
# 3. Fill with text at coordinates
# 4. Export filled PDF
```

---

## How It Works

1. **Load PDF** → Convert pages to images
2. **Apply Grid** → Overlay 100×100 coordinate system
3. **Map Fields** → User specifies grid coordinates for each field
4. **Fill Forms** → Place text at exact positions
5. **Export** → Generate filled PDF

---

## Next Steps

- [ ] Build FastAPI backend
- [ ] Add CSV import for batch processing
- [ ] Deploy to Render
- [ ] Get first beta user
- [ ] Get first paying customer ($1)

---

## Target Market

- Immigration paralegals
- HR departments (onboarding)
- Small law firms
- Real estate agents
- Tax preparers

**Anyone filling 50+ PDF forms per month.**

---

## Goal

**10 paying customers by December 31, 2025**

Revenue target: $1,000/month

---

## Notes to Self

- Keep it simple - no over-engineering
- Ship fast, iterate based on real feedback
- Build → Test → Ship → Repeat
- Revenue > Engagement
- Customers > Followers

---

**Last Updated:** October 27, 2025