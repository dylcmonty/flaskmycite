# MSS Notes: Datums, Constraints, Lenses, and Emergent Tables

These notes capture the current working mental model for the **MSS / Mycite** data representation approach as implemented in the JSON *anthology* and *conspectus* prototypes, and how the portal UI (`data.py`) should begin interpreting and editing that data.

The key idea is that the system is **not “a set of tables” first**—it is a **graph of datums**. “Tables”, “rows”, “fields”, and even “meaning” are *derived* by a small number of structural rules plus optional interpretive “lenses”.

---

## 1. Core premise

### 1.1 Datums are the primitive
A **datum** is the atomic addressable object. Everything else is a consequence of how datums reference each other.

Datums live in the **anthology** as entries keyed by an identifier:

```
<layer>-<value_group>-<iteration>
```

Example identifiers: `11-0-1`, `4-1-9`, `11-3-1`.

### 1.2 Meaning is late-bound
Low-layer datums (e.g., “a space of 128”) are not inherently semantic. They become meaningful only when used by higher-layer datums along a reference path.

This results in **late binding** and **context-dependent semantics**:
- Bottom layers define *constraints and spaces*.
- Higher layers assemble *structures and records* using those spaces.
- UI/logic chooses *lenses* that “smooth” the interpretation for the user.

---

## 2. Minimal structural rules (fewer rules than it seems)

The system is designed so there are **few invariants**, and most meaning is emergent.

### Rule A — Layer constraint
A datum at layer **L** may only reference datums in layers **< L**.

Example: `11-3-1` (layer 11) should only reference datums from layers 0–10.

### Rule B — Value-group arity
The **value_group** in `<layer>-<value_group>-<iteration>` indicates *how many field/value associations* are present in that datum instance.

- `value_group = 0` → “archetype / declaration / selection” style usage
- `value_group > 0` → a tuple-like datum referencing `value_group` field/value pairs

This does **not** automatically imply “row of a table”.
It only implies: “this datum binds N field/value associations.”

### Rule C — Two common anthology shapes
In the prototype JSON, two shapes appear commonly:

**Definition-style datum**
- One reference + magnitude, with a label/title.

Conceptually:
- “This datum is defined as reference X with magnitude M.”

**Tuple-style datum**
- A sequence encoding alternating: `field_datum, value, field_datum, value, ...`

Conceptually:
- “This datum binds these fields to these values.”

These two shapes are enough to build the first useful interpreter.

---

## 3. Bacillette → Baciloid → Babel → Column/Field

A recurring abstraction chain builds “spaces” and then makes them usable:

### 3.1 Bacillette (rudiment set size)
A **bacillette** is a datum that defines “how many rudiments exist in a nominal set”.

Example concept:
- ASCII bacillette: 128 rudiments.

This is not “ASCII” *by itself*—it’s “a set of size 128”.
It becomes ASCII only when later paths treat it as such.

### 3.2 Baciloid (array-of-rudiments)
A **baciloid** duplicates a bacillette by a multiplier (commonly 256) to form a higher-dimensional constraint:
- “an array of 256 cells where each cell is 0 or one of 128 rudiments”.

This gives you a structured space: (length × alphabet).

### 3.3 Babel (a referencable space, not a concrete instance)
A **babel** is made by referencing a baciloid with magnitude **0** to prevent further duplication and to treat the result as a *space* rather than an *instance*.

Intuition:
- A baciloid is like “a concrete array definition”.
- A babel is like “the ambient space” (a referencable constraint).

### 3.4 Column vs Field: “constraint pointer” vs “substance”
From a babel, you typically declare both:

- **Column datum**: references the babel with magnitude **0**  
  → “referencable object without substance” (constraint-only)

- **Field datum**: references the babel with magnitude **1**  
  → “substantive object” that can appear in tuple-style datums as a field

This is the key distinction used later:
- Columns participate in *table archetypes* and structural metadata.
- Fields appear in *entries* and carry substantive values.

---

## 4. Example trace: interpreting `11-3-1`

Consider a layer 11 datum instance:

### 4.1 Structural facts
- `11-3-1` is layer 11.
- `value_group = 3` means it binds 3 field/value associations.

### 4.2 Field/value associations (conceptual form)
```
11-3-1 ; 4-1-9  : dylan_montgomery
11-3-1 ; 4-1-3  : 3-2-3-17-77-1-6-4-1-3
11-3-1 ; 10-1-2 : 2
```

