# CAD guidelines

Apply these rules to CAD construction, assemblies, drawings, and CAD exports.
Use the [project brief](../project.md) for requirements and acceptance criteria
and the [project status](../status.md) for evidence and outstanding work.
Also read the [3D printing guidelines](3d-printing.md) for printed parts.

## Design defaults, reuse, and standards

- Unless the project specifies otherwise, assume designs are made entirely by
  3D printing, including connectors and assembly features. Apply the printing
  guide from the start. Ask a focused question when function, loads, environment,
  or manufacturing constraints make an exception useful or necessary; do not
  silently add purchased hardware, inserts, adhesives, or other nonprinted parts.
- Maximize the use of existing and standardized parts wherever they meet the
  project's function, interfaces, printability, and quality requirements. Before
  designing a new part, search existing project components, reusable libraries,
  and relevant manufacturer or standards-based catalogs. Prefer reuse, then a
  controlled adaptation, over a new design; briefly record why custom geometry
  is needed when suitable reuse is not possible.
- McMaster-Carr, parts4cad, and TraceParts are available in the user's Fusion
  environment as user-provided template defaults. Include these sources in relevant
  component searches and use suitable existing models instead of redrawing them.
  Verify access and the actual import result when using a source; do not assume
  that an available UI integration also exposes an automation API.
- Reusing a catalog model does not imply purchasing the physical component or
  establish that a printed copy has the original part's material properties or
  performance. Apply the fully 3D-printed default and validate any adaptation
  for the intended printing process.
- Verify a reused model's source, revision, scale, geometry, and license for the
  intended use, modification, manufacturing, and distribution. Record its catalog
  or manufacturer, part number/configuration, source link, applicable standard,
  and adaptations in the authoritative BOM or linked component record. Keep
  attribution and provenance; do not import incompatible or unverified-license
  assets into deliverables. A catalog listing alone does not prove compliance
  with an official standard.
- Reuse identical parts as instances of one definition. For small differences,
  prefer parameters or controlled variants over redesigning from scratch. Record
  the variant and its compatibility; do not change a shared master for one use
  without checking its other consumers, or treat different geometry as identical.
- Standardize interfaces, connectors, dimensions, and part families where suitable
  to increase interchangeability and reduce the number of unique manufactured
  parts. Do not force reuse when it compromises fit, function, or manufacturability.
- Prefer applicable official standards, such as ISO standards, for dimensions,
  interfaces, tolerances, and documentation. Verify the identifier, edition, and
  scope from the issuing body's authoritative sources and record the relevant
  requirements. If the normative text is unavailable, disclose that limitation;
  do not invent values or claim compliance. Document any printing-related
  deviations and their effect on compatibility rather than labeling them compliant.

## Source and working state

- Identify the authoritative native document, its location or document ID,
  revision, and the components within the authorized scope before editing.
- Inspect the live application state: active document, component, edit context,
  history position, pending changes, and active commands. Recheck after a
  document switch, interrupted operation, or reconnect.
- Preserve unrelated changes and foreign documents. Do not silently switch,
  close, save over, or alter another document to make automation succeed.
- Respect active interactive commands. If one prevents safe editing, record
  the blocker and continue independent work; resume after it ends and state
  has been rechecked. Do not assume an issued tool call completed successfully.
