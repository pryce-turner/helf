# Workout Tracker App — Design System & UI Specification

## Overview

This document defines the complete design system for a workout tracking PWA. All pages and components must follow these guidelines to ensure visual consistency, polish, and a premium user experience.

**Target aesthetic**: Dark, motivational fitness app. Think Nike Training Club meets Linear—functional, bold, satisfying to use. The UI should make fitness tracking feel rewarding, not like data entry.

---

## Core Design Principles

1. **Dark-first**: Dark backgrounds reduce eye strain and feel premium. Light theme is optional/secondary.
2. **Celebrate progress**: Every visualization should make the user feel good about consistency and improvement.
3. **Minimal friction**: Common actions should be fast and satisfying.
4. **Information density done right**: Show useful data without clutter. Use progressive disclosure.
5. **Motion with purpose**: Animations should feel responsive and rewarding, never slow or decorative-only.

---

## Color System

Define these as CSS variables at `:root` level. Reference variables everywhere—never hardcode colors.

```css
:root {
  /* Backgrounds - layered depth */
  --bg-base: #09090b;           /* Deepest background */
  --bg-primary: #0a0a0b;        /* Main content background */
  --bg-secondary: #141416;      /* Cards, elevated surfaces */
  --bg-tertiary: #1c1c1f;       /* Nested elements, inputs */
  --bg-hover: #252528;          /* Hover states */
  --bg-active: #2f2f32;         /* Active/pressed states */
  
  /* Text hierarchy */
  --text-primary: #fafafa;      /* Headings, important content */
  --text-secondary: #a1a1a6;    /* Body text, descriptions */
  --text-muted: #5c5c5e;        /* Labels, placeholders, disabled */
  --text-inverse: #09090b;      /* Text on accent backgrounds */
  
  /* Brand accent - vibrant green (success, activity, primary actions) */
  --accent: #22c55e;
  --accent-hover: #16a34a;
  --accent-muted: #15803d;
  --accent-glow: rgba(34, 197, 94, 0.15);
  --accent-subtle: rgba(34, 197, 94, 0.08);
  
  /* Semantic colors */
  --success: #22c55e;
  --warning: #eab308;
  --error: #ef4444;
  --info: #3b82f6;
  
  /* Data visualization palette */
  --chart-1: #22c55e;           /* Primary metric (weight lifted, etc.) */
  --chart-2: #3b82f6;           /* Secondary metric (cardio, reps) */
  --chart-3: #a855f7;           /* Tertiary metric */
  --chart-4: #f97316;           /* Quaternary metric */
  --chart-5: #eab308;           /* Additional metric */
  
  /* Borders & dividers */
  --border: #2a2a2d;
  --border-subtle: #1f1f22;
  --border-focus: var(--accent);
  
  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.5);
  --shadow-glow: 0 0 20px var(--accent-glow);
}
```

---

## Typography

### Font Stack

**DO NOT USE**: Inter, Roboto, Arial, Helvetica, system-ui, or any generic sans-serif. These make the app look like every other AI-generated UI.

**Required fonts**:
```html
<!-- Load from Fontshare (free) -->
<link href="https://api.fontshare.com/v2/css?f[]=clash-display@500,600,700&f[]=satoshi@400,500,600,700&display=swap" rel="stylesheet">

<!-- Monospace for numbers -->
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

**Usage**:
```css
:root {
  --font-display: "Clash Display", sans-serif;   /* Headings, hero text */
  --font-body: "Satoshi", sans-serif;            /* UI text, body copy */
  --font-mono: "JetBrains Mono", monospace;      /* Numbers, stats, data */
}
```

### Type Scale

| Element | Font | Size | Weight | Color | Letter Spacing |
|---------|------|------|--------|-------|----------------|
| Page title | Display | 32px | 700 | primary | -0.02em |
| Section heading | Display | 24px | 600 | primary | -0.01em |
| Card title | Body | 18px | 600 | primary | 0 |
| Body text | Body | 15px | 400 | secondary | 0 |
| Small/caption | Body | 13px | 500 | muted | 0.01em |
| Label | Body | 12px | 600 | muted | 0.05em (uppercase) |
| Stat number | Mono | 32px | 700 | primary | -0.02em |
| Data value | Mono | 16px | 500 | primary | 0 |

---

## Spacing System

Use a consistent 4px base unit. Define spacing tokens:

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
}
```

**Guidelines**:
- Card padding: `--space-5` (20px)
- Gap between cards: `--space-4` (16px)
- Section spacing: `--space-8` or `--space-10`
- Tight groups (e.g., label + input): `--space-2`

---

## Border Radius