At this stage, there is *no rule* that declares this is a “table row”.
It is simply a datum binding three fields to magnitudes.

### 4.3 Planned representation change
Right now, the magnitude for `4-1-9` may store the literal string `dylan_montgomery`.
The plan is to instead store a numeric encoding representing a selection inside the 256×128 space.

So the UI needs two parallel representations:
- **stored magnitude** (numeric)
- **display value** (decoded string)

This is the role of “lenses”.

---

## 5. Conspectus “0 selection” and table archetypes

### 5.1 Table archetypes exist, but tables are emergent
A datum like `11-0-1` can declare a *table archetype* (e.g., `msn_index_table`).

The **conspectus** provides a selection list for the table archetype:
- It defines which **columns** are “available/active” for that table archetype.

Importantly:
- This selection does not necessarily force all entries to conform.
- It provides structure and intent, not absolute validity.

### 5.2 Why fewer rules
If a new `11-3-x` appears that references a different set of fields:
- It is **not invalid**
- It is simply **not part of the same table instance**

So “table membership” is a **soft inference**.

---

## 6. Sets, validity, and why some things *can* be invalid

The system is heavily “set-driven”:

- A field implies a **set of admissible values** (by its constraint chain).
- A row can be “not part of a table” without being invalid.
- But a value written into a field can be invalid if it falls outside the field’s admissible set.

Example:
- If `4-1-9` is a 256-character field,
  you cannot write a 257-character string into it
  because it is not a member of the implied set.

This is the key separation:

- **Table grouping** → heuristic / emergent / non-fatal
- **Field validity** → strict / set-based / fatal on write

---

## 7. “Lenses”: the UI interpretation library

### 7.1 Purpose
A **lens** is a modular interpreter that:
- recognizes a field’s constraint pattern,
- validates values,
- encodes/decodes stored magnitudes,
- provides user-friendly rendering (icons, labels, formatting).

You will maintain a growing library of lenses:
- base lenses are standardized and always available
- custom lenses can be authored later using the same base primitives

### 7.2 Two initial lens tiers
**Tier 1: Constraint lenses (hard validity)**
- ASCII lens (256×128)
- hex-color lens (e.g., 16,777,216 rudiments)
- MSN-ID lens (structured code constraints)
These enforce set membership.

**Tier 2: Presentation lenses (soft display)**
- icon mapping for fields
- label smoothing, abbreviations, colors
- grouping hints for “table instances”

These do not enforce validity; they improve readability and usability.

### 7.3 Lens matching strategy
A lens should not rely on hard-coded IDs alone.
It should match by **reference-chain pattern**.

Example: ASCII lens matches a field whose chain looks like:
- field → babel → baciloid → bacillette → nominal incremental unit

This makes the system portable and allows renumbering or alternate constructions.

---

## 8. How `data.py` should evolve (core engine plan)

The goal is to implement the **true core** of `data.py` as a rule engine over datums, while still loading from JSON (so it can later be swapped for DB storage).

### 8.1 Stage 1: Graph + indexing (pure structure)
- parse anthology entries into an in-memory `DatumGraph`
- expose:
  - `get_title(id)`
  - `parse_id(id) -> (layer, value_group, iteration)`
  - `is_definition_datum(id)`
  - `is_tuple_datum(id)`
  - `tuple_pairs(id) -> [(field_id, value), ...]`
  - `definition_ref(id) -> (ref_id, magnitude)`

### 8.2 Stage 2: Chain resolution (constraints)
- `resolve_chain(field_id)` follows definition refs downward
- `compile_constraint(field_id)` builds a minimal `ConstraintSpec`

At first, this can be coarse (length and alphabet size).
Later, it can compile structured schemas and transformations.

### 8.3 Stage 3: Lens registry (interpretation)
- implement `Lens.validate / Lens.encode / Lens.decode / Lens.render`
- choose lens per field when rendering/editing cells

### 8.4 Stage 4: Emergent table views
Instead of assuming “a table is a fixed schema”, infer “table instances”:

- define a **row signature**: `signature(row) = set(field_ids referenced)`
- cluster rows by signature within a layer (e.g., layer 11)
- optionally label clusters using table archetypes + conspectus selections

This supports:
- multiple tables per layer
- rows appearing interleaved in iteration order
- divergence without invalidation