- Maintain a recoverable native save or version before substantial changes.
  Record external references and linked components needed to reopen the model.
  A screenshot or mesh export is not a substitute for the editable source.
  Follow the shared [saving and commit checkpoints](collaboration.md#saving-and-commit-checkpoints)
  throughout construction, including work that is not yet complete.

## Design contracts

- Record intended function, interfaces, envelope, loads, operating conditions,
  materials, and required manufacturing process in the project documentation.
  Label unknowns and provisional assumptions; make them easy to revise.
- Define model units and coordinate conventions. Confirm the units expected
  by APIs, imported references, and exports; document explicit conversions.
- Use stable part and assembly IDs with traceable revisions. Keep display
  names descriptive and avoid relying solely on transient application indices.
- Prefer editable, parametric construction when appropriate. Name important
  parameters, constrain functional geometry, and document intentional freedoms.
  Record the reason when using a direct or mesh-based workflow instead.
- Distinguish nominal dimensions, tolerances, and assembly clearances. Document
  mating surfaces, fasteners, motion limits, and relevant tolerance stacks.
- Maintain one authoritative bill of materials (BOM) with part IDs, revisions,
  quantities, materials, and any explicitly included purchased items. Distinguish
  unique part designs from repeated assembly instances and manufacturing quantities.
- Document material properties and calculation assumptions used for mass,
  center of gravity, strength, or thermal conclusions. Keep estimates separate
  from measured or qualified values.

## Autodesk Fusion distributed design

- Use a hierarchical, distributed assembly with externally linked components.
  The main assembly should predominantly reference independent subassembly
  documents. Store large, reusable, or independently edited parts in separate
  Fusion documents and reference them externally as well.
- Small parts used only within a subassembly may remain internal components.
  Every physical part must still have its own component or an occurrence of an
  identical part definition, including separately printed segments. Do not use
  a collection of bodies in one component as a substitute for the assembly BOM.
- Arrange documents so parts can be manufactured independently, subassemblies
  edited separately, and reusable components maintained centrally. Avoid one
  document per trivial part when internal components serve the same purpose.
  Record component IDs, document locations, and their hierarchy in the project.
  See Autodesk's [component model](https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-COMPONENTS.htm).
- Use shared assembly coordinates and traceable master reference geometry.
  Define origins, axes, datums, and intentional local transforms consistently.
  Give cross-document parameters one authoritative owner and a documented
  propagation strategy supported by the actual Fusion setup; record units,
  dependent documents, and how updates are verified. Avoid circular dependencies
  and unnecessary geometry copies; do not assume same-named parameters synchronize.
- Incorporate external changes into parent assemblies deliberately. Record the
  referenced revisions, inspect affected interfaces, joints, geometry, mass,
  and center of gravity, and resolve reference or assembly-context warnings.
  Do not blindly accept every latest version. Use the appropriate native
  [reference update operation](https://help.autodesk.com/cloudhelp/ENU/Fusion-Assemble/files/ASM-UPDATE-ASSEMBLY.htm)
  for the installed Fusion version and verify the resulting assembly.
- Use Fusion's native data management for linked documents. In addition, create
  local, revisioned recovery backups under `cad/` at meaningful checkpoints.
  Include the referenced document set, master references, and parameter sources
  needed to reconstruct the saved assembly; do not break live links for backup.
- Use native F3Z archives for distributed designs where supported; standalone
  F3D files do not substitute for an assembly's external references. Record an
  archive manifest with source document IDs/revisions, dependency mapping, file
  paths, and recovery steps. Verify reference coverage and recovery by importing
  into a separate authorized recovery location, without overwriting live sources.
  If recovery cannot be tested, mark it unverified and record what remains.
  Exports do not retain associativity to the original cloud documents; see
  Autodesk's [export guidance](https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-EXPORT-DESIGN).

## Materials and visual identification

- Assign appropriate physical materials and intentional appearances/colors to
  Fusion components, including imported parts. Use actual specified material
  properties where available; label provisional substitutes and density assumptions.
  Check overrides on bodies and occurrences so mass calculations and displayed
  colors represent the intended parts consistently.
- Use consistent colors for materials, part families, or assembly identification,
  and explain the convention in assembly documentation. Colors supplement stable
  part IDs; they do not replace them or establish mechanical properties. See
  Autodesk's [physical materials and appearances](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/GUID-55EC2C42-60E1-48C7-B802-D2AA7AB6F0CB.htm).
- Treat CAD mass and center-of-gravity results as model estimates. Account for
  print settings, voids, and material assumptions when comparing with slicer or
  measured values; an assigned bulk material is not a validated printed strength.

## Construction and verification

- Construct the geometry and interfaces required by the active milestone.
  A plan, script, rendering, or outer shell alone does not prove construction.
- Inspect actual resulting geometry and relevant application diagnostics after
  edits. Check feature failures, body/component counts, dimensions, and units.
- Check assemblies for intended placement, interference, clearances, access,
  motion, and correspondence with the BOM, as relevant to acceptance criteria.
- Verify imports against a known reference dimension and orientation. Record
  reference provenance and distinguish reference geometry from deliverable parts.
- If a script performs the changes, retain its inputs and execution evidence
  when needed to reproduce the result. Separate prepared, executed, and verified
  steps in status updates.
- Treat simulation results as conditional on their setup, material data,
  contacts, loads, and boundary conditions. Record limitations and required
  physical validation instead of implying qualification from appearance.

## Deliverables and continuation

- Save the native source and export the same identified revision. Record export
  settings, source revision, part IDs, units, and the tool/version when relevant
  to reproducibility. Mark superseded outputs so they cannot be mistaken for
  current deliverables.
- Choose formats for their purpose: native files preserve editable construction;
  STEP supports solid-model exchange; STL provides triangulated geometry without
  reliable unit metadata; 3MF can carry units and manufacturing information.
  Do not assume an exchange format preserves native history or all metadata.
- Inspect or reimport outputs to check geometry, scale, orientation, and package
  membership. Verify the entire requested assembly, including unchanged parts.
- Link the source, BOM, outputs, and validation evidence from the project status.
  Record remaining assumptions, failed checks, and the next actionable step.
  Keep requirements in the project brief instead of duplicating them here.
- Report digital validation separately from fabrication, physical fit, load,
  endurance, or other real-world tests. Complete only the acceptance criteria
  supported by evidence; leave dependent physical milestones open.

## Troubleshooting

- Wrong scale: inspect source, API, and import/export units against a known
  dimension before applying a corrective scale factor.
- Missing or stale geometry: compare source revision, component visibility,
  export selection, and BOM with the actual exported files.
- Blocked application operation: inspect current commands and edit context;
  avoid repeated mutations until the state is understood.
