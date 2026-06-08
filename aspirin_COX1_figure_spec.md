# FIGURE SPEC: Aspirin Irreversibly Inhibits Cyclooxygenase-1 (COX-1)
# File: aspirin_COX1_figure_spec.md
# Purpose: Full reproduction spec for imageGen skill / Claude Code
# Panels: Title + 4-step mechanism row + Bottom summary bar

---

## 1. FIGURE OVERVIEW

**Subject:** Mechanism by which aspirin irreversibly inhibits COX-1 via acetylation of Ser530
**Figure type:** Multi-step mechanistic pathway diagram, educational/publication quality
**Overall layout:** Three horizontal tiers stacked vertically
  - Tier 1: Title block (full width)
  - Tier 2: 4-step mechanism row (full width, equal panels)
  - Tier 3: Bottom summary bar (full width, two-section)
**Aspect ratio:** Wide landscape (~4:1 width:height for main row, full figure ~3:1)
**Background color:** #F0F2F8 (very light cool blue-gray, NOT pure white)
**Design language:** Clean, modern educational schematic. Publication-quality. Resembles textbook biochemistry illustration. No photorealistic elements except the stylized protein surface blobs.

---

## 2. GLOBAL STYLE GUIDE

### Typography
- **Font family:** Clean sans-serif — Inter, Helvetica Neue, or equivalent
- **Main title:** Bold, large, deep navy #1C2B4A
- **Subtitle:** Italic, regular weight, medium slate-blue #607090
- **Step labels:** Bold, dark navy #1C2B4A, two lines, center-aligned, ~16–18pt equivalent
- **Residue labels (Ser530):** Regular or italic, purple #7B52AB, ~11pt
- **Residue labels (His513):** Regular or italic, blue #2563A8, ~11pt
- **Chemical atom labels (CH₃, O, OH, COOH):** Small, dark navy, inline with structure
- **Section headers (bottom bar):** Bold, blue #2563A8
- **Callout box header:** Bold, purple #7B52AB
- **Callout box body:** Regular, dark navy #2A3A5A, ~11pt

### Color Palette (complete)
| Token | Hex | Usage |
|---|---|---|
| bg-main | #F0F2F8 | Figure background |
| bg-panel-bottom | #EEF3FB | Bottom bar background |
| navy-dark | #1C2B4A | Primary text, step badges, arrows |
| navy-mid | #2A3A5A | Molecular sticks, body text |
| blue-label | #2563A8 | His513 label, section headers, "Aspirin" box title |
| blue-border | #6B9FD4 | Box borders, panel borders |
| blue-dots | #4A7ABF | Prostaglandin dots (normal) |
| blue-protein | #CBD5E8 | Protein surface fill |
| blue-protein-alt | #8FA8C8 | COX-1 blob (bottom bar) |
| slate-subtitle | #607090 | Figure subtitle |
| purple-label | #7B52AB | Ser530 label, callout border/header |
| purple-bg | #F0EAF8 | Callout box background |
| red-oxygen | #CC2222 | Oxygen atoms, inhibition arrows, X mark |
| red-label | #CC2222 | "Aspirin" label in bottom bar |
| green-salicylate | #33AA33 | Salicylic acid structure and labels |
| gray-faded | #AAAAAA | Faded arrows, divider lines |
| white | #FFFFFF | Step badge numbers, COX-1 text in blob |

### Line Weights & Styles
- Molecular sticks (main): 2–2.5px solid, navy-mid
- Dashed interaction lines (H-bond): 1.5px dashed, colored per residue (red or blue)
- Transition arrows (between steps): 2px solid black, standard arrowhead
- Mechanism arrows (curly): 1.5–2px solid black, curved with arrowhead at tip
- Inhibition arrow (⊣): 2px solid red, flat perpendicular terminator
- Red X on COX-1: 3–4px solid red, bold diagonal cross
- Box borders: 1.5–2px solid, color per context
- Faded pathway arrow: 2px, gray #AAAAAA

---

## 3. LAYOUT STRUCTURE

```
┌──────────────────────────────────────────────────────────────┐
│                        TITLE BLOCK                           │
│              (centered, full width, ~15% height)             │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│   STEP 1     │   STEP 2     │   STEP 3     │   STEP 4        │
│  [Aspirin    │  [Nucleoph.  │  [Acetyl     │  [Irreversible  │
│   box +      │   Attack]    │   Transfer]  │   Acetylation]  │
│   protein]   │              │              │   + callout     │
│              │              │              │                 │
│   (~60% height of main row) │              │                 │
├──────────────────────────┬───────────────────────────────────┤
│   BOTTOM BAR LEFT        │   BOTTOM BAR RIGHT                │
│   "Physiological Pathway"│   "Effect of Aspirin"             │
│   (~15% height)          │                                   │
└──────────────────────────┴───────────────────────────────────┘
```