### 8.5 Stage 5: Editing with strict field validation
On edit:
1. determine the field datum for that cell
2. select matching lens
3. parse input to stored magnitude (encode)
4. validate stored magnitude against compiled constraint
5. write back to JSON

This is the first place the system becomes truly “data-correct”.

---

## 9. Immutability and versioning (important future rule)

Foundational constraint layers should be treated as **immutable**.
If you want “512 characters instead of 256”:
- you should not update the original baciloid/babel
- you should create new datums and new field/column declarations

This preserves historical interpretation and prevents retroactive constraint changes.

---

## 10. Practical UI implications

### 10.1 Excel-like view is a “lens view”
The grid is not “the data”; it is an interpreted view:
- columns are field datums (or their column twins)
- cell display is decoded by a lens
- writes are validated by field constraints

### 10.2 Icons and ambiguous labels
Eventually each datum can have:
- an icon datum reference
- a presentation lens
so the UI becomes less “coded” and more semantically legible.

This is a display concern and should not change the underlying structural rules.

---

## 11. Glossary (current working vocabulary)

- **Datum**: atomic addressable unit in anthology.
- **Layer**: stratification level; higher layers build on lower layers.
- **Value group**: arity of field/value associations in tuple-style datums.
- **Magnitude**: the value stored with respect to a datum reference.
- **Bacillette**: defines size of a rudiment set (e.g., 128).
- **Baciloid**: structured array built from a bacillette (e.g., ×256).
- **Babel**: a referencable space (magnitude 0) preventing further duplication.
- **Column datum**: babel reference with magnitude 0; constraint-only metadata.
- **Field datum**: babel reference with magnitude 1; substantive field usable in entries.
- **Conspectus selection**: declares available columns/fields for an archetype.
- **Lens**: interpreter module for rendering/encoding/validating field values.
- **Table instance**: an inferred cluster of rows sharing field sets/signatures.

---

## 12. Immediate next steps (implementation-focused)

1. Build `DatumGraph` with reliable detection of definition vs tuple datums.
2. Implement chain resolution (`resolve_chain`) and minimal constraint compilation.
3. Implement the first lens: ASCII (256×128).
4. Implement row signature clustering to infer table instances within a layer.
5. Update the data UI to:
   - render via lenses
   - validate writes against constraints
   - treat “not in this table” as a different cluster rather than an error.

This keeps the JSON backend isolated while building the interpretive core that can later be backed by a database.


---

## 13. Data tool as a NIMM-driven interface

This section describes the intent for the **Data** tool (the “Data tab”) to behave as a sturdy, extensible interface whose behavior is governed by a small set of action categories. The goal is to avoid hard-coding view logic per table or per domain, and instead drive UI changes from an explicit state model.

### 13.1 Intent: NIMM directives

The Data tool supports four core action categories:

- **Navigation (`nav`)**: change the location of focus (e.g., which JSON file, which table archetype, which table instance).
- **Investigation (`inv`)**: open an inspection view of a subject (e.g., datum details, abstraction path, constraint compilation) without necessarily changing the navigation focus.
- **Mediation (`med`)**: change the interpretive lens or method used to render/organize the current subject (e.g., show “abstraction path” vs “flat row view”, reorder by timestamp vs by actor).
- **Manipulation (`man`)**: stage and apply edits (with validation), including helper UI for constrained sets (drop-downs, pickers, invalid highlighting).

These directives are collectively referred to as **NIMM**: **Nav / Inv / Med / Man**.

### 13.2 Intent: directive syntax (conceptual)

A directive is expressed conceptually as:

```
(<NIMM_action> with respect to <subject> in a manner of <method/context>)
```

Examples (conceptual, not a required wire format):

- `nav:anthology;top_level_view`
- `inv:11-0-1;abstraction_path`
- `med:11-3-1;ascii_lens`
- `man:11-3-1;set_field=4-1-9,value=<...>`

The important point is **not the string format**, but that actions are explicit, composable, and stateful.

### 13.3 Intent: state is defined separately from what is rendered

The Data tool should maintain an explicit **Data View State** which drives what the UI shows. The state is separate from the “meaning” of the underlying datums.

A minimal state model (conceptual):

- **Focus / location**
  - which source is in focus (e.g., anthology vs conspectus vs SAMRAS)
  - which table archetype or table instance is in focus (if applicable)
- **Pane layout**
  - left pane = primary navigation context
  - right pane = investigation/inspection context
