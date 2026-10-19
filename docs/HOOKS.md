# Git hooks and mechanical feedback

Two executable POSIX Git hooks are prepared. This directory was not a Git checkout during setup; no repository was initialized and no hook configuration was activated.

| Hook | Command |
| --- | --- |
| [pre-commit](../.githooks/pre-commit) | `make verify-fast` |
| [pre-push](../.githooks/pre-push) | `make verify` |

Both use `set -eu`, change to the Git root, and propagate failures. They do not stage, stash, commit, rewrite source, apply migrations, invoke AI, or contact product services. Checks can produce ignored cache/coverage artifacts. Pre-push checks every invocation, including deletion-only pushes; no ref-based skip is implemented.

Prerequisites are Git, POSIX sh, Make, Poetry, Python, and installed locked dependencies. Fast checks should take normal lint/typecheck time; full verification also runs tests. There is no artificial timeout or retry loop. Interrupt hung checks and diagnose the underlying command directly.

## Activation and coexistence

After creating or cloning a Git checkout, inspect the effective configuration:

```sh
git config --show-origin --get core.hooksPath
```

If no custom path or hook manager exists, activation is a deliberate checkout action:

```sh
git config --local core.hooksPath .githooks
```

Preserve existing custom hooks/managers; integrate the commands or report a conflict. Never change global configuration. To disable this installation, first verify the local path still equals `.githooks`, then run `git config --local --unset core.hooksPath`. Restore executable bits only on the two hook files if needed.

Run failing commands directly and fix scoped failures without weakening checks or silently bypassing hooks. Tests run both scripts with temporary stubbed Git/Make commands to check root selection, command choice, and propagation of failures. They also test that failed fast checks prevent tests in aggregate verification.

Hooks inspect the working tree, not the exact partially staged commit or pushed revision. CI runs metadata/lock validation, installs locked dependencies, and executes `make verify` on the checked-out revision. Host-specific lifecycle hooks are not configured; every check remains directly invokable.
