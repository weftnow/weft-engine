# API presentation

This is a backend-only service with no application UI, visual tokens, component system, or browser interaction design. Development Swagger UI is generated from typed FastAPI routes. `GET /health` is the only application route and returns a small typed JSON response. Production disables the OpenAPI route and Swagger UI.

Future HTTP interfaces must use explicit response schemas, stable machine-readable errors, documented validation/status semantics, and versioned contracts. Do not expose raw provider exceptions, credentials, profile snapshots, or organizer-only facts through generic error payloads. Match explanations need their own visibility rules before user-facing delivery. These are interface requirements for future work, not implemented matching endpoints.