- **Mode**
  - general view vs inspect view vs raw view vs inferred-table view
- **Lens selection**
  - which lens(es) are active globally or for a specific field/subject
- **Staged edits**
  - pending edits not yet committed (with validation results)
- **Selection**
  - a selected datum, field, row signature cluster, etc.

The UI should be a **reflection** of this state, not the source of truth.

### 13.4 Intent: two-pane interaction model

Initial UX target:

- **Left pane**: “top level view” of whatever is currently navigated (files, tables, datums, table instances).
- **Right pane**: investigation view for a selected facet (datum trace, abstraction chain, compiled constraints, field/value pair inspection).

This supports exploration without forcing users to “leave” their current navigation context.

### 13.5 Intent: mediation as lens switching

Mediation is the mechanism for changing **how** a subject is interpreted or organized without changing the underlying data.

Examples:
- message-board datum organized by timestamp vs organized by participating `msn_id`
- a row datum shown as raw field/value pairs vs shown as a decoded “record” with human labels/icons
- a field magnitude shown as raw numeric magnitude vs decoded ASCII string

Mediation is where the “library of lenses” becomes a first-class capability.

### 13.6 Intent: manipulation as staged, validated edits

Manipulation should follow a staged model:

1. user edits a cell or field
2. engine applies a lens-specific parse/encode step
3. engine validates against compiled constraints (set membership)
4. edit is staged (not persisted) and reflected in the view state
5. commit action persists staged edits through the storage adapter

This keeps the system robust and supports later migration to database storage.

---

## 14. Responsibility boundaries (data engine vs controllers vs UI)

This section defines **intentional separation of responsibility**. It is not a mandate for a specific folder layout; it is a contract about where meaning is computed and where it is displayed.

### 14.1 Intent: the data directory is the domain engine

The `data/` area (and its supporting modules) is responsible for:

- parsing and indexing datums (anthology/conspectus/SAMRAS)
- resolving definition chains and compiling constraints
- selecting lenses and producing display-ready view models
- table-instance inference (row signatures, clustering)
- staging edits and validating them
- committing changes through a storage adapter (JSON now; DB later)

It should not depend on Flask, templates, or request objects.

### 14.2 Intent: controllers are thin glue

Controllers (portal API routes) are responsible for:

- accepting user intent (NIMM directive submissions, edit requests)
- invoking data-engine operations
- returning view models and validation results
- enforcing portal-only boundaries

Controllers should avoid embedding semantic logic (no chain parsing in routes).

### 14.3 Intent: UI is presentation only

The UI should:

- render views returned by the engine (left/right panes, tables, inspectors)
- provide interaction affordances (clicks, tabs, drop-downs)
- send directives/actions to controllers
- reflect staged edits and errors

The UI should not read JSON files directly or infer table meaning.

### 14.4 Implementation guidance (non-binding)

A typical pattern that satisfies the above:

- Data Engine: `data/engine/*` + `data/storage_*`
- Controller endpoints: `/portal/api/data/...`
- UI pages: `/portal/data` shell template + JS that fetches view models

These are suggestions; the boundary constraints are the requirement.

---

## 15. NIMM Data Tool packaging (intent + implementation guidance)

### 15.1 Intent

- Data capabilities should be exposed as a **tool package** (`data_tool`) instead of hard-coded core UI.
- NIMM state is the control surface:
  - `nav` updates navigation context
  - `inv` updates investigation context
  - `med` changes mode/lens interpretation
  - `man` stages or commits edits
- The engine owns all semantics, and the UI only renders returned view models.

### 15.2 Implementation guidance (current naming)

- Tool package:
  - `portal/tools/data_tool/__init__.py`
  - tool route: `GET /portal/tools/data_tool/home`
- Engine:
  - `data/engine/workspace.py`
  - `data/engine/nimm/state.py`
  - `data/engine/nimm/directives.py`
  - `data/engine/nimm/viewmodels.py`
- Controllers:
  - `portal/api/data_workspace.py` routes under `/portal/api/data/*`
- UI:
  - `portal/ui/templates/tools/data_tool_home.html`
  - `portal/ui/static/tools/data_tool.js`

### 15.3 State persistence guidance

- Workspace state should persist in local private storage:
  - `private/daemon_state/data_workspace.json`
- State data is non-secret and recoverable.
- Malformed state files should be handled by reset-to-default + warning.
