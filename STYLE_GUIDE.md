# Esoteria Design System
## Shared Style Guide v1.0
### All Projects — Esoteria Platform

```
Status: Active
Applies to: Esoteria main site,
Denuncia Popular, Civic Intelligence
Platform, all white-label instances
Last updated: March 2026
Maintained by: Douglas Galloway
```

---

## 1. Design Principles

These principles apply to every project
in the Esoteria platform ecosystem.
They are not aesthetic preferences.
They are constraints.

```
Institutional over decorative
Every visual decision should reinforce
credibility and seriousness.
If it looks like a startup marketing site
it is wrong.

Legibility over expression
Content is the design. Typography carries
the visual weight. Decoration does not.

Consistency over creativity
Every project should feel like it belongs
to the same family. A user moving from
the main site to Denuncia Popular should
feel continuity, not disconnection.

Governance-first visual language
The design system reflects the doctrine.
Structure, clarity, no ambiguity.
```

---

## 2. Color System

### 2.1 Core Tokens — Fixed Across All Projects

These values never change regardless
of instance or use case:

```
--color-background: #0A0A0A
Primary page background.
Never replaced with white or light values.
Dark mode is not a feature — it is the
default and only mode.

--color-surface: #111111
Card backgrounds, elevated containers,
form fields.

--color-border: #222222
All borders, dividers, separators.
1px solid only. No thick borders.

--color-text-primary: #FFFFFF
All headings, primary body text,
nav labels.

--color-text-secondary: #AAAAAA
Supporting body text, descriptions,
secondary information.

--color-text-muted: #666666
Status indicators, metadata, timestamps,
labels, breadcrumbs.

--color-text-disabled: #444444
Inactive states, placeholder text.
```

### 2.2 Accent Token — Configurable Per Instance

This is the only color that changes
between instances:

```
--color-accent: [instance-defined]
Used for: CTAs, active states, division
tags, links, hover states, icons.

Esoteria main site: #C0392B
Denuncia Popular Instance 01: #C0392B
White-label instances: defined per brand

Accent hover state:
Always 15% darker than accent value.
Esoteria: #A93226

Accent usage rules:
- Never use as background on large areas
- Never apply gradients to accent color
- Flat color only
- Maximum 20% of any page surface
```

### 2.3 Status Colors — Fixed

```
--color-status-active: #27AE60
Live, published, confirmed states.

--color-status-pending: #F39C12
In preparation, forthcoming, review states.

--color-status-inactive: #666666
Archived, deprecated, disabled states.

--color-status-alert: #C0392B
Errors, warnings, critical states.
Same as default accent on main site —
on instances with different accent colors
this remains #C0392B for alert states only.
```

---

## 3. Typography

### 3.1 Font Stack

```
Primary: IBM Plex Mono
Use: All headings, navigation, labels,
buttons, technical elements, code,
monospace display text.
Weights used: 400, 500, 600, 700, 800

Fallback: Inter
Use: Body text fallback only when
IBM Plex Mono fails to load.
Never use Inter as a deliberate choice.

System fallback:
system-ui, -apple-system, monospace

CSS declaration:
font-family: 'IBM Plex Mono', 'Inter',
system-ui, -apple-system, monospace
```

### 3.2 Type Scale

```
Hero H1 — Page heroes, primary statements
font-size: clamp(32px, 8vw, 84px)
font-weight: 700
font-family: IBM Plex Mono

Page H1 — Interior page titles
font-size: clamp(32px, 6vw, 64px)
font-weight: 800
font-family: IBM Plex Mono

H2 — Section headings
font-size: clamp(28px, 5vw, 48px)
font-weight: 700
font-family: IBM Plex Mono

H3 — Card titles, subsection headings
font-size: clamp(20px, 3vw, 28px)
font-weight: 700
font-family: IBM Plex Mono

Body Large — Lead paragraphs, descriptions
font-size: 20px
font-weight: 400
line-height: 1.7

Body — Standard body text
font-size: 18px
font-weight: 400
line-height: 1.7

Body Small — Supporting text, card body
font-size: 16px
font-weight: 400
line-height: 1.6

Label — Tags, metadata, breadcrumbs
font-size: 14px
font-weight: 500
font-family: IBM Plex Mono
letter-spacing: 0.02em

Micro — Timestamps, status, footnotes
font-size: 12px
font-weight: 400
color: --color-text-muted
```

### 3.3 Typography Rules

```
Never use serif fonts anywhere.

Never use font-weight below 400.

Headings always use IBM Plex Mono
explicitly — never rely on inheritance
alone. Always declare fontFamily on
every heading element.

Line length — body text maximum 680px.
Never let body text span full container
width on large screens.

All caps — never use text-transform:
uppercase on body text. Acceptable on
micro labels only and sparingly.

Hyphenation — never use
hyphens: auto on any text.
Use word-break: break-word on headings
only for mobile overflow prevention.
```

---

## 4. Spacing System

```
Base unit: 8px

Scale:
--space-1: 8px
--space-2: 16px
--space-3: 24px
--space-4: 32px
--space-5: 48px
--space-6: 64px
--space-7: 80px
--space-8: 120px

Common applications:
Card padding: 48px desktop / 32px 24px mobile
Section padding vertical: 80px desktop
Page hero padding top: 120px
Container horizontal padding: 24px mobile
Gap between cards: 24px
Gap between nav items: 32px
```

---

## 5. Layout System

### 5.1 Container

```
Max width: 1200px
Margin: 0 auto
Width: 100%
Horizontal padding: 24px mobile
                    32px tablet
                    0px desktop
                    (contained by maxWidth)
```

### 5.2 Grid

