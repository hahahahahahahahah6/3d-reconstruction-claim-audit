# Documentation claim auditor

An offline static checker that compares documented promises about the checked
capability with Python source patterns. It reads the root README and Markdown
files below any docs directory, excludes fenced blocks, and counts inline code.
Source is parsed without execution. There are no runtime dependencies.

```sh
python3 -m pip install .
3d-reconstruction-claim-audit --version
3d-reconstruction-claim-audit audit . --json
3d-reconstruction-claim-audit audit . --fail-on medium --ignore vendor/ --ignore generated/
python3 -m 3d_reconstruction_claim_audit audit . --verbose
```

The audit subcommand defaults to the current directory. Prefix exclusions use
repository relative paths and can be repeated, one value per option. The default
threshold is high; medium also fails on evidence found only in tests. Exit 0
means no finding meets the threshold, exit 2 means a finding meets it, and exit 1
means a usage or I/O error. JSON includes verdict, findings with id, severity and
message, matched phrases, and production and test evidence paths. A report may
have a FAIL verdict yet exit 0 when its findings fall below the threshold.

```text
documented-3d-reconstruction-claim-false  HIGH or MEDIUM
documented-no-3d-reconstruction-claim-false  HIGH
```

A positive promise without production evidence produces the first finding;
evidence only in tests lowers it to medium. A denial contradicted by production
evidence produces the second. Without source files, a positive promise fails
and a denial passes. Each family produces at most one finding.

Evidence includes supported library operations, a volume construction paired
with integration on that volume, a complete four stage feature and geometry
pipeline, or a listed generic operation call. Each pair or pipeline must occur
in one module. Imports alone, file loading, display, model containers, comments,
strings, and external command invocations do not establish the checked feature.
Local definitions shadow route names. Imported aliases and direct bindings are
tracked, including annotated assignments and context manager targets.

Symlinked files and directories are skipped. Source under fixtures, docs, and
examples is excluded; test files are classified separately. Invalid syntax
provides no evidence. Files must be readable UTF-8 text.

## Differentiation

Depth estimates describe distance per pixel. Image stitching joins overlapping
pictures. Pose estimation locates joints or a camera. Optical flow tracks pixel
motion. Image generation creates pictures. None alone establishes the checked
operation, which requires the specific source patterns described by this audit.

## Honest limitations

Exact wording can refer to a foam toy brand, a survey job, unrelated sparse or
dense mathematical models, downloaded assets, or a hardware scanner workflow.
Those uses may trigger a false positive. Generic wrappers may invoke an external
binary, and generic viewer calls may match despite performing only display.
Handwritten neural models with ray based rendering loops and no listed named
operation are missed. Training and mapping through external programs are missed:

```text
ns-train (Nerfstudio), colmap (COLMAP), Meshroom
```

Constructing a model container alone does not establish the checked operation:

```text
pycolmap.Reconstruction()
```

Static matching cannot judge semantics or whether code runs; dead code counts.
Complex alias chains may be missed. Only exact phrases match, and denial handling
depends on a fixed vocabulary. Evidence spread across modules is missed.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

Requires Python version 3.9 or later. Distributed under the MIT license.
