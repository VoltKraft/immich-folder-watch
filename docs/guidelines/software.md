# Software

Read this guide for software implementation, including CAD/export automation.
The [project brief](../project.md) owns the actual stack, interfaces, and commands;
the [status](../status.md) records what was run and verified.

## Implementation and validation

- Inspect checked-in manifests and existing code before choosing tools or patterns.
  Document purpose, important directories, entry points, and architectural
  boundaries in the brief, with links to detailed specifications when needed.
- Record exact setup, development, build, test, lint, formatting, and static
  analysis commands where applicable. Mark unsupported workflows as not
  applicable; remove examples that do not work for this project.
- Preserve compatibility contracts, user data, and unrelated changes. Document
  migration steps for changed interfaces, defaults, or persistent formats.
- Validate behavior at the narrowest relevant level first. Add or update
  meaningful tests for changed behavior and regressions when appropriate; do
  not add tests that merely mirror text or low-impact reversible changes.
- Use actual tool output as evidence. Report failures and unavailable checks;
  never treat syntax validation as proof of runtime behavior or integration.
- Keep secrets out of code, examples, logs, and version control. Record required
  environment variable names and purpose without secret values.

## Code comments and API documentation

- Prefer clear names and straightforward structure over comments that explain
  obvious code.
- Use comments to explain why a decision exists, not to narrate what the code
  does.
- Document non-obvious invariants, assumptions, edge cases, units, concurrency
  behavior, security boundaries, performance tradeoffs, and external
  constraints.
- Explain workarounds with the underlying issue, affected dependency or
  platform, and the condition under which the workaround can be removed.
- Add docstrings or equivalent API documentation to public interfaces and
  complex internal abstractions.
- Document contracts, parameters, return values, errors, side effects,
  mutability, nullability, thread safety, and lifecycle requirements when
  relevant.
- Keep comments close to the behavior they describe and update them in the same
  change as the code.
- Treat stale or misleading comments as defects.
- Do not leave commented-out code; rely on version control.
- Avoid vague TODOs. A TODO must state the missing work, why it remains, and a
  tracking reference when one exists.
- Do not add large explanatory comments to compensate for unnecessarily complex
  code. Simplify the implementation first when practical.
- Do not generate documentation or comments merely to increase coverage or
  volume. Add them only when they clarify usage, contracts, constraints, or
  decisions that are not apparent from the implementation.