```
Desktop: 12-column grid
Standard content: 8 columns centered
Two-column cards: 6/6
Three-column cards: 4/4/4

Tablet (768px and below):
Two-column → single column
Three-column → single column

Mobile (480px and below):
All layouts → single column
Full width cards
Reduced padding
```

### 5.3 Breakpoints

```
Mobile: max-width 480px
Tablet: max-width 768px
Desktop: min-width 769px
Wide: min-width 1200px
```

---

## 6. Component Patterns

### 6.1 Cards

```
Background: --color-surface (#111111)
Border: 1px solid --color-border (#222222)
Border-radius: 0px — never rounded
Padding desktop: 48px
Padding mobile: 32px 24px
Box-shadow: none — never

Hover state (interactive cards only):
border-color: --color-accent
transition: border-color 200ms ease
```

### 6.2 Buttons

```
Primary button:
background: --color-accent
color: #FFFFFF
border: none
border-radius: 0px
padding: 16px 32px
font-family: IBM Plex Mono
font-size: 16px
font-weight: 700
cursor: pointer
transition: background 200ms ease

Hover:
background: accent hover value

Secondary button / outline:
background: transparent
color: --color-accent
border: 1px solid --color-accent
border-radius: 0px
padding: 16px 32px
font-family: IBM Plex Mono
font-size: 16px
font-weight: 700

Hover:
background: --color-accent
color: #FFFFFF

Terminal style CTA (main site pattern):
prefix: ">"
example: "> Contact Esoteria"
No button container — styled as
inline terminal command link
color: --color-accent
font-family: IBM Plex Mono
```

### 6.3 Navigation

```
Background: #0A0A0A
Border-bottom: 1px solid #222222
Height: 64px desktop / 56px mobile
Font: IBM Plex Mono
Font-size: 13px
Font-weight: 500
Color: #FFFFFF
Letter-spacing: 0.01em
White-space: nowrap — never wrap nav labels

Active/current page:
color: --color-accent

Hover:
color: --color-accent
transition: color 200ms ease

Logo:
Font: IBM Plex Mono
Font-weight: 700
Prefix: ">"
Suffix: "_" (blinking cursor optional)
```

### 6.4 Forms

```
Field container:
background: --color-surface
border: 1px solid --color-border
border-radius: 0px
padding: 16px

Focus state:
border-color: --color-accent
outline: none

Labels:
font-size: 14px
font-weight: 600
font-family: IBM Plex Mono
color: --color-text-primary
margin-bottom: 8px

Input text:
font-size: 16px
font-family: IBM Plex Mono
color: --color-text-primary
background: transparent

Placeholder:
color: --color-text-muted
```

### 6.5 Division Tags

```
Format: "> Division I — [Name]"
        "> División I — [Nombre]" (ES)
font-size: 14px
font-family: IBM Plex Mono
font-weight: 500
color: --color-accent
margin-bottom: 16px
```

### 6.6 Status Indicators

```
Format: "> [Status text]"
font-size: 14px
font-family: IBM Plex Mono
color: --color-text-muted (#666666)
or --color-status-[state] as appropriate
```

---

## 7. Visual Rules — Non-Negotiable

```
No gradients
Never use linear-gradient or
radial-gradient anywhere in the UI.
Flat color only.

No border-radius
All containers, cards, buttons, inputs
use border-radius: 0px.
No rounded corners anywhere.

No shadows
Never use box-shadow or drop-shadow
on any UI element.

No animations beyond transitions
No keyframe animations, no scroll
animations, no entrance effects.
Transition on hover states only.
Max transition duration: 300ms.

No decorative elements
No divider graphics, no background
textures, no illustration, no icons
beyond functional UI icons.

No light mode
Dark background is not a theme option.
It is the only mode.
```

---

## 8. White-Label Configuration

When deploying a new instance the
following tokens are configurable.
Everything else inherits from this
style guide unchanged:

```
CONFIGURABLE PER INSTANCE:
--color-accent: [brand color]
Logo text: [instance name]
Nav prefix ">": optional per instance
Font imports: IBM Plex Mono always loaded,
additional fonts may be added but never
replace IBM Plex Mono as primary

NOT CONFIGURABLE:
Background colors
Surface colors
Border colors
Text colors (primary, secondary, muted)
Typography rules
Spacing system
Layout system
Component border-radius
Gradient prohibition
Shadow prohibition
```

### Configuration File Pattern

Each instance should maintain a
`DESIGN_TOKENS.md` file at repo root
with the following structure:

```markdown
# [Instance Name] — Design Tokens
## Inherits: Esoteria Style Guide v1.0

INSTANCE: [name]
ACCENT_COLOR: [hex value]
ACCENT_HOVER: [hex value]
LOGO_TEXT: [display name]
DEPLOYED_AT: [domain]
LAST_UPDATED: [date]

## Overrides
[List any approved overrides here.
Empty means full inheritance.]

## Approved By
Douglas Galloway — [date]
```

---

## 9. File Locations

```
Main site:
/styles/globals.css — global tokens
/DESIGN_TOKENS.md — instance config

Denuncia Popular:
/styles/globals.css — global tokens
/DESIGN_TOKENS.md — instance config

Civic Intelligence Platform:
/styles/globals.css — global tokens
/DESIGN_TOKENS.md — instance config

Shared reference:
This document lives in the Esoteria
main site repo at:
/docs/STYLE_GUIDE.md

All other repos reference it via link.
One source of truth. One maintainer.
```

---

## 10. Version Control

```
This document is versioned.
All changes require approval from
Douglas Galloway before merging.

Version history:
v1.0 — March 2026 — Initial release
       Derived from Esoteria main site
       post-rebrand visual audit
```

---

*Esoteria Design System v1.0*
*Intelligence Infrastructure —
Mission-Driven Organizations*
