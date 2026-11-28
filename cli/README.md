# orbital-cli

Command-line interface for [Orbital](https://github.com/gggard/orbital):
deploy and manage apps from a terminal, a CI pipeline or an AI agent.

```bash
uvx orbital-cli --help
```

See the [CLI guide](https://gggard.github.io/orbital/CLI/) (source:
[docs/CLI.md](../docs/CLI.md)) for installation, authentication, CI
recipes and the full command reference.

## Development

```bash
make cli-install   # from the repo root: installs the CLI and the control plane in .venv
make cli-test cli-lint cli-typecheck
```

The contract tests in `tests/test_contract.py` run CLI commands against the
real control-plane API in-process, so they need the `orbital` package
installed too (`make cli-install` does both); they're skipped otherwise.
