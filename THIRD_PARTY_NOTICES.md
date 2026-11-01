# Third-Party Notices

SecOne itself is licensed under the Apache License 2.0 (see `LICENSE`).

This file summarizes third-party components that may be distributed with a
SecOne build. It is not a substitute for the full license texts under
`licenses/` and, for model assets, the license files shipped by the model
publisher.

## Model assets (not included in this repository)

### XuanmuSec-2.6B

- Upstream statement: Apache-2.0 for the XuanmuSec work.
- Base model: LFM1.0 License (Liquid AI). The base-model terms apply in
  addition to the XuanmuSec terms.
- Action required before distribution: review both licenses, preserve all
  copyright notices, NOTICE files, and license texts, and document any
  additional use restrictions. Do not redistribute the GGUF unless the
  combined terms permit it.
- `licenses/LICENSE-LFM1.0.txt` contains the verbatim LFM Open License v1.0
  text retrieved from the Liquid AI LFM2-2.6B release on 2026-10-31.
- `licenses/LICENSE-XuanmuSec.txt` records the publisher's declared
  Apache-2.0 license selection; the full Apache text is in
  `licenses/Apache-2.0.txt`. The publisher's own NOTICE/copyright file must
  still be obtained and placed beside it before redistributing weights.
- `scripts/package_model.py` refuses to build a model package when either
  file is missing.

The quantization and GGUF conversion may introduce additional notices from
the conversion tooling; check the model publisher's package.

## Runtime

### llama.cpp / llama-server

- License: MIT (`licenses/LICENSE-llama.cpp.txt`).
- The runtime binaries are not included. Distributors should include the
  upstream MIT license text and pin/document the build variant (CPU, CUDA,
  Vulkan, etc.).

## Python and Qt

### Python

- License: PSF-2.0 (Python Software Foundation License).
- Bundled by standalone builds. Include the Python license text from the
  Python distribution.

### PySide6, Shiboken6, Qt

- License: LGPL-3.0-only, with commercial alternatives (GPL options also
  exist upstream).
- SecOne dynamically links Qt/PySide6 components. Distribution should keep
  the LGPL text (`licenses/LGPL-3.0.txt`), the Qt/PySide6 license files,
  and allow recipients to replace the Qt dynamic libraries. Static linking
  or modified Qt builds require a separate compliance review.

## Python dependencies

| Component | Version in development | License | License text |
| --- | --- | --- | --- |
| PyYAML | 6.0.3 | MIT | `licenses/LICENSE-PyYAML.txt`, `licenses/python-packages/PyYAML-6.0.3/` |
| pypdf | 6.21.4 | BSD-3-Clause | `licenses/LICENSE-pypdf.txt`, `licenses/python-packages/pypdf-6.21.4/` |
| Pillow | 13.0.0 | MIT-CMU (HPND) | `licenses/LICENSE-Pillow.txt`, `licenses/python-packages/Pillow-13.0.0/` |
| py7zr | 1.1.4 | LGPL-2.1-or-later | `licenses/LICENSE-py7zr.txt`, `licenses/python-packages/py7zr-1.1.4/` |
| pybcj | 1.0.8 | LGPL-2.1-or-later | `licenses/python-packages/pybcj-1.0.8/` |
| pyppmd | 1.3.1 | LGPL-2.1-or-later | `licenses/python-packages/pyppmd-1.3.1/` |
| python-pycryptodomex | 3.24.1 | BSD-2-Clause / public domain portions | `licenses/python-packages/pycryptodomex-3.24.1/` |
| inflate64 | 1.0.4 | LGPL-2.1-or-later | `licenses/LGPL-2.1.txt`, `licenses/python-packages/inflate64-1.0.4/` |
| multivolumefile | 0.2.3 | LGPL-2.1-or-later | `licenses/LGPL-2.1.txt`, `licenses/python-packages/multivolumefile-0.2.3/` |
| Brotli | 1.2.1 | MIT | `licenses/python-packages/brotli-1.2.1/` |
| backports.zstd | 1.8.0 | PSF-2.0 backport + zstd BSD | `licenses/PSF-2.0.txt`, `licenses/python-packages/backports.zstd-1.8.0/` |
| texttable | 1.7.2 | MIT | `licenses/python-packages/texttable-1.7.2/` |
| psutil | 7.2.2 | BSD-3-Clause | `licenses/python-packages/psutil-7.2.2/` |

The `licenses/python-packages/` directory is generated from installed package
metadata with `scripts/collect_licenses.py`. Re-run it after upgrading
dependencies and update this table.

## Build-only tools (not redistributed)

- Nuitka (Apache-2.0) and Inno Setup (Inno Setup License) are used at build
  time. They are not installed as part of the SecOne application.
- pytest is a development/test dependency and is not part of the runtime
  distribution.
