# CONTINUUM — THEME 4: MIDNIGHT AMETHYST
### Enterprise Project Knowledge Continuity & Handover Verification Platform
**Design Direction:** Premium Fintech & AI Dashboard • Dark Cinematic Atmosphere • Midnight Amethyst

---

## 1. Executive Summary

This folder contains the complete, standalone frontend prototype for **Continuum Theme 4: Midnight Amethyst** (`cont3`).

Continuum is an enterprise software platform engineered to preserve, reconstruct, and transfer institutional codebase knowledge between departing engineers and their successors. It models evidence-backed architectural decisions, conflicting claims across repositories and runbooks, connected source integrations, structured handover workflows, and deterministic readiness evaluations.

Following the design requirements and the reference screenshot of a premium dark investment dashboard, this prototype introduces a luxurious, dark cinematic visual identity. Every surface, border, button, badge, and typographic element has been built with uncompromising precision using:
- **Midnight Black** foundation (`#100E14`) for sidebar and canvas baseline.
- **Dark Aubergine** panels (`#18131E` / `#231B29`) darker than the background for maximum visual depth and floating card contrast.
- **Dusty Mauve** & **Smoky Plum** atmospheric radial background gradients (`#352A38` / `#51404F`).
- **Soft Orchid** (`#C995BC`) for primary call-to-action pills, glowing progress rings, active indicators, and verified evidence accents.
- **Pearl White** (`#F4ECF2`) and **Secondary Text** (`#D0C0CC`) for high-contrast, WCAG AAA compliant readability.

---

## 2. Quick Start & How to Open

