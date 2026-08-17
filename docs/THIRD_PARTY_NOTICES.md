# Third-Party Notices

This is a practical inventory for the current source tree, not legal advice
and not a replacement for the license files shipped by each dependency. The
application itself is released under the [MIT License](../LICENSE).

## Direct runtime dependencies

The Python requirements are intentionally expressed as compatible ranges in
`requirements.txt`, so the exact installed version can vary. These are the
license declarations observed for the direct packages used by this project:

| Component | License | Source |
| --- | --- | --- |
| FastAPI | MIT | [FastAPI repository](https://github.com/fastapi/fastapi) |
| Google Gen AI SDK | Apache-2.0 | [googleapis/python-genai](https://github.com/googleapis/python-genai) |
| HTTPX | BSD-3-Clause | [encode/httpx](https://github.com/encode/httpx) |
| NumPy | BSD-3-Clause, 0BSD, MIT, Zlib, CC0-1.0 | [NumPy licenses](https://numpy.org/doc/stable/license.html) |
| OpenCV headless wheels | Apache-2.0 | [opencv-python](https://github.com/opencv/opencv-python) |
| Pydantic | MIT | [pydantic/pydantic](https://github.com/pydantic/pydantic) |
| python-dotenv | BSD-3-Clause | [theskumar/python-dotenv](https://github.com/theskumar/python-dotenv) |
| python-multipart | Apache-2.0 | [Kludex/python-multipart](https://github.com/Kludex/python-multipart) |
| Uvicorn | BSD-3-Clause | [encode/uvicorn](https://github.com/encode/uvicorn) |

The frontend's direct runtime dependencies are Next.js 16.3.1, React 19.2.8,
and React DOM 19.2.8, each distributed under the MIT License. The exact
development dependencies and transitive packages are recorded in
`frontend/package-lock.json` and retain their upstream licenses.

## Media tools

The backend image installs FFmpeg from the base distribution. FFmpeg is
available under LGPL 2.1-or-later, with GPL-licensed components enabled by
some builds. The exact obligations depend on the binary and its configure
flags. Confirm the deployed image with `ffmpeg -version`, preserve the binary's
license notices, and review the relevant FFmpeg and codec licenses before
redistributing the image.

## External services

Google Gemini, Google Veo, and ElevenLabs are hosted services called through
their APIs; their SDKs and terms are separate from this repository's MIT
license. A deployment must comply with the current provider terms, pricing,
commercial-use rules, privacy notices, and attribution requirements. See the
[AI disclosure](AI_DISCLOSURE.md) for the data sent to each service.

## Release procedure

Before public distribution, generate an SBOM and a complete transitive license
report for the exact Python environment and frontend lockfile used to build the
release. Recheck the container's FFmpeg package and any provider-specific
terms after changing dependencies, base images, or model providers.
