---
name: imageGen
description: Generate publication-style schematic scientific figures — pathway diagrams, reaction schemes, experimental workflows, cellular schematics, and mechanism cartoons — from a natural-language request. Use when the user asks to draw, diagram, or sketch a biological pathway or signalling cascade, a chemical reaction scheme, an experimental protocol workflow, a labelled cell schematic, or a reaction mechanism cartoon. Produces vector-first schematic figures (SVG/PNG/PDF) — not photorealistic images and not plots of real data.
---

# imageGen — Scientific Figure Generation

Generate publication-style schematic figures — pathway diagrams, reaction
schemes, experimental workflows, cellular schematics, mechanism cartoons, and
multi-panel graphical abstracts — from a natural-language request.

Figures are **vector-first and schematic**: clean SVG/PNG/PDF assembled from a
curated library of biology- and chemistry-aware primitives. This is not an
image generator and not a data-plotting tool.

---

## Environment — Claude Code (native Bash + file tools)

**This skill runs in Claude Code**, which has native execution tools — there
is no osascript, no "Control your Mac" MCP, and no `copy_file_user_to_claude`
hop. Use:

- **`Bash`** for every command (validate / render / verify). It runs directly
  on the user's Mac.
- **`Read`** to read fixtures and to display the rendered PNG inline in chat.
- **`Write`/`Edit`** to create the spec or IR file.

Paths: use the venv Python `~/Desktop/.venv/bin/python` (the `imageGen`
package is installed there). The repo root is `~/Desktop/imageGen-v2.6/`;
fixtures cited as `tests/fixtures/<file>` live at
`~/Desktop/imageGen-v2.6/tests/fixtures/<file>`. Write throwaway specs and
output to `~/Desktop/scratch/`. `~` works fine in the Bash tool.

> **If you are a chat assistant *without* a shell** (e.g. claude.ai with no
> Claude Code session): do **not** try to execute anything. Your job is to
> **author the YAML spec** (Steps 1–3) and hand the user the single command
> in Step 4 to run in Claude Code. You are excellent at composing the spec;
> let Claude Code do the rendering.

---

## Quickest path (one command)

The whole pipeline collapses to four actions — three of them are tool calls
you already have, and the render+verify is a **single** Bash command:

```
1. Classify the request + Read the matching fixture (Step 1).
2. Write a small YAML spec (Step 3).
3. Bash:  ~/Desktop/.venv/bin/python -m imageGen render-spec SPEC.yaml \
              -o OUT.png --verify
4. Read OUT.png to show it inline (Step 5).
```

`render-spec` builds the IR through the schema (so validation happens for
free) and `--verify` runs all three verifiers and prints a one-line report —
no separate validate or verify round-trip.

---

## When to trigger this skill

Use imageGen when the user asks for a **schematic scientific figure**:

- A signalling or metabolic **pathway** ("show the MAPK cascade", "diagram how
  insulin signalling works")
- A **reaction scheme** ("draw the oxidation of ethanol", "show this SN2 step")
- An experimental **workflow** ("a figure of the western blot protocol")
- A **cellular schematic** ("a labelled eukaryotic cell", "where these
  proteins localise")
- A **mechanism cartoon** ("cartoon the catalytic mechanism")
- A multi-panel **graphical abstract** combining the above

## When NOT to trigger

Decline (politely, see *Refusal scripts*) and suggest the right tool when the
user wants:

- A **photorealistic** image or artistic illustration — this skill draws
  schematics only.
- A **plot of real measured data** (bar chart, dose-response curve, kinetics)
  — use a plotting library on the actual dataset.
- A **3D molecular structure** — defer to PyMOL or a structure viewer.
- A figure whose request **cannot be classified** into one of the five
  archetypes below.

---

## Mandatory workflow

Follow these steps in order. Do not skip the IR or the verification step.

### Step 1 — Classify and read fixture (locked gate)

Classify the request into exactly one archetype (see *Archetypes*). If none
fit, refuse.

**Immediately after classifying, read the corresponding fixture file before
doing anything else.** Do not write any IR until you have read the fixture and
confirmed its structure matches your plan.

Archetype → required fixture file:

| Archetype | Fixture file |
|---|---|
| `pathway` | `gpcr_signaling.json` |
| `reaction_scheme` | `oxidation_reaction.json` |
| `workflow` | `western_blot_schematic.json` |
| `cellular_schematic` | `cellular_schematic.json` |
| `mechanism_cartoon` | `showcase/aspirin_cox1_v3_acceptance.json` — a **tier** figure (note: lives under `showcase/`, not `tests/fixtures/`); read it, then see *Tier figures* below |
| multi-panel figure | `three_panel_workflow.json` **AND** `graphical_abstract_mrna_vaccine.json` |

Read it with the **`Read`** tool. Leaf and multi-panel fixtures live at
`~/Desktop/imageGen-v2.6/tests/fixtures/<file>`; the `mechanism_cartoon` tier
fixture is at `~/Desktop/imageGen-v2.6/showcase/aspirin_cox1_v3_acceptance.json`.

### Step 2 — Plan and output confirmation block

Before writing any JSON, output the following confirmation block as visible
text in your response:

```
Archetype: <selected archetype> — because <one-sentence reason>
Fixture(s) read: <filename(s)>, confirmed structure matches plan
Entity count per panel: <N> (ring layouts: up to ~12 is fine; DAG/spring: aim ≤7, collapse only if verifier warns)
Label safety: all entity and relation labels are ASCII-only — confirmed
```

**For a `mechanism_cartoon` (tier figure)** the confirmation block is shorter —
there are no per-panel entity counts; instead confirm the tier plan:

```
Archetype: mechanism_cartoon — because <one-sentence reason it is mechanistic>
Fixture read: showcase/aspirin_cox1_v3_acceptance.json, confirmed tier structure matches plan
Tier plan: <title tier> + <N>-scene mechanism row (scene_row) [+ summary scene_row]
Slots per scene: molecule(s) + residue(s)/glyph(s); sizing is automatic (no hand-set scale)
Label safety: all labels ASCII-only — confirmed
```

Then skip to *Tier figures (the V3 scene chassis)* below and author the `tiers`
IR JSON directly; Steps 3–4 (smiles_map / tuple-spec) are for leaf figures only.

Do not proceed to Step 3 until this block is written. For **ring layouts**
(cycles, metabolic loops) do NOT collapse biochemically distinct nodes — the
ring engine handles up to ~12 nodes legibly. For spring/DAG layouts, aim for
≤7 entities per panel and collapse only when the layout engine actually warns
about label overlap. Never merge distinct metabolites or proteins unless the
user explicitly asks for a simplified schematic.

### Step 3 — smiles_map (reaction_scheme only)

For `reaction_scheme` figures only: build a `smiles_map`,
`{entity_id: "SMILES"}`, covering every entity. You supply the SMILES from
chemical knowledge (e.g. ethanol → `"CCO"`). It is a render argument, not an
IR field. **Write** it to its own JSON file (e.g.
`~/Desktop/scratch/smiles.json`).

### Step 4 — Write the spec

**Write** a small YAML spec to `~/Desktop/scratch/figure.yaml`. The spec is a
flat description piped through the builder, so entities and relations are
positional lists — far less to type than raw IR JSON:

```yaml
archetype: pathway
style: nature              # cell_press (default) | nature | acs
title: MAPK cascade        # optional
entities:
  - [ras, protein, Ras]            # [id, type, label]  (+ optional 4th: compartment id)
  - [raf, kinase, Raf]
  - [mek, kinase, MEK]
relations:
  - [ras, activates, raf]          # [source, type, target]  (+ optional 4th: label)
  - [raf, phosphorylates, mek]
compartments:                      # optional
  - [cyto, cytoplasm, Cytoplasm]   # [id, type, label]
```

See *IR reference* for every type and field. Labels must be **ASCII-only**
(see *Step 2*). If you'd rather hand-write full IR JSON, that works too —
`render-spec` accepts a `.json` spec with the same shape.

### Step 5 — Render + verify (one command)

Run **one** `Bash` command. `render-spec` builds and validates the IR through
the schema, renders the PNG (and a sibling `.svg`), and `--verify` runs all
three verifiers and prints a one-line report:

```bash
~/Desktop/.venv/bin/python -m imageGen render-spec ~/Desktop/scratch/figure.yaml \
    -o ~/Desktop/scratch/figure.png --verify --autocrop \
    [--smiles-map ~/Desktop/scratch/smiles.json]   # reaction_scheme only
```

`--autocrop` trims dead margin from the shipped figure **in place**, so it ships
tight by default — unlike the older `--crop` (Step 7), which writes a separate
`*_cropped` sibling and leaves the original untouched.

- A **`pydantic.ValidationError`** means the spec is malformed — read the
  message, fix only what it names (common: a relation referencing an unknown
  entity id, an `entity` 4th-element naming a missing compartment, mixing
  `entities` with `panels`), and re-run.
- The printed **`VERIFY:`** line reports `semantic` / `legibility` /
  `convention`. A `semantic=FAIL` or `convention=FAIL` is a real defect — fix
  the spec and re-render. `legibility` reports `needs_crop` (informational)
  and only FAILs on genuinely illegible overlap.
- Dense figures no longer crash: unplaceable labels shrink/nudge or land with
  a tolerated overlap (a `UserWarning` is printed). Add `--strict-labels` to
  fail loud instead, or `--no-labels` to suppress labels entirely.

### Step 6 — Present

**Read** `~/Desktop/scratch/figure.png` with the `Read` tool to display it
inline, then add a one- or two-sentence caption describing what it depicts.
Do **not** use `open`, `osascript`, Preview, or any external viewer. If any
element is illustrative/schematic rather than measured data, say so.

### Step 7 — Crop fallback (rarely needed)

With `--autocrop` in Step 5 the shipped figure is already trimmed in place, so
`VERIFY:` should report **`needs_crop=False`**. Only if you skipped `--autocrop`
or the displayed image still floats in whitespace: present the full figure
first, then **ask the user**: *"Want me to crop in tighter on the figure?"*
Do not crop unprompted.

If they say yes, re-run Step 5's command with `--crop` added. It writes a
sibling `~/Desktop/scratch/figure_cropped.png` (the original is kept) reframed
onto the content with a comfortable margin. **Read** that sibling to show it.

```bash
~/Desktop/.venv/bin/python -m imageGen render-spec ~/Desktop/scratch/figure.yaml \
    -o ~/Desktop/scratch/figure.png --crop
# add --crop-keep-aspect to keep a uniform 4:3 shape (crops less)
```

`--crop` fits the content's own shape (a wide pathway becomes a wide, short
image) — that's what actually removes whitespace. `--crop-keep-aspect` keeps
the canvas proportions but, because layouts fill a full dimension, usually
crops little.

---

## Archetypes

| Archetype (`archetype` value) | Use for | Shape | Needs `smiles_map` |
|---|---|---|---|
| `pathway` | Signalling / regulatory networks: entities connected by typed relations, optionally grouped into compartments | Leaf | No |
| `reaction_scheme` | A chemical transformation: reactants → products with reagents/conditions | Leaf | **Yes** |
| `workflow` | Step-by-step experimental procedures | Leaf or panels | No |
| `cellular_schematic` | A cell with compartments and localised entities | Leaf | No |
| `mechanism_cartoon` | A reaction/process **mechanism** at the molecular level — arrow-pushing, active-site events, transition states, multi-step catalysis | **Tier** (V3 scene chassis) | No (SMILES live inline in each slot) |

**Two shapes, two authoring models.** A **leaf** figure (`pathway`,
`reaction_scheme`, `workflow`, `cellular_schematic`) is flat `entities` +
`relations` laid out as boxes-and-arrows by the graph engine — authored with the
tuple-shorthand spec (Steps 1–6 below). A **tier** figure (`mechanism_cartoon`,
and *any* mechanism / catalytic / active-site request) is the **V3 scene
chassis**: `tiers → scenes → slots` (real molecules, residues, blobs, glyphs)
placed by relative anchoring, with atom-anchored curly/H-bond arrows. Tier
figures are authored as **IR JSON carrying a `tiers` list** — see *Tier figures
(the V3 scene chassis)* below, which **replaces** Steps 2–4 for this archetype.
`render_figure` dispatches automatically on whichever container is populated
(`entities`/`relations` vs `tiers`); the render+verify command in Step 5 is
identical for both.

A multi-panel **graphical abstract** is a `Figure` with `panels` — each panel's
`content` is itself a leaf `Figure` of any archetype.

> **Don't downgrade a mechanism to a leaf pathway.** Boxes-and-arrows with
> `activates`/`inhibits` edges cannot show arrow-pushing, a residue attacking a
> bond, or a transition state. If the request is mechanistic, it is a **tier**
> figure — author `tiers`, not `entities`.

---

## Tier figures (the V3 scene chassis)

`mechanism_cartoon` figures are authored as a **tier figure**: a top-level
`tiers` list instead of `entities`/`relations`. Each tier is a full-width
horizontal band, stacked top-to-bottom in list order. This is the only way to
render molecular mechanisms (real structures, residues, atom-anchored arrows) —
the leaf graph engine cannot.

**Author the IR JSON directly** (the tuple-shorthand spec is leaf-only). Write a
`.json` file with `archetype: "mechanism_cartoon"` + `tiers`, then render it with
the **same Step 5 command** — `render-spec` accepts full IR JSON unchanged
(`--smiles-map` is *not* used; each molecule slot carries its own `smiles`).

### The anatomy of a tier figure

```
Figure.tiers = [
  Tier(role="title",     …)   # typography band: label + subtitle
  Tier(role="scene_row", …)   # a row of scenes — the mechanism steps
  Tier(role="scene_row", …)   # optional summary band (also scene_row)
]
```

A **`scene_row`** tier holds `scenes` (a left-to-right row), optional `rails`
(named reference lines) and `transitions` (cross-scene arrows). Each **`scene`**
holds `slots` (the things drawn), `attach` (relative placement), and `connect`
(intra-scene edges). **A slot never gets an absolute position** — you anchor it
to another slot and the solver places it.

### Tier — fields

| Field | Notes |
|---|---|
| `id` | unique; no `.` or `__` |
| `role` | `title` (label+subtitle), `scene_row` (holds scenes). **Use `scene_row` for *any* band with content, including a summary band** — style it via `style.band_fill`. |
| `label` / `subtitle` | text (title tier); `label` also names a scene_row band |
| `height_frac` | fraction of canvas height, `(0,1]`; omit to auto-size by role |
| `style` | band styling, e.g. `{"band_fill": "#F0F2F8"}` |
| `scenes` | list of `Scene` (scene_row) |
| `step_sequence` | *alternative* to `scenes`: one base scene + per-step deltas (auto-expands to one scene per step). Use for state-diff stories where most slots are unchanged between steps. |
| `rails` | named lines: `{"name":"mid","axis":"y","at":0.5}` — `at` is a 0–1 fraction of the cross-axis |
| `transitions` | cross-scene arrows (`TierEdge`) |

### Scene — fields

| Field | Notes |
|---|---|
| `id` | unique within the tier |
| `badge` | small corner number (e.g. `"1"`, `"2"` for step order) |
| `label` | scene caption (placed below the scene) |
| `slots` | the placeable primitives (below) |
| `attach` | relative-placement constraints (below) |
| `connect` | `SceneEdge`s between slot anchors (below) |
| `style` | scene-level style cascade base |

### Slot — `kind` and what it needs

A slot is one drawn primitive. **Molecule sizing is automatic** — every
structure in the figure is rendered at one consistent bond length. Do **not**
hand-tune `scale` on molecules/residues to make them fit; `scale` is only for
deliberately shrinking a glyph/blob.

| `kind` | Renders | Required style | Anchors it exposes |
|---|---|---|---|
| `molecule` | 2-D skeletal structure | `style.smiles` | `a{map}` per SMILES atom-map (`[C:1]`→`a1`); `atom0…atomN`; `bond_<x>_<y>` (bond midpoint); `lp_<x>` (lone pair); `center`; + any name you give in `style.anchor_names` |
| `residue` | an amino-acid side chain with an open valence | `style.residue` | `a1` (the reactive terminal atom), `lp_a1` (its lone pair) |
| `glyph` | a registry icon | `style.glyph` | `center` |
| `blob` | organic protein surface with a binding pocket | (none) | `center`, `cavity_center`, `cavity_top`, `cavity_bottom` |
| `text` | free label | — (uses `label`) | `center` |

- **`molecule` `style`:** `smiles` (required); `anchor_names` `{ "1": "carbonylC" }`
  maps SMILES atom-map numbers → human anchor names (so a `connect` ref reads
  `sub.carbonylC` instead of `sub.a1`); per-element colour overrides like
  `chem_atom_O`, `chem_bond_stroke`; `label_font_color`.
- **`residue` `style.residue`:** a named side chain — `ser`, `his`, `tyr`, `cys`,
  `lys` (or the COX-1 aliases `ser530`/`his513`) — **or** a raw SMILES carrying a
  mapped reactive atom (e.g. `"*CO[C:1](=O)C"` for an acetylated serine; `*` is
  the backbone attachment, suppressed in the drawing).
- **`glyph` `style.glyph`:** any registered primitive name — e.g.
  `protein_blob`, `pg_cluster`, `tablet`, plus the lab/cell/organelle glyph names
  from the leaf *Glyph overrides* table. `scale` (e.g. `0.6`) shrinks it; `blob_fill`,
  `pg_fill`, `reduced` are glyph-specific.

### Attach — relative placement

`{ "child": "ser", "parent": "asp", "edge": "top", "offset": [0, -34] }` places
`ser` at `asp`'s **top** edge, nudged by `(dx, dy)`. `parent: null` (or omitted)
attaches to the scene frame. `edge` ∈ `top` `bottom` `left` `right` `center`,
or `cavity_top` / `cavity_bottom` / `cavity_center` to drop a child *inside* a
parent blob's pocket. `offset` is the only explicit number — everything else is
solved, and the solver spreads co-located slots so they don't overlap.

### SceneEdge (`connect`) — intra-scene arrows

`{ "from_anchor": "ser.lp_a1", "to_anchor": "sub.carbonylC", "type": "curly",
"style": {"curl":"cw","bow":22} }`. Anchors are `slot_id.anchor`. `type` ∈
`dashed` (interaction/forming bond), `hbond`, `curly` (arrow-pushing — point it
from a real lone-pair/bond anchor), `departs` (leaving group), `transition`,
`binds`, `activates`, `inhibits`, `generic`. Curly-arrow style: `curl`
(`cw`/`ccw`), `bow` (curvature), `arc` (`s`/`n`/…); a `dashed` half-bond takes
`style.partial: true`.

### TierEdge (`transitions`) — cross-scene arrows

`{ "from_ref": "s1@right", "to_ref": "s2@left", "type": "transition",
"on_rail": "mid" }`. Endpoints are `scene@edge` (frame edge: `left`/`right`/…),
`scene.slot.anchor`, or `rail:NAME`. `on_rail` clamps both ends to a declared
rail so a row of step-to-step arrows lines up at the same height.

### Worked skeleton (renders + verifies clean)

A two-step mechanism row + summary band. (The full four-step reference is the
fixture `showcase/aspirin_cox1_v3_acceptance.json` — read it.)

```json
{
  "archetype": "mechanism_cartoon",
  "tiers": [
    { "id": "title", "role": "title", "height_frac": 0.14,
      "label": "Serine Nucleophilic Attack", "subtitle": "Active-site acylation" },
    { "id": "mech", "role": "scene_row", "height_frac": 0.6,
      "style": { "band_fill": "#F1F4F0" },
      "rails": [ { "name": "mid", "axis": "y", "at": 0.5 } ],
      "scenes": [
        { "id": "s1", "badge": "1", "label": "Substrate bound",
          "slots": [
            { "id": "sub", "kind": "molecule",
              "style": { "smiles": "CC(=O)NC[C:1](=O)NC",
                         "anchor_names": { "1": "carbonylC" } } },
            { "id": "ser", "kind": "residue", "label": "Ser195",
              "style": { "residue": "ser" } } ],
          "attach": [ { "child": "ser", "parent": "sub", "edge": "top",
                        "offset": [0, -34] } ],
          "connect": [] },
        { "id": "s2", "badge": "2", "label": "Nucleophilic attack",
          "slots": [
            { "id": "sub", "kind": "molecule",
              "style": { "smiles": "CC(=O)NC[C:1](=O)NC",
                         "anchor_names": { "1": "carbonylC" } } },
            { "id": "ser", "kind": "residue", "label": "Ser195",
              "style": { "residue": "ser" } } ],
          "attach": [ { "child": "ser", "parent": "sub", "edge": "top",
                        "offset": [0, -34] } ],
          "connect": [ { "from_anchor": "ser.lp_a1", "to_anchor": "sub.carbonylC",
                         "type": "curly", "style": { "curl": "cw", "bow": 22 } } ] }
      ],
      "transitions": [ { "from_ref": "s1@right", "to_ref": "s2@left",
                         "type": "transition", "on_rail": "mid" } ] }
  ]
}
```

Render it with the Step 5 command (no `--smiles-map`):

```bash
~/Desktop/.venv/bin/python -m imageGen render-spec ~/Desktop/scratch/mech.json \
    -o ~/Desktop/scratch/mech.png --verify --autocrop
```

### What the tier engine does NOT render yet

Stay inside the supported surface — the schema validates more than the renderer
draws:

- **Slot kinds** `box`, `group`, `generic` are accepted by the schema but raise
  `NotImplementedError` at layout. Only `molecule`/`residue`/`glyph`/`blob`/`text`
  draw.
- **Tier roles** `summary_bar` / `band` render a band background only (no inner
  scenes). For a summary with content, use `scene_row` + `style.band_fill`.
- **`Tier.content`** (an embedded leaf Figure inside a band) is not laid out.
- **Attach `edge`** `anchor` / `custom` are not solved — use the face or cavity
  edges above.

---

## IR reference

The IR (intermediate representation) is a `Figure` — a strict, validated
Pydantic model. Unknown fields are rejected. Build it as JSON. The fields below
describe the **leaf** figure (`entities`/`relations`/`panels`); the **tier**
container (`tiers` → `Tier`/`Scene`/`Slot`/`Attach`/`SceneEdge`/`TierEdge`/`Rail`/
`StepSequence`) is documented above in *Tier figures (the V3 scene chassis)*.

### `Figure`

| Field | Type | Required | Notes |
|---|---|---|---|
| `archetype` | archetype value | yes | one of the five above |
| `title` | string | no | |
| `caption` | string | no | |
| `style_preset` | string | no | defaults to `"cell_press"` |
| `entities` | list of `Entity` | no* | |
| `compartments` | list of `Compartment` | no* | |
| `relations` | list of `Relation` | no* | |
| `panels` | list of `Panel` | no* | |
| `tiers` | list of `Tier` | no* | the V3 scene chassis — see *Tier figures* above |
| `annotations` | list of `Annotation` | no | |
| `glossary` | list of `GlossaryEntry` | no | abbreviation key; draws a boxed "Abbreviations" strip below the figure when non-empty |

**\*One container per figure:** a figure is *either* a **leaf** (has
`entities`/`compartments`/`relations`), *multi-panel* (has `panels`), *or* a
**tier** figure (has `tiers`) — never more than one. `render_figure` dispatches
on whichever is populated.

### `Entity`

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | unique within the figure |
| `type` | entity type | yes | see below |
| `label` | string | yes | shown on the figure — ASCII only |
| `location` | string | no | a compartment `id` (must exist) |
| `style` | object | no | per-entity style overrides |

`type` ∈ `protein`, `complex`, `ligand`, `receptor`, `kinase`, `gene`, `rna`,
`metabolite`, `cell`, `organelle`, `equipment`, `sample`, `generic`.

The cellular / method-figure types render as domain icons. The label is
inspected first: a keyword picks a specific glyph automatically — e.g. an
`equipment` labelled "Western blot" or "SDS-PAGE" draws a gel, "96-well plate"
a well plate, "mouse" a mouse; an `organelle` "Nucleus" draws a nucleus, "Golgi"
the Golgi; a `cell` "Neuron" / "T cell" draws the neuron / immune-cell shape.
With no recognised keyword the type default is used: `cell` → a cell outline,
`organelle` → a mitochondrion, `equipment` → a microscope, `sample` → a tube.
Set a `style.primitive` override (below) to force a specific glyph regardless of
the label.

#### Glyph overrides — `style.primitive`

The `type` above picks a default shape. To render an entity with a more
specific glyph, set `style.primitive` to one of the names below — the entity
keeps its `type` (use the closest one) but draws as the chosen glyph. Unknown
names warn and fall back to the type default.

| Theme | `style.primitive` values |
|---|---|
| Proteins / enzymes | `kinase`, `phosphatase`, `gpcr`, `receptor`, `transcription_factor`, `protein_complex`, `antibody` |
| Membrane transport | `ion_channel`, `transporter`, `pump` |
| Subcellular | `ribosome`, `vesicle` (simple sphere), `liposome` (lipid-bilayer ring) |
| Nucleic acids | `gene_helix` (DNA), `rna_helix` (RNA), `mrna_helix` (5' cap + polyA), `primer_helix` (3' arrow) |
| Lab equipment (embedded icons) | `microscope`, `tube`, `well_plate`, `mouse`, `gel` (agarose), `western_blot`, `flask`, `centrifuge` — real Bioicons art (faithful color; see note) |
| Lab equipment (house-style glyph) | `pipette`, `human_figure` (re-traced, themeable), `flow_cytometer`, `sequencer`, `petri_dish`, `syringe` |
| Cell shapes | `cell` (generic), `cell_neuron`, `cell_epithelial`, `cell_immune` |
| Organelles | `mitochondrion`, `nucleus`, `endoplasmic_reticulum`, `golgi`, `lysosome` |
| Chemical structure | `molecule` — 2-D structure; **also set `style.smiles`**. `functional_group` — named callout; **also set `style.functional_group`** (see below) |
| Domain idioms | `voltage_trace` (action-potential V-vs-t plot) |

The **embedded-icon** lab glyphs are real [Bioicons](https://bioicons.com) art
(e.g. an `equipment` labelled "Western blot" auto-renders the blot icon, "Mouse"
the mouse, etc.). They keep their original color and do **not** retheme with
journal style presets. Icons under CC-BY are credited automatically: a small
**Credits** section appears in the figure's info box and a `<output>.credits.txt`
sidecar is written; CC0 icons need no credit. Pass `render_figure(credits=False)`
to drop the on-figure Credits section (the sidecar is still written).

For `molecule`, add a `style.smiles` entry alongside the override: e.g.
`{"id": "glc", "type": "metabolite", "label": "Glucose", "style": {"primitive":
"molecule", "smiles": "C(C1C(C(C(C(O1)O)O)O)O)O"}}`. This renders a single
metabolite's structure *inline in a pathway*; full reaction schemes still use
the `reaction_scheme` archetype + `--smiles-map`. A missing/invalid SMILES
warns and falls back to a label only.

For `functional_group`, set `style.functional_group` to one of `carboxyl`,
`amine`, `phosphate`, `hydroxyl`, `methyl`, `aldehyde`, `ester` — or just name
the group in the entity `label` (e.g. `label: "amine"`) and omit the key. An
unknown group warns and falls back to a label only.

Example: `{"id": "igg", "type": "protein", "label": "IgG", "style":
{"primitive": "antibody"}}`.

### `Compartment`

`id` (unique), `type`, `label`. `type` ∈ `extracellular`, `membrane`,
`cytoplasm`, `nucleus`, `mitochondrion`, `custom`.

### `Relation`

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | string | yes | an entity `id` (must exist) |
| `target` | string | yes | an entity `id` (must exist) |
| `type` | relation type | yes | see below |
| `label` | string | no | ASCII only; omit if panel already has 3 labels |
| `label_side` | `above` \| `below` \| `left` \| `right` | no | which side of the arrow the label prefers; use to split the two labels on a parallel forward/back edge pair. Reciprocal `A→B`+`B→A` labeled pairs auto-separate even without it. |
| `conditions` | `ReactionConditions` or object | no | reaction context |

`type` ∈ `activates`, `inhibits`, `binds`, `translocates`, `phosphorylates`,
`transcribes`, `catalyzes`, `cleaves`, `transports`, `recruits`, `generic`.
Conventions: `activates` → solid filled arrow; `inhibits` → T-bar;
`binds` → double-headed; `translocates` → dashed open head;
`catalyzes` → open-circle terminus; `cleaves` → arrow with a cut-mark;
`transports` → hollow block arrow; `recruits` → dashed line ending in a dot.

### `ReactionConditions` (for `relation.conditions`)

`reagents` (list of strings), `yield_pct` (0–100), `reversible` (bool),
`notes` (string). All optional.

### `Panel` (multi-panel figures)

`id` (unique), `title` (optional), `content` (a nested `Figure`),
`grid` (`[row, col, rowspan, colspan]` — `row`/`col` ≥ 0, spans ≥ 1, panels
must not overlap).

### `Annotation`

`type` ∈ `label`, `caption`, `scale_bar`; `text` (string — ASCII only);
`position` — either `[x, y]` coordinates or a named slot ∈ `top`, `bottom`,
`left`, `right`, `top-left`, `top-right`, `bottom-left`, `bottom-right`,
`center`.

### `GlossaryEntry` (for `figure.glossary`)

`term` (the abbreviation) and `definition` (its expansion). A non-empty
`glossary` auto-draws a boxed "Abbreviations" key in a strip below the figure.
`--verify` advisory-warns about acronyms in labels with no matching `term`
(only when a glossary is present).

### Validators (will reject the IR if violated)

- Entity, compartment, and panel `id`s are unique within a figure.
- Every `relation.source`/`target` references an existing entity.
- Every `entity.location` references an existing compartment.
- One container per figure (leaf / panels / tiers — above). Panel grids must not
  overlap.
- Tier figures: slot ids unique within a scene; `attach`/`connect`/`transition`
  refs must resolve to a declared slot/scene/rail; ids carry no `.` or `__`.

---

## Encoding pitfalls — avoid these

Three mis-encodings silently degrade output. Check the IR against them before
rendering.

**1. Reactions: parallel edges, not a chain.** A single-step multi-product
reaction `A + B → C + D` is **parallel** reactant→product edges — `A→C` and
`B→D` (or `A→C`, `B→C` if both feed one product). Do **not** write a chain like
`A→C, B→C, C→D`: that makes `C` both a target *and* a source, so the engine
reads it as a false intermediate (a multi-step reaction) and routes it
differently. Use a chain `A→B→C` only when `B` is a **genuine** isolated
intermediate in a multi-step sequence.

**2. Decorations are glyphs on a relation, not entity nodes.** A phosphosite,
N-/C-terminus, ubiquitin tag, methyl mark, etc. is **not** its own entity. Model
the modification as the relation between modifier and substrate (e.g. a kinase
`phosphorylates` its target — the "P" badge is drawn automatically). A separate
`"P"`/`"phosphosite"` entity node clutters the graph and breaks layout.

**3. Mechanisms use `mechanism_cartoon`, not `reaction_scheme`.** Arrow-pushing
/ intermediates / transition states → `mechanism_cartoon`. Net transformations
(reactants → products) → `reaction_scheme`.

---

## Style presets

Pass `--style` (or `style_preset` in the IR) to pick a journal aesthetic:

- `cell_press` — soft, friendly, rounded. **Default.**
- `nature` — bolder, geometric, colorblind-safe palette.
- `acs` — monochrome, formal; the chemistry default.

---

## Refusal scripts

When a request falls outside scope, decline plainly and redirect:

- **Fabricated data plot** — "I can't generate a chart that looks like real
  measured data, since that would be misleading. imageGen produces
  schematic figures only. If you have an actual dataset I can help you plot
  it with a plotting library instead."
- **Photorealistic image** — "imageGen draws schematic, vector-style
  scientific figures, not photorealistic images. I can make a clean
  schematic of this if that works for you."
- **3D molecular structure** — "This skill renders 2D schematics. For a 3D
  molecular structure, a tool like PyMOL is the right choice."

---

## Error recovery

### Crowded labels

By default labels never crash the render — an unplaceable label shrinks,
nudges, or lands with a tolerated overlap (you'll see a `UserWarning`). If the
result looks cluttered, improve it rather than accepting it:

1. **Ring layouts:** do not collapse nodes. The ring engine is designed for
   cycles of up to ~12 nodes. If labels overlap, shorten the node labels
   (e.g. "a-Ketoglutarate" → "a-KG") rather than merging nodes.
2. **Spring/DAG layouts:** if any panel has >7 entities *and* the verifier or
   render warns about label overlap, collapse closely related nodes (e.g.
   merge "Gs protein" + "Adenylyl Cyclase" into "Gs/AC").
3. Count labelled relations per panel. Remove labels until ≤3 remain; move
   removed labels into the caption.
4. Still cluttered? Render `--no-labels` and describe the relations in the
   caption.

(`--strict-labels` turns an unplaceable label back into a hard
`LabelPlacementError` if you want the render to fail rather than overlap.)

### ValidationError

Read the full pydantic error message before changing anything. Check:

- Are all `relation.source`/`target` values valid entity `id`s?
- Are all `entity.location` values valid compartment `id`s?
- Is the figure mixing more than one container — `entities`/`relations`,
  `panels`, or `tiers` (only one is allowed)?
- For tier figures: does every `connect`/`attach`/`transition` reference name a
  slot/scene/rail that exists, and is each `slot.kind` one of the rendered kinds
  (`molecule`/`residue`/`glyph`/`blob`/`text`)?

Fix only what the error message identifies, then revalidate before rendering.

### Bash command failure

Do not retry the same command unchanged. Check:

- Python is the venv: `~/Desktop/.venv/bin/python` (bare `python` won't have
  `imageGen` installed).
- The spec file was actually written to disk before the render command runs.
- For `reaction_scheme`, `--smiles-map` is present and covers every entity.

---

## Pointers

- **Primitives** (`imageGen/primitives/`): proteins, membranes, nucleic
  acids, cells, chemistry (RDKit), lab equipment, arrows — assembled
  automatically by the layout engines; you author the IR, not primitives.
- **CLI** (`python -m imageGen`): two modes —
  `render-spec SPEC.{yaml,json} -o OUT` (preferred; builds + validates from a
  flat spec) and the raw `IR_PATH -o OUT`. Shared flags:
  `--style {cell_press,nature,acs}`, `--format {svg,png,pdf}` (else inferred
  from suffix), `--dpi N` (default 300), `--smiles-map FILE.json`,
  `--no-labels`, `--strict-labels`, `--canvas WxH`, `--verify`,
  `--autocrop` (trim the shipped figure in place — preferred),
  `--crop` (+ `--crop-keep-aspect`, `--crop-margin FRAC`; writes a sibling).
- **Builder API** (`imageGen.ir.builder.build`): the same tuple-friendly
  shorthand the spec uses, for calling from Python.
- **Example IRs**: every archetype has a worked example in
  `tests/fixtures/` — **Read** these to pattern-match the shape.

---

## Cookbook

**Before writing any IR, read the fixture file for your archetype (Step 1).**
The fixture is the ground truth for IR structure — do not write JSON from
memory.

Worked examples — each `tests/fixtures/<file>` is a complete, validated IR.
**Read** them at `~/Desktop/imageGen-v2.6/tests/fixtures/<file>`.

1. **"Show the MAPK kinase cascade."** → `pathway`. Entities Ras (protein),
   Raf/MEK/ERK (kinases); relations `activates` then `phosphorylates`.
   See `tests/fixtures/mapk_cascade.json`.

2. **"Diagram a GPCR signalling event across the membrane."** → `pathway`
   with compartments (`extracellular`, `membrane`, `cytoplasm`); entities
   carry `location`. See `tests/fixtures/gpcr_signaling.json`.

3. **"Draw how this drug inhibits its target."** → `pathway` with an
   `inhibits` relation (renders as a T-bar). See
   `tests/fixtures/drug_inhibition.json`.

4. **"Show the oxidation of ethanol to acetaldehyde."** → `reaction_scheme`.
   Two `metabolite` entities, one relation with `conditions`
   (`reagents`, `notes`). Build `smiles_map`
   `{"alcohol": "CCO", "aldehyde": "CC=O"}`. See
   `tests/fixtures/oxidation_reaction.json`.

5. **"Cartoon how aspirin acetylates COX-1 Ser530."** (or any active-site /
   catalytic / arrow-pushing mechanism) → `mechanism_cartoon`, a **tier figure**:
   a title tier + a `scene_row` of mechanism steps (molecule + residue slots,
   curly/H-bond `connect` edges on real atom anchors, rail-aligned `transitions`)
   + an optional summary `scene_row`. Author `tiers` IR JSON — see *Tier figures
   (the V3 scene chassis)*. Reference: `showcase/aspirin_cox1_v3_acceptance.json`.

6. **"A labelled diagram of a eukaryotic cell."** → `cellular_schematic`
   with five compartments and entities localised via `location`. See
   `tests/fixtures/cellular_schematic.json`.

7. **"A three-step western blot workflow figure."** → multi-panel
   `workflow`: a `Figure` with three `panels` on a `[0,c,1,1]` grid, each
   panel's `content` a small `workflow` figure. See
   `tests/fixtures/three_panel_workflow.json`.

8. **"A graphical abstract for an mRNA vaccine study."** → multi-panel
   figure mixing `cellular_schematic` and `pathway` panels. See
   `tests/fixtures/graphical_abstract_mrna_vaccine.json`.
