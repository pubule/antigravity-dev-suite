---
name: visual-qa
description: Dual-viewport Playwright visual QA inspector for desktop (1280x800) and mobile (375x667) UI components.
---

# 👁️ Visual QA Skill (Dual-Viewport Playwright Inspector)

> **Paths**: `scripts/` is the suite folder, not your project: `~/.gemini/config/plugins/antigravity-dev-suite/scripts/`. On Windows use `py -3` instead of `python3`. The Stop gate runs the checks again when you finish.

Use this skill whenever modifying or creating user interfaces, web layouts, HTML, CSS, React, Next.js, Vue, or Svelte components.

> **Enforced.** When you change a UI file (`.tsx .jsx .vue .svelte .astro .html .css .scss`), the Stop gate runs this check by itself and blocks while it fails. Run it yourself first, so you find the defects before the gate does.

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
python3 ~/.gemini/config/plugins/antigravity-dev-suite/scripts/visual_qa.py http://localhost:5173
# Or for static HTML files:
python3 ~/.gemini/config/plugins/antigravity-dev-suite/scripts/visual_qa.py path/to/page.html
```
Exit code 0 means a clean page. Exit code 1 means defects: read `page_errors`, `console_errors`, `http_errors` and `a11y_violations` in the JSON output.
Then open `desktop_preview.png` and `mobile_preview.png` (paths in `screenshots`) and look at them.

### Method 0: The gate itself
`python3 ~/.gemini/config/plugins/antigravity-dev-suite/scripts/agy_hook.py check` runs the same visual step as the Stop gate, with the dev server settings from `.agents/agy.json`.

### Method 2: Playwright MCP Tools (interaction)
Use this to test what a static screenshot cannot show: menus, modals, forms, navigation.
When the Playwright MCP server (`@playwright/mcp`) is active:
1. `browser_navigate` to the target URL.
2. `browser_resize` with `{ "width": 1280, "height": 800 }`, then `browser_take_screenshot`.
3. `browser_snapshot` to read the page structure, then `browser_click` / `browser_type` to use the feature you changed.
4. `browser_resize` with `{ "width": 375, "height": 667 }`, then `browser_take_screenshot` again.
5. `browser_console_messages` must show zero errors. `browser_evaluate` with `() => document.documentElement.scrollWidth > window.innerWidth` must return `false`.

---

## 📋 Verification Checklist
- [ ] Desktop preview (1280x800) matches design layout.
- [ ] Mobile preview (375x667) has **zero horizontal scrollbar**.
- [ ] All interactive buttons and links have adequate touch target sizing (≥44px).
- [ ] 0 JavaScript runtime errors and 0 HTTP 404 network errors.
- [ ] Screenshot paths embedded in the response or summary artifact.