### Files in this Repository
- **Interactive Prototype:** [`index.html`](file:///c:/Users/PRANAV%20GAIKWAD/OneDrive/Desktop/cont3/index.html)
- **Design System Documentation:** [`README.md`](file:///c:/Users/PRANAV%20GAIKWAD/OneDrive/Desktop/cont3/README.md)

### How to Run
1. **Direct Double-Click:** Double-click [`index.html`](file:///c:/Users/PRANAV%20GAIKWAD/OneDrive/Desktop/cont3/index.html) in Windows File Explorer, or right-click and open with **Google Chrome** (or Edge, Brave, Firefox, Safari).
2. **Zero Dependencies & Zero Build Step:**
   - No `npm install` or `node_modules`
   - No bundler, compiler, or build process
   - No server, database, or API keys required
   - 100% self-contained vanilla HTML5, CSS3, and modern ES6 JavaScript
3. **Offline Reliability:** Fonts are linked to Google Fonts (`Plus Jakarta Sans`, `Inter`, `IBM Plex Mono`) with robust native system font fallbacks (`system-ui`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `sans-serif`), ensuring instant rendering and complete offline functionality.

---

## 3. Approved Midnight Amethyst Color Palette

The color system strategically balances depth, smoky ambiance, and high-contrast readability:

| Token | Hex / Value | Architectural Role & Usage |
|---|---|---|
| **Midnight Black** | `#100E14` | Fixed left navigation container & canvas foundation |
| **Canvas Deep Base** | `#0D0B10` | Deepest background baseline |
| **Atmospheric Plum** | `#352A38` / `#51404F` | Fixed ambient radial glow in the canvas midtones |
| **Card Surface** | `#18131E` | Primary cards (intentionally darker than ambient glow) |
| **Card Elevated** | `#261D2E` | Hover states, elevated panels, dropdown menus |
| **Highlight Card Base** | `#1C1525` | Base for "Decisions Verified by Evidence" hero card |
| **Muted Plum Border** | `rgba(142, 115, 139, 0.22)` | Fine 1px structural card borders, dividers, inputs |
| **Subtle Divider** | `rgba(142, 115, 139, 0.14)` | Table row dividers, inner sub-section lines |
| **Hover / Focus Border** | `rgba(201, 149, 188, 0.45)` | Interactive card focus outlines and button glows |
| **Soft Orchid** | `#C995BC` | Primary action buttons, readiness progress ring, active navigation indicator |
| **Soft Orchid Hover** | `#DBA8CE` | Primary button hover highlight with soft ambient glow |
| **Dark Aubergine Text** | `#17101A` | High-contrast text on Soft Orchid buttons (WCAG AAA > 7.5:1) |
| **Pearl White** | `#F4ECF2` | Headings, prominent metrics, card titles (WCAG AAA > 14:1) |
| **High Emphasis White**| `#FFFFFF` | Key numbers, active tab text |
| **Secondary Text** | `#D0C0CC` | Explanatory paragraphs, descriptions, code quotes |
| **Muted Lavender-Grey**| `#A698A6` | Timestamps, kickers, entity paths, inactive icons |
| **Functional Emerald** | `#34D399` | Verification pass, online status, positive velocity |
| **Functional Amber** | `#FBBF24` | Pending review, in progress, warning issues |
| **Functional Crimson** | `#F87171` | Open conflict, blockers, rejected claims |

---

## 4. Atmospheric Background Treatment

Directly inspired by the primary visual reference, the root canvas employs a multi-stop fixed radial and linear gradient. This creates a soft, dark plum/mauve illumination that gives cards the appearance of floating with deep spatial separation:

```css
body {
  margin: 0;
  padding: 0;
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.6;
  color: #D0C0CC;
  background:
    radial-gradient(
      ellipse at 58% 20%,
      rgba(137, 99, 130, 0.28),
      transparent 58%
    ),
    radial-gradient(
      ellipse at 85% 75%,
      rgba(98, 69, 101, 0.16),
      transparent 55%
    ),
    radial-gradient(
      ellipse at 15% 45%,
      rgba(81, 64, 79, 0.18),
      transparent 50%
    ),
    linear-gradient(
      125deg,
      #100E14 0%,
      #352A38 52%,
      #17131D 100%
    );
  background-attachment: fixed;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

### Critical Visual Principle: Cards are Darker than Background
Rather than placing lighter cards on a dark background or making everything uniform, the cards use deep near-black aubergine (`#18131E` / `linear-gradient(180deg, #1B1524 0%, #15101C 100%)`). Against the smoky mauve background gradient, the cards form crisp, dark silhouettes with fine plum borders and soft shadows (`0 10px 30px -4px rgba(0, 0, 0, 0.55)`).

---

## 5. Typography Standards

- **Primary Sans-Serif Font Stack:**
  `font-family: 'Plus Jakarta Sans', 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;`
  Enforced globally across all headings (`h1`–`h6`), body paragraphs, buttons, navigation links, and modal dialogs.
- **Strictly Zero Serif Fonts:** No serif fonts exist anywhere in the stylesheet.
- **Technical Monospace Font Stack:**
  `font-family: 'IBM Plex Mono', SFMono-Regular, Menlo, Monaco, Consolas, monospace;`
  Used strictly and exclusively for code tokens, entity hashes, commit IDs, and keyboard shortcuts (`<kbd>`).
- **Minimum Font Size Standard:**
  **Zero text smaller than 12px exists anywhere in the prototype.** All small kickers, badges, timestamps, and metadata are set to 12px–13.5px for clear legibility on standard and high-DPI displays.
- **Standard Scale:**
  - Page Headings: `32px` (weight 700/800, Pearl White)
  - Section Headings: `20px–22px` (weight 700)
  - Card Headings: `18px–20px` (weight 700)
  - Metric Numbers: `34px–42px` (weight 800)
  - Body Text: `15px–16px` (line-height 1.6, Secondary Text `#D0C0CC`)
  - Subtitles & Descriptions: `14px–15px`
  - Navigation & Buttons: `14px–16px` (weight 600)
  - Badges & Kickers: `12px–13px` (minimum)

---

## 6. Reference-Inspired UI Components

### 6.1 Topbar & Floating Search Pill ("Ask Continuum AI anything...")
- Styled after `Ask helios.ai anything` from the reference image.
- Capsule search pill (`border-radius: 9999px`) with sparkle icon, keyboard shortcut badge (`⌘K`), and hover glow.
- Clicking or pressing `⌘K` / `Ctrl+K` opens the interactive **Ask Continuum AI Modal** with pre-configured questions and instant synthesized evidence citations.
- Includes breadcrumbs, simulated API status indicator, Public Demo Environment badge, and user profile capsule (`Alex Mercer / lead@continuum.dev`).

### 6.2 Upper 3-Column Dashboard Hero
Directly mirrors the layout of the reference screenshot's upper dashboard:
1. **Left Column (Readiness + Hero Highlight Card):**
   - **Handover Readiness Tile:** Bold `98.2%` with selector pill `PG-16 ⌄` and green delta badge `+3.5% vs baseline`.
   - **"Decisions Verified by Evidence" Highlight Card:** Direct homage to the reference's "Decisions Powered by Data" card. Features an internal bottom radial glow rising in dusty mauve/soft orchid (`radial-gradient(circle at 50% 120%, rgba(201, 149, 188, 0.32) 0%, rgba(81, 64, 79, 0.15) 50%, transparent 75%)`), heading "Decisions Verified by Evidence", and a prominent Soft Orchid pill button (`Explore Sample Project →`).
2. **Center Column (Knowledge Scenarios):**
   - Direct homage to the reference's "Watchlist" card.
   - Segmented pill controls: `[Active] [Ready] [Review]`.
   - Scenario rows for Payment Gateway, Subscription Billing, and Cold-Chain Alerts with custom icons, stack tags, readiness percentages, and green deltas (`+16.3% ready`, `+8.1% ready`, `+4.9% ready`).
3. **Right Column (Institutional Memory):**
   - Direct homage to the reference's "My Portfolio" card with `Explore all ↗` pill.
   - 2x2 metric quad: Claims Extracted (`42`), Connected Sources (`8`), Open Conflicts (`0`), Successor Tasks (`12`).

### 6.3 Continuity & Verification Velocity Chart
- Direct homage to the reference's "Portfolio Performance" card.
- Interactive time-range pill group: `[1D] [1W] [1M] [6M] [1Y]`.
- Smooth SVG curved bezier path with glowing Soft Orchid stroke (`#C995BC`, `filter: drop-shadow(0 0 10px rgba(201, 149, 188, 0.45))`).
- Translucent vertical area gradient fill fading to transparent at the baseline.
- Vertical dashed guideline at peak milestone (`x=560`).
- Glowing checkpoint circle node with double pulse ring.
- Floating glass tooltip card: `1st Jun 2025 • Handover Milestone | 98.2% Verified | +3.5%`.
- 12-month axis ticks with June highlighted in Soft Orchid.

### 6.4 Circular Readiness Progress Ring
- Large circular SVG gauge (`width: 144px; height: 144px;`).
- Background track in Dark Aubergine / muted plum (`rgba(142, 115, 139, 0.20)`).
- Progress stroke in Soft Orchid (`#C995BC`) with soft drop-shadow glow (`0 0 10px rgba(201, 149, 188, 0.45)`).
- Large, bold central percentage: `98.2%` with uppercase kicker `READY`.

### 6.5 Primary & Secondary Button System
- **Primary Action Buttons:** Soft Orchid background (`#C995BC`), Dark Aubergine text (`#17101A`), rounded pill shape (`border-radius: 9999px`), semi-bold weight (600), subtle box-shadow (`0 4px 16px rgba(201, 149, 188, 0.28)`), and smooth hover lift (`#DBA8CE`).
- **Secondary Buttons:** Dark Aubergine background (`#231B29`), fine plum border (`rgba(142, 115, 139, 0.40)`), Pearl White text (`#F4ECF2`), rounded pill shape, and hover highlight (`#32253B`, border `#C995BC`).

---

## 7. Interactive Feature Parity & Route Directory

The prototype provides full deep-link hash routing across all Continuum workflows:

| Route | View | Description & Capabilities |
|---|---|---|
| `#/dashboard` | **Global Dashboard** | 3-column reference hero, Decisions Verified highlight card, Continuity Velocity chart, demo shortcuts, aggregate metrics, scenario cards, and knowledge breakdown bars. |
| `#/projects` | **Projects Directory** | Searchable project catalog, status tabs, readiness indicators, and new project modal. |
| `#/project-new` | **New Project Wizard** | Multi-field project configuration dialog with validation. |
| `#/sources` | **Global Sources Catalog** | Unified searchable table of ingested repositories, documents, and PRs. |
| `#/sources/:id` | **Source Excerpt View** | Full document inspection with evidence spans and syntax formatting. |
| `#/settings` | **Workspace Settings** | Session state, environment status, database info, and simulated API toggles. |
| `#/projects/:id` | **Project Overview** | Scenario focus card, **98.2% circular readiness gauge**, definition lists, and source breakdown bars. |
| `#/projects/:id/sources` | **Project Sources** | Document library, upload zone with drag-and-drop, and GitHub connect workflow. |
| `#/projects/:id/memory` | **Project Memory** | Categorized knowledge repository (Architecture, Decisions, Ownership, Risks). |
| `#/projects/:id/memory/claims` | **Claims Directory** | Filterable claims catalog with AI verdict tags and evidence citations. |
| `#/projects/:id/memory/review` | **Human Review Queue** | Interactive claim approval workflow (**Approve** and **Reject** buttons with live state mutations). |
| `#/projects/:id/memory/conflicts` | **Conflict Resolution** | Side-by-side claim disagreement review with resolution commit and toast confirmation. |
| `#/projects/:id/memory/uncertainty` | **Uncertainty Tracking** | Open architectural questions and unverified claim tracking. |
| `#/projects/:id/memory/timeline` | **Timeline View** | Vertical chronological milestone log with node markers and claim references. |
| `#/projects/:id/handover` | **Handover Packet** | Synthesized handover document with version history, **Markdown download (`.md`)**, and **browser print trigger**. |
| `#/projects/:id/readiness` | **Readiness Assessment** | Deterministic readiness evaluation (98.2%), dimensional progress bars, blockers, and warnings. |
| `#/projects/:id/successor-workspace` | **Successor Workspace** | Operational roadmap, secret rotation checklist, and architectural boundaries. |
| `#/projects/:id/successor-checklist` | **Successor Checklist** | Interactive task checklist with toggleable checkboxes, strikethrough styling, and task creator modal. |
| `#/projects/:id/knowledge-risk` | **Knowledge Risk Matrix** | Single-owner risks, unapproved operational procedures, and freshness gap audits. |
| `#/projects/:id/evaluation` | **Benchmark Evaluation** | Deterministic extraction metrics, evidence precision, and conflict recall benchmarks. |
| `#/projects/:id/system-health` | **System Health Dashboard** | Service status monitors for ingestion, vector store, and synthesis pipelines. |
| `#/projects/:id/audit` | **Audit Trail** | Event audit log with timestamped records and **CSV export (`.csv`)**. |

---

## 8. Verification & QA Sign-Off

All checks specified in the design brief have been executed and verified:

- [x] **File Isolation:** All work strictly confined to `c:\Users\PRANAV GAIKWAD\OneDrive\Desktop\cont3`. Original application and previous themes (`CONTINUUM`, `Conti`, `Conti2`) are 100% untouched.
- [x] **Visual Reference Atmosphere:** Accurately reproduces the dark panels, smoky plum background gradients, soft orchid accents, and refined typography of the reference screenshot.
- [x] **Approved Palette:** Strictly enforces Midnight Black (`#100E14`), Dark Aubergine (`#18131E`), Dusty Mauve (`#51404F`), Muted Plum (`#8E738B`), Soft Orchid (`#C995BC`), Pearl White (`#F4ECF2`), Secondary Text (`#D0C0CC`), and Muted Lavender (`#A698A6`).
- [x] **Cinematic Gradient Background:** Body uses the multi-stop radial and linear gradient with fixed background attachment.
- [x] **Card Visual Separation:** Cards use deep near-black aubergine surfaces (`#18131E`) that are darker than the atmospheric background, creating clean silhouette separation and depth.
- [x] **Zero Serif Fonts:** 100% modern sans-serif stack (`Plus Jakarta Sans` and `Inter`) for all text and headings.
- [x] **Zero Sub-12px Font Sizes:** Minimum text size is 12px–13.5px across all labels, kickers, and badges.
- [x] **High Contrast (WCAG AA):** Pearl White on Dark Aubergine exceeds 14:1 contrast ratio; Dark Aubergine text on Soft Orchid buttons exceeds 7.5:1 (WCAG AAA).
- [x] **Interactive Demos & Routing:** All routes, tabs, modals (Ask AI, New Project, Add Source, Add Task, Reset Demo), toasts, conflict resolution, and checklist toggles function with simulated persistence.
- [x] **Circular Readiness Visualization:** Preserves the 98.2% circular progress ring with glowing Soft Orchid stroke.
- [x] **All 3 Sample Projects Preserved:**
  1. Payment Gateway System
  2. Subscription Billing & Dunning
  3. Cold-Chain Inventory Alerts
- [x] **Responsive Across Viewports:** Desktop (1440px), Laptop, Tablet, and Mobile (390px) verified with collapsible sidebar drawer and wrapping controls.
- [x] **Standalone Delivery:** Double-click `index.html` opens directly in Google Chrome or Edge with zero installation, build tools, or servers.