- Step panels are separated by solid black horizontal arrows at vertical midpoint
- Steps 1 and 2 share the left half of the main row; Steps 3 and 4 the right half
- Aspirin box (Step 1 area) sits at the far left, vertically centered
- Bottom bar has a vertical dashed divider at its horizontal midpoint

---

## 4. ELEMENT LIBRARY (Reusable Components)

### A. Step Badge
- Filled circle, ~24–28px diameter
- Fill: navy-dark #1C2B4A
- Number: bold white, centered, ~14pt
- Positioned top-left of each step's protein panel

### B. Protein Surface Blob
- Organic rounded blob / cloud silhouette (not a perfect circle or rectangle)
- Fill: blue-protein #CBD5E8
- Subtle shading: slightly darker at edges, lighter at center cavity
- Has a central groove/cavity where ligand sits
- Approximate size: ~200×220px per step panel
- The blob has an irregular perimeter with bumps — resembles a protein surface cross-section

### C. Ser530 Residue
- Stick model: 2 carbons of side chain + terminal oxygen
- Sticks: navy-mid #2A3A5A, 2px
- Terminal O (hydroxyl or acetylated): red #CC2222, filled circle ~6px
- Enters frame from top of protein blob
- Label: "Ser530" in purple #7B52AB, positioned top-left near residue

### D. His513 Residue
- Imidazole ring: 5-membered ring, stick model
- Sticks: medium blue #4A6A9A, 2px
- Positioned at bottom of protein blob cavity
- Label: "His513" in blue #2563A8, bottom-center

### E. Blue Dashed Line (His513 interaction)
- Color: #4A7ABF, dashed 1.5px
- Connects His513 imidazole upward toward aspirin ring
- Persists through Steps 1–4 unchanged

### F. Red Dashed Line (Ser530 H-bond)
- Color: #CC2222, dashed 1.5px
- Connects Ser530 O to aspirin –OH
- Present in Step 1 only (replaced by solid bond in Steps 3–4)

### G. Horizontal Transition Arrow
- Solid black #1A1A1A
- Standard filled arrowhead
- Positioned at vertical midpoint between step panels
- Width: ~30–40px

### H. Curly Mechanism Arrow
- Solid black, curved, with filled arrowhead at tip
- 1.5–2px stroke
- Used in Step 2 to show electron flow from Ser530 O → carbonyl C
- Organic chemistry style (not a circle, a curved sweep)

### I. Inhibition Bar Arrow (⊣)
- Horizontal red line with flat vertical bar at right end
- Color: red #CC2222, 2px
- Indicates pharmacological inhibition

