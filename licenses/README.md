# License texts

This directory holds license and notice texts required for redistribution.

Included:

- `Apache-2.0.txt` — SecOne application license.
- `LICENSE-XuanmuSec.txt` — XuanmuSec-2.6B license selection notice
  (Apache-2.0 declared by the publisher; full text in `Apache-2.0.txt`).
- `LICENSE-LFM1.0.txt` — LFM Open License v1.0, verbatim upstream text for
  the Liquid AI LFM2 base model. Retrieved 2026-10-31 from
  `https://huggingface.co/LiquidAI/LFM2-2.6B/raw/main/LICENSE`.
- `LGPL-3.0.txt` — Qt/PySide6 dynamic-linking obligations.
- `LGPL-2.1.txt` — py7zr and its LGPL dependencies.
- `PSF-2.0.txt` — Python runtime.
- `LICENSE-llama.cpp.txt` — llama.cpp runtime (MIT).
- `LICENSE-PyYAML.txt`, `LICENSE-pypdf.txt`, `LICENSE-Pillow.txt`,
  `LICENSE-py7zr.txt` — direct dependencies.
- `python-packages/` — license files collected from installed wheels.

`LICENSE-XuanmuSec.txt` is a license-selection notice, not the publisher's
copyright statement. Before redistributing model weights, obtain the
publisher's NOTICE/copyright file and add it to this directory; the model
packaging script copies everything here into the model package.

Re-run `scripts/collect_licenses.py` after upgrading Python dependencies.

Nothing in this directory changes the upstream license terms; the upstream
texts control. If a file here conflicts with the upstream distribution,
replace it with the official upstream copy.
