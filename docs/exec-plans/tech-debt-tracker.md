# Technical debt and setup gaps

Product features F06–F08 are deferred scope, not technical debt. No feature execution plan exists.

| Gap | Impact | Next action |
| --- | --- | --- |
| Initial Poetry resolution blocked by unavailable PyPI DNS | No generated lockfile or installed target environment; CI lock validation cannot pass yet | With network access, run `poetry lock`, `poetry sync`, `poetry check --lock --strict`, and `make verify`; commit the generated lockfile with dependency metadata |
| `.agents/` is read-only in the setup workspace | Conventional automatic repository-skill discovery is unavailable here | Read the three procedures in [skills](../../skills/README.md) manually; if discovery is desired in another environment, relocate them and update canonical links/checker paths |

Prepared Git hooks still require a Git checkout and deliberate activation; see [hooks](../HOOKS.md). Future provider, storage, and worker decisions are tracked in [Product](../product.md), not treated as implemented systems.
