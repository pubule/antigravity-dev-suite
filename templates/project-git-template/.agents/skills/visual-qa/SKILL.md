---
name: visual-qa
description: Dual-viewport Playwright visual QA inspector for desktop (1280x800) and mobile (375x667) UI components.
---

# 👁️ Visual QA Skill (Dual-Viewport Playwright Inspector)

Use this skill whenever modifying or creating user interfaces, web layouts, HTML, CSS, React, Next.js, Vue, or Svelte components.

---

## 📐 Dual-Viewport Specification

Every frontend change must be visually inspected and proven across two standard viewports:

| Viewport | Resolution | Focus Areas | Pass Criteria |
| :--- | :---: | :--- | :--- |
| **Desktop** | **1280 x 800** | Grid/flex layouts, navigation bar, typography, sidebars | Proper visual hierarchy, no clipped content |
| **Mobile (iPhone SE)** | **375 x 667** | Touch targets, responsive wrapping, hamburger menus | **0 horizontal scroll overflow**, min 44x44px touch targets |

---

## 🚀 Execution Methods

### Method 1: Built-in Python Playwright Runner
Execute the integrated cross-platform visual QA script:
```bash
python3 scripts/visual_qa.py http://localhost:5173
# Or for static HTML files:
python3 scripts/visual_qa.py path/to/page.html
```

### Method 2: Playwright MCP Tools
When the Playwright MCP server is active, invoke:
1. `browser_navigate` to target URL.
2. `browser_set_viewport_size` with `{ width: 1280, height: 800 }` and capture screenshot.
3. `browser_set_viewport_size` with `{ width: 375, height: 667 }` and capture mobile screenshot.
4. Check for console errors and `document.documentElement.scrollWidth > window.innerWidth`.

---

## 📋 Verification Checklist
- [ ] Desktop preview (1280x800) matches design layout.
- [ ] Mobile preview (375x667) has **zero horizontal scrollbar**.
- [ ] All interactive buttons and links have adequate touch target sizing (≥44px).
- [ ] 0 JavaScript runtime errors and 0 HTTP 404 network errors.
- [ ] Screenshot paths embedded in the response or summary artifact.
