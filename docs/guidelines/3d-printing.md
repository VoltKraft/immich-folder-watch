# 3D printing guidelines

Apply these rules to parts intended for additive manufacturing, print packages,
slicer projects, and physical test reporting. Read the
[CAD guidelines](cad.md) when creating or changing geometry. Keep requirements
in the [project brief](../project.md) and evidence in the
[project status](../status.md).

## Available equipment and alternatives

- Unless the project specifies otherwise, use the user's Bambu Lab A1 mini and
  PLA as the available printing baseline (user-provided template defaults). Carry
  this baseline into new project planning without asking for it again; update
  the project brief when the user reports different equipment or materials.
- The manufacturer's nominal build volume is 180 x 180 x 180 mm; see the
  [official A1 mini specifications](https://uk.store.bambulab.com/products/a1-mini).
  Check usable space in the actual slicer profile, including brims, supports,
  and placement restrictions. Installed nozzle, filament grade, slicer/profile,
  accessories, and calibration remain unspecified until established.
- Inform the user when another material or a larger build volume would better
  serve the design. Explain the benefit, affected parts, and relevant tradeoffs,
  such as durability, joint behavior, part splitting, or assembly effort. Record
  the recommendation and assumptions in the project brief.
- Such a recommendation is not a project blocker and does not require a reply
  before continuing useful authorized work. Continue with explicit, revisable
  assumptions and suitable design options. Prefer A1 mini / PLA compatibility
  where it meets the requirements; consider orientation or mechanically joined
  segments when sensible, without forcing an unsuitable material or excessive
  splitting merely to fit the available printer.
- Distinguish available equipment from proposed alternatives. Keep any actual
  fabrication or validation prerequisite explicit in status while progressing
  independent work; do not claim that a recommended material or larger printer
  is available, or that PLA meets unverified functional requirements.

## Process and design inputs

- Apply the [CAD design defaults](cad.md#design-defaults-reuse-and-standards),
  including their scope and exception rules, to parts and printed connectors.
- Identify the actual printing process, printer, usable build volume, material,
  and slicer. For extrusion printing, include nozzle size and relevant bed or
  chamber capabilities; record equivalent constraints for other processes.
- Record the material grade and profile assumptions relevant to fit, strength,
  temperature, or durability. Do not treat a generic material name as measured
  performance for a particular print.
- Label missing inputs as provisional assumptions. Continue independent design
  work where possible, but do not claim machine compatibility or physical
  performance until the required inputs and checks are available.
- Assess orientation, layer direction and anisotropy, wall thickness, supports,
  overhangs, bridging, dimensional accuracy, shrinkage, and assembly clearances
  when relevant to the selected process and part function.
- Prioritize easy printing and support-free geometry where feasible; otherwise
  minimize supports and allow their removal. Check limits against the actual
  process, material, orientation, and profile rather than universal angle rules.
- Consider service temperature, creep, repeated loads, environmental exposure,
  and failure consequences where relevant. Record the required validation in
  the project brief; do not infer suitability from material labels alone.
- Prefer a small fit or process sample before a large print when it can resolve
  a material uncertainty. Define what will be measured and what counts as a pass.

## Connections and assembly instructions

- Design assemblies without adhesives, using mechanical joints. Distinguish
  permanent joins, such as build-volume splits intended to remain assembled,
  from joints that must support intentional disassembly. Record that intent for
  each interface; any departure from the defaults requires explicit agreement.
- Choose suitable printed connections, including snap fits or compliant
  mechanisms where appropriate. Assess material behavior, allowable strain,
  expected assembly cycles, creep, tolerances, print orientation, and access
  for assembly and release. Prototype uncertain joints before full physical
  production. Continue digital work while physical checks are pending; require
  those checks for digital milestone completion only if its criteria include them.
- For every multipart assembly, provide an illustrated step-by-step manual
  and an exploded view derived from the actual delivered CAD revision. Label
  parts consistently with the CAD model and authoritative BOM; include required
  quantities and materials through a linked or generated view of that BOM,
  avoiding an independently maintained second list.
- Show assembly order, insertion directions, joint engagement and locking
  checks, and disassembly steps for separable joints. Identify permanent joins
  clearly so the reader knows which steps cannot be routinely reversed.
- Verify illustrations, labels, and instructions against the actual geometry,
  revision, and package contents. Keep source views and manual revision traceable;
  illustrative images alone do not establish that an assembly has been tested.

## Printable package

- Tie every output to its part ID and source revision. Record intended units,
  orientation, material, and required quantity in a package manifest or the
  authoritative BOM; avoid competing copies of the same production data.
- Follow the [CAD format and revision rules](cad.md#deliverables-and-continuation).
  State STL units explicitly. Check which settings and objects a 3MF file holds;
  it may contain geometry only or a slicer-specific project.
- Validate meshes for the intended process: expected bounds and scale, valid
  surfaces, normals, unintended intersections, and closed volumes where needed.
  Inspect repairs for changed geometry instead of assuming every automatic fix
  preserves the design.
- Compare the complete requested package with the full assembly BOM, including
  unchanged parts. Check part families, unique files, and total instance counts.
  One file may represent several identical pieces if quantities are explicit.
- Include purchased parts and nonprinted assembly dependencies in the BOM only
  when explicitly included in the project, clearly marked as nonprinted items.
  Include printed connectors and check mirrored or handed variants separately.
- Label partial exports as subsets and identify omitted items. Do not describe
  a changed-parts archive as a complete assembly package.
- Verify archive contents and readability after packaging. For released or
  transferred packages, record checksums when needed to identify exactly which
  files were reviewed, delivered, or printed.

## Slicer validation

- Record the slicer version, target machine/profile, material profile, relevant
  overrides, orientation, and instance placement with the inspected revision.
  Preserve the slicer project when needed to reproduce the preparation.
- Check every build plate for usable-volume limits, object quantities, missing
  features, unsupported regions, first layers, support access, and collisions
  or prohibited print sequences relevant to the machine.
- Inspect the layer preview and relevant warnings. Record estimated material
  and time as estimates, and state explicitly if slicing was not performed.
- Treat machine code, including G-code, as specific to its machine, firmware,
  process, and settings. Do not present it as a universal printable artifact.
- File preparation does not authorize uploading to a printer, heating, motion,
  or starting a job. Follow the project's established operational authorization
  and respect the actual machine state before any machine action.

## Physical validation and traceability

- Distinguish CAD checks, mesh checks, slicer checks, successful fabrication,
  physical fit, and functional qualification. Evidence for one stage does not
  establish completion of the others.
- Associate a physical specimen with its part revision, package, machine,
  material, and relevant print settings. Record observed defects or deviations.
- For each physical test, record the method, acceptance criterion, result, and
  evidence. Attribute user-reported results to the user; do not invent measured
  dimensions, loads, temperatures, or successful tests.
- After a geometry, material, orientation, or process change, identify which
  earlier checks no longer apply and repeat those needed for acceptance.
- Update project status with completed digital stages, outstanding physical
  checks, and the next step. If a test requires user action, state the concrete
  measurement or observation needed and continue independent authorized work.

## Troubleshooting

- Missing parts: compare archive membership and plate instances against the
  full BOM, accounting for repeated parts and multiple build plates.
- Poor fit: compare measured mating dimensions, tolerances, orientation, and
  process calibration before changing nominal CAD dimensions.
- Unexpected preview or scale: verify export units and bounds, mesh integrity,
  slicer import behavior, and profile overrides before preparing machine code.