```css
:root {
  --radius-sm: 6px;      /* Buttons, inputs, small elements */
  --radius-md: 10px;     /* Cards, dropdowns */
  --radius-lg: 16px;     /* Large cards, modals */
  --radius-xl: 24px;     /* Hero sections, special containers */
  --radius-full: 9999px; /* Pills, avatars, circular elements */
}
```

---

## Component Specifications

### Navigation Bar

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo]     [Calendar] [Progress] [Body] [Planned]    [Avatar] │
└─────────────────────────────────────────────────────────────────┘
```

- Height: 64px
- Background: `var(--bg-secondary)`
- Border-bottom: 1px solid `var(--border-subtle)`
- Horizontal padding: 24px

**Nav items**:
- Icon (20px) + label (14px, medium weight)
- Default: `var(--text-muted)`
- Hover: `var(--text-secondary)` + `var(--bg-hover)` pill background
- Active: `var(--accent)` icon and text + `var(--accent-subtle)` pill background
- Pill padding: 8px 12px, radius: `var(--radius-full)`
- Transition: all 150ms ease

**Mobile**: Icons only, bottom navigation bar

---

### Cards

The primary container for content groups.

```css
.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}

.card--interactive {
  cursor: pointer;
  transition: all 150ms ease;
}

.card--interactive:hover {
  background: var(--bg-tertiary);
  border-color: var(--border);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
```

---

### Stat Cards

For displaying key metrics prominently.

```
┌────────────────────┐
│  📊                │  <- Icon (optional, 24px, muted)
│  1,247             │  <- Value (Mono, 32px, bold)
│  Total Workouts    │  <- Label (13px, muted)
│  +12% vs last mo   │  <- Trend (13px, green/red)
└────────────────────┘
```

```css
.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  min-width: 150px;
}

.stat-card__value {
  font-family: var(--font-mono);
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}

.stat-card__label {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: var(--space-2);
}

.stat-card__trend {
  font-size: 13px;
  font-weight: 500;
  margin-top: var(--space-2);
}

.stat-card__trend--positive { color: var(--success); }
.stat-card__trend--negative { color: var(--error); }
```

---

### Buttons

**Primary** (main actions):
```css
.btn-primary {
  background: var(--accent);
  color: var(--text-inverse);
  font-weight: 600;
  padding: 12px 20px;
  border-radius: var(--radius-sm);
  transition: all 150ms ease;
}

.btn-primary:hover {
  background: var(--accent-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow);
}
```

**Secondary** (less prominent):
```css
.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  /* Same padding and radius as primary */
}

.btn-secondary:hover {
  background: var(--bg-hover);
  border-color: var(--border);
}
```

**Ghost** (minimal):
```css
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}

.btn-ghost:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
```

---

### Form Inputs

```css
.input {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  color: var(--text-primary);
  font-size: 15px;
  transition: all 150ms ease;
}

.input::placeholder {
  color: var(--text-muted);
}

.input:hover {
  border-color: var(--border);
  background: var(--bg-hover);
}