### J. COX-1 Blob (bottom bar)
- Same organic cloud shape as protein surface but smaller, used as enzyme icon
- Fill: blue-protein-alt #8FA8C8
- White bold "COX-1" text centered inside
- Normal version: no overlay
- Inhibited version: same blob + large red X (#CC2222) overlaid diagonally

### K. Prostaglandin Dot Cluster
- 4–5 circles, slight size variation, loosely clustered
- Normal: color #4A7ABF, medium size
- Reduced (inhibited): 2–3 circles, more muted color ~#8FA8C8, slightly smaller

---

## 5. PANEL-BY-PANEL SPEC

---

### PANEL 0: TITLE BLOCK

**Layout:** Full width, ~15% of total figure height, centered content

**Element 1 — Main title**
- Text: "Aspirin Irreversibly Inhibits Cyclooxygenase-1 (COX-1)"
- Style: Bold, sans-serif
- Color: #1C2B4A (navy-dark)
- Size: ~22–24pt equivalent
- Alignment: Center

**Element 2 — Subtitle**
- Text: "Acetylation of Ser530 in the Active Site"
- Style: Italic, regular weight, same font
- Color: #607090 (slate-subtitle)
- Size: ~14–15pt equivalent (~62% of title size)
- Alignment: Center
- Spacing: ~1.3× line height below title

---

### PANEL 1: STEP 1 — "Substrate (Aspirin) Enters Active Site"

**Step badge:** "1" (see Element Library A)

**Step label text (two lines, bold navy):**
  Line 1: "Substrate (Aspirin)"
  Line 2: "Enters Active Site"

**Sub-element: Aspirin Box (far left of panel)**
- Rounded rectangle, white fill #F5F8FF, border blue #6B9FD4, ~2px
- Header: "Aspirin" — bold blue #2563A8, centered
- Sub-header: "(acetylsalicylic acid)" — regular, dark gray, smaller, centered
- Chemical structure (2D skeletal, dark navy lines):
  - Benzene ring (regular hexagon) at center
  - Upper-right branch: C=O (double bond up) + OH (single bond right) → carboxylic acid
  - Lower-left branch: O (ether) → C=O (double bond) → CH₃ → acetyl ester
  - All lines dark navy, no colored atoms in this 2D view
- Arrow: solid black → pointing right from box toward protein blob

**Protein blob:** (see Element Library B), Steps 1 style

**Ser530:** (see Library C)
- In Step 1: –OH form (not yet acetylated)
- Red dashed line from Ser530 O downward to aspirin –OH (see Library F)

**Aspirin in cavity (stick model):**
- Benzene ring, dark navy sticks
- Carboxylic acid branch (upper): C=O with red O, –OH with red O
- Acetyl ester branch (lower-right): –O–C(=O)–CH₃, red O atoms, CH₃ label
- The –OH of carboxylic acid faces upward toward Ser530
- Oriented roughly vertically in the cavity

**His513:** (see Library D & E) — blue dashed line connecting upward to aspirin ring

**Transition arrow →** (see Library G) — pointing right to Step 2

---

### PANEL 2: STEP 2 — "Nucleophilic Attack by Ser530"

**Step badge:** "2"

**Step label text:**
  Line 1: "Nucleophilic Attack"
  Line 2: "by Ser530"

**Protein blob:** same style

**Ser530:** same –OH form, red O
- Red dashed line to aspirin O still present but now paired with curly arrow
- **Curly mechanism arrow #1:** from Ser530 O → toward carbonyl C of aspirin acetyl group (downward sweep)
- **Curly mechanism arrow #2:** from C=O double bond of acetyl → (electron pair movement)
- Both arrows: solid black, 1.5–2px, organic chemistry curly style

**Aspirin in cavity:** same as Step 1
- Acetyl ester (–O–C(=O)–CH₃) prominently shown
- The ester O (connecting ring to acetyl) is the site of attack

**His513:** same, blue dashed line maintained

**Transition arrow →** pointing right to Step 3

---

### PANEL 3: STEP 3 — "Acetyl Transfer & Leaving Group Departure"

**Step badge:** "3"

**Step label text:**
  Line 1: "Acetyl Transfer &"
  Line 2: "Leaving Group Departure"

**Incoming arrow ←** from left (Step 2)

**Protein blob:** same style, left edge may be slightly cropped

**Ser530:** red O shown
- Acetyl group in **transitional state**:
  - Ser530–O–C(=O)–CH₃ forming above
  - Bottom O of old ester linkage: dashed/thin line indicating breaking bond
  - CH₃ label visible
- Label "Ser530" in purple

**His513:** same, blue dashed line maintained

**Salicylic acid departure element (floating, between Panels 3 and 4):**
- 2D skeletal structure drawn entirely in green #33AA33:
  - Benzene ring (hexagon)
  - C=O at top position (carbonyl, =O drawn in green)
  - Two –OH substituents on ring at ortho/para positions
- Black arrow → pointing from protein toward this structure
- Labels below structure, all in green #33AA33:
  - "Salicylic acid" — bold, ~13pt
  - "(2-hydroxybenzoic acid)" — regular, ~11pt, parenthetical
  - "Leaves active site" — regular or italic, ~11pt

**Transition arrow →** pointing right to Step 4

---

### PANEL 4: STEP 4 — "Irreversible Acetylation of Ser530"

**Step badge:** "4"

**Step label text:**
  Line 1: "Irreversible Acetylation"
  Line 2: "of Ser530"

**Protein blob:** same style, slightly more compact

**Ser530:**
- Acetyl group **covalently and permanently attached** — all solid bonds:
  - Ser530 backbone → O (red) → C(=O) → CH₃
  - CH₃ label visible
  - NO dashed lines above (bond is now covalent)
- Label "Ser530" in purple
- **Small white arrow** on protein surface near entrance, indicating blocked substrate access

**No aspirin ring present** — salicylate portion has fully departed; only acetyl–Ser530 remains

**His513:** same imidazole, blue dashed line, label in blue

**Callout box (right of protein, vertically centered):**
- Rounded rectangle
- Border: purple #7B52AB, ~2px
- Background: light lavender #F0EAF8
- Header: "Irreversible Inhibition" — bold, purple #7B52AB
- Body text (regular, dark navy #2A3A5A, ~11pt):
  "Covalent acetylation of Ser530 prevents arachidonic acid binding and cyclooxygenase activity."

---

### PANEL 5: BOTTOM SUMMARY BAR

**Container:**
- Wide rounded rectangle, full figure width, ~15% of total height
- Background: #EEF3FB
- Border: #6B9FD4, ~1–2px
- Vertical dashed divider at horizontal midpoint: #AAAAAA, dashed 1.5px

---

**LEFT SECTION — "Physiological Pathway"**

Section header: "Physiological Pathway" — bold, #2563A8, top-left

Flow (left → right):

1. **Arachidonic acid** (2D skeletal, dark navy):
   - Long fatty acid chain (C20)
   - 4 cis double bonds (shown as 4 zigzag double-bond breaks in chain)
   - Terminal –COOH group at right
   - Label below: "Arachidonic acid" — regular, dark navy, small

2. **Black arrow →**

3. **COX-1 blob icon** (see Library J, normal version):
   - Organic cloud shape, fill #8FA8C8, white bold "COX-1" text

4. **Black arrow →**

5. **Prostaglandin cluster** (see Library K, normal version):
   - 4–5 blue circles #4A7ABF, loose cluster
   - Labels below:
     - "Prostaglandins" — regular/bold, dark navy
     - "(physiological functions)" — lighter, smaller

---

**RIGHT SECTION — "Effect of Aspirin"**

Section header: "Effect of Aspirin" — bold, #2563A8, top-left of right section

Flow (left → right):

1. **Aspirin tablet icon:**
   - Circle, light gray fill, diagonal score line through center
   - Slight bevel/3D appearance
   - Label ABOVE: "Aspirin" — bold red #CC2222

2. **Inhibition bar arrow ⊣** (see Library I):
   - Red #CC2222, horizontal with flat bar at right end

3. **COX-1 blob (inhibited)** (see Library J, inhibited version):
   - Same shape/fill as normal
   - Large red X (#CC2222, 3–4px, bold) overlaid diagonally

4. **Faded gray arrow →:**
   - Color #AAAAAA, standard arrowhead
   - Indicates reduced/blocked flow

5. **Prostaglandin cluster (reduced)** (see Library K, reduced version):
   - 2–3 circles, muted blue-gray ~#8FA8C8, slightly smaller

6. **Text label (right of reduced cluster):**
   - "↓ Prostaglandin production" — ↓ glyph + bold/regular dark navy
   - "(anti-inflammatory, analgesic," — regular, dark navy, ~11pt
   - "antipyretic effects)" — continuation on next line

---

## 6. RENDERING NOTES

### Protein Surface Blobs
- Should NOT be perfect ovals — must be organic/irregular with bumps and indentations
- The central cavity/groove should be visible as a slightly lighter or recessed area
- Use radial gradient or subtle shading: center slightly lighter, edges slightly darker
- Color base: #CBD5E8 in main panels, #8FA8C8 in bottom bar icons

### Chemical Structures
- All stick structures use consistent bond angle conventions (120° for sp2, 109° for sp3)
- Double bonds drawn as two parallel lines
- Oxygen atoms in 3D stick models colored red (#CC2222)
- Oxygen atoms in 2D skeletal structures (Aspirin box, salicylic acid) follow:
  - Aspirin 2D box: all lines dark navy (no atom coloring)
  - Salicylic acid departure: all lines and atoms green #33AA33
  - 3D stick models inside protein blobs: O atoms red, C backbone navy

### Arrows
- Transition arrows between panels: positioned at vertical center of the mechanism row
- Curly arrows (mechanism): must be clearly curved, not straight — organic chemistry convention
- The ⊣ inhibition symbol: the flat terminator bar is perpendicular to the line, ~20px tall

### Step Numbering
- Steps numbered 1–4 left to right
- Badge positioned top-left corner of each protein panel area
- Badge and label are visually grouped (label immediately right of or below badge)

### Spacing
- Equal horizontal spacing between the 4 main step panels
- Consistent vertical alignment of protein blobs across all 4 steps
- Residue labels maintain consistent position relative to their residue across all steps

### Hierarchy Summary
- Layer 1 (background): figure bg #F0F2F8
- Layer 2: protein blobs
- Layer 3: molecular sticks inside blobs
- Layer 4: dashed interaction lines
- Layer 5: mechanism arrows, text labels
- Layer 6: step badges, callout boxes
- Layer 7: transition arrows between panels

---

## 7. FIGURE DIMENSIONS (recommended)

- Full figure: 1400–1600px wide × 500–600px tall
- Title block: full width × ~80px
- Main mechanism row: full width × ~360px
- Bottom bar: full width × ~100px
- Individual step panel width: ~280–320px
- Protein blob dimensions: ~180px wide × ~200px tall
- Bottom bar height: ~90px
- Margins: ~20px all sides

---

END OF SPEC
# aspirin_COX1_figure_spec.md
