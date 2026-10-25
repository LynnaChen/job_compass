# Security and private data

This application is designed for one person on their own computer. It binds to loopback only, checks Host and Origin on writes, and requires a session token. It is not a public hosted multi-user application.

Resume PDFs and raw text are not persisted. Confirmed skill terms and preferences, application notes and progress are private runtime data. Do not commit `data/`, `.env` files, local environments or personal documents. The source-only release script provides a stronger boundary than zipping the project folder yourself.

Keep pypdf updated within the supported major version when reviewing dependency updates. Do not submit private CVs, credentials, raw database files or application notes in public issues. For a bug report, use a synthetic resume and a minimal reproduction. The public repository contains only synthetic test fixtures.

Source URLs are limited to public HTTP(S) hosts and standard ports. Extracted text is escaped before rendering, and content from job pages is treated as data. PDF parsing is limited to 5 MB and 15 pages; no OCR, scripts or PDF actions are executed. Do not expose the local port through a public tunnel or shared host without adding a separate authentication and isolation layer.