.input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.input-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}
```

---

### Charts & Data Visualization

**General rules**:
- Use `var(--chart-*)` colors for data series
- Background: `var(--bg-secondary)` or transparent
- Grid lines: `var(--border-subtle)`, 1px, dashed or subtle
- Axis labels: `var(--text-muted)`, 12px
- Data labels: `var(--font-mono)`, `var(--text-secondary)`
- Tooltips: `var(--bg-tertiary)` background, `var(--border)` border, `var(--radius-md)`

**Bar charts**:
- Border-radius on bars: 4px (top only for vertical, right only for horizontal)
- Hover state: Slight brightness increase + tooltip
- Consider gradient fills for visual interest

**Line charts**:
- Line width: 2-3px
- Area fill: 10-20% opacity of line color
- Data points: Show on hover or always if sparse data
- Smooth curves (cardinal or monotone interpolation)

**Donut/ring charts**:
- Stroke width: 12-16px
- Gap between segments: 2px
- Center text: Large stat number

---

## Page-Specific Guidelines

### Calendar Page

**Calendar grid**:
- Container: `var(--bg-secondary)`, `var(--radius-lg)`, padding 16px
- Day cells: Square aspect ratio, `var(--bg-tertiary)`, `var(--radius-md)`
- Cell gap: 4px
- Day number: Top-left, 14px, `var(--text-secondary)`
- Today: 2px accent outline, accent background on day number
- Has workout: Accent glow background + indicator dot(s) at bottom
- Other month days: 30% opacity, no interaction

**Month navigation**: Prev/next arrows with month/year centered, bold display font

**Stats row**: Horizontal scrollable row of stat cards below calendar

---

### Progress Page

**Chart section**:
- Full-width chart card showing primary metric over time
- Time range selector: Pills (1W, 1M, 3M, 6M, 1Y, All)
- Exercise/metric filter dropdown

**Progress metrics grid**:
- 2-3 column grid of stat cards
- Show: Total volume, max weight, total reps, PR count, etc.
- Each card can have a mini sparkline

**Personal records section**:
- List or grid of PR achievements
- Show: Exercise name, weight, date achieved
- Highlight recent PRs with accent treatment

---

### Body Composition Page

**Current stats hero**:
- Large display of current weight
- Secondary stats: Body fat %, muscle mass, BMI (if available)
- Trend indicator (up/down arrow with percentage)

**Progress chart**:
- Line chart showing weight over time
- Optional: Overlay goal line
- Time range selector

**Measurement log**:
- Table or list of recent entries
- Columns: Date, weight, body fat, notes
- Editable inline or via modal

**Progress photos** (if applicable):
- Grid of thumbnail images
- Click to expand comparison view
- Date labels on each

---

## Animation Guidelines

### Timing

```css
:root {
  --duration-fast: 100ms;
  --duration-normal: 150ms;
  --duration-slow: 250ms;
  --duration-slower: 350ms;
  
  --ease-default: ease;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

### Standard Transitions

Apply to all interactive elements:
```css
transition: all var(--duration-normal) var(--ease-default);
```

### Page Load Animation

Stagger content appearance:
```css
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-in {
  animation: fadeInUp var(--duration-slow) var(--ease-out) backwards;
}

/* Stagger children */
.stagger-children > *:nth-child(1) { animation-delay: 0ms; }
.stagger-children > *:nth-child(2) { animation-delay: 50ms; }
.stagger-children > *:nth-child(3) { animation-delay: 100ms; }
/* ... etc */
```

### Meaningful Motion

- **Adding workout**: Green pulse/ripple on calendar day
- **New PR**: Confetti or celebration animation
- **Stat change**: Number counting up/down animation
- **Page transitions**: Slide or fade based on navigation direction

---

## Responsive Breakpoints

```css
/* Mobile first */
--breakpoint-sm: 640px;
--breakpoint-md: 768px;
--breakpoint-lg: 1024px;
--breakpoint-xl: 1280px;
```

**Mobile (<768px)**:
- Single column layouts
- Bottom navigation bar
- Full-width cards
- Horizontal scroll for stat card rows
- Simplified charts

**Tablet (768px - 1024px)**:
- 2-column grids where appropriate
- Side navigation or top navigation
- Medium-sized charts

**Desktop (>1024px)**:
- Multi-column layouts
- Top navigation
- Max content width: 1200px, centered
- Full-featured charts with more data points

---

## Accessibility Requirements

- All interactive elements must have visible focus states (accent outline)
- Color contrast: Minimum 4.5:1 for body text, 3:1 for large text
- Don't rely on color alone to convey information (use icons, patterns, labels)
- Touch targets: Minimum 44x44px on mobile
- Support reduced-motion preference:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Empty States

Every page/section needs a designed empty state:

```jsx
<div className="flex flex-col items-center justify-center py-16 text-center">
  <div className="w-16 h-16 mb-4 rounded-full bg-[--bg-tertiary] flex items-center justify-center">
    <Icon className="w-8 h-8 text-[--text-muted]" />
  </div>
  <h3 className="text-lg font-semibold text-[--text-primary] mb-2">
    {title}
  </h3>
  <p className="text-[--text-secondary] mb-6 max-w-sm">
    {description}
  </p>
  <Button variant="primary">{actionLabel}</Button>
</div>
```

---

## Implementation Checklist

Before considering any page complete:

- [ ] CSS variables defined and used consistently (no hardcoded colors)
- [ ] Correct fonts loaded and applied (Clash Display, Satoshi, JetBrains Mono)
- [ ] All text uses appropriate type scale
- [ ] Spacing uses defined tokens
- [ ] All interactive elements have hover/focus/active states
- [ ] Cards have proper backgrounds, borders, and border-radius
- [ ] Charts use defined color palette
- [ ] Page load animations implemented
- [ ] Empty states designed
- [ ] Responsive at all breakpoints
- [ ] Focus states visible for accessibility
- [ ] Reduced motion preference respected

---

## Anti-Patterns to Avoid

❌ **DO NOT**:
- Use raw HTML tables with default borders
- Leave default browser input styles
- Use pure black (#000000) backgrounds
- Mix different border-radius values inconsistently
- Hardcode colors instead of using variables
- Skip hover/focus states on interactive elements
- Use generic fonts (Inter, Roboto, Arial)
- Create flat, unstyled layouts without depth
- Ignore mobile responsiveness
- Add animations that serve no purpose

✅ **DO**:
- Use the defined component patterns
- Maintain consistent spacing with tokens
- Create visual hierarchy with color and typography
- Add subtle depth with backgrounds and shadows
- Make every interaction feel responsive
- Test at multiple screen sizes
- Celebrate user achievements with visual feedback