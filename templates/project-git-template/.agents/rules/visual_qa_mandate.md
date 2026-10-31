# Multimodal Visual QA & Layout Verification Mandate

Whenever creating or modifying frontend artifacts, UI components, HTML, CSS, React/Vue/Svelte layouts, or SVG assets, you MUST enforce the **Visual QA Protocol**:

## 1. Dual-Viewport Verification
- **Desktop Viewport**: 1280x800 (Full-page layout, navigation, grid/flex structure).
- **Mobile Viewport**: 375x667 (iPhone SE standard — touch targets, text wrapping, zero horizontal scroll overflow).

## 2. Execution via Playwright
- Execute headless visual inspection using the bundled `visual_qa.py` runner or Playwright MCP.
- The runner automatically detects active local dev servers (ports `5173`, `3000`, `8080`, `4200`, etc.) or static HTML entry points.
- Inspect captured screenshots for:
  1. **Visual Fidelity**: Proper alignment, margins, colors, and font rendering.
  2. **Responsive Constraints**: No elements clipped or forced off-screen on 375px widths.
  3. **Console & Asset Health**: 0 JavaScript runtime errors and 0 HTTP 404s on images/fonts.

## 3. Autonomous Visual Defect Remediation
- If a visual defect, misaligned button, or overflow is detected in the captured screenshots, immediately edit the CSS/DOM rules and re-capture until the layout is clean.
- Include screenshot references or visual status in your final completion artifact.
