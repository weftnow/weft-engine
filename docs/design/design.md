# API presentation

This is a backend-only service with no application UI, visual tokens, component system, or browser interaction design. Development Swagger UI is generated from typed FastAPI routes. The public `GET /health` route returns a small typed JSON response; versioned matching routes are service-authenticated. Production disables the OpenAPI route and Swagger UI.

HTTP interfaces use explicit response schemas, stable machine-readable errors, documented validation/status semantics, and versioned contracts. Do not expose raw provider exceptions, credentials, profile snapshots, or organizer-only facts through generic error payloads. Matching explanations have their own visibility rules before user-facing delivery; see the [F06 API contract](../matching-api.md).
