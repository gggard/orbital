# Contributing to Orbital

Thanks for your interest in improving Orbital. This document covers
the mechanics of contributing; for local environment setup (minikube, the
console, the demo auth stack) see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Before you start

For anything beyond a small fix, please open an issue first to discuss the
approach — it avoids wasted work on a PR that doesn't fit the project's
direction. Check [SPEC.md](SPEC.md) for the current functional spec and the
README's Status section for what's already in progress.

## Making changes

1. Fork the repo and create a branch off `main`.
2. Follow the setup in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) to run the
   control plane and console locally.
3. Keep changes focused — one logical change per PR makes review faster and
   keeps `git bisect` useful.
4. Add or update tests under `tests/` for control-plane changes. There's no
   fixed style guide; match the conventions already used in the file you're
   editing.

## Before opening a PR

Run what CI runs:

```bash
make test        # control plane (pytest)
cd ui && npm run build   # console (Next.js build)
```

Both the `test-python` and `build-ui` jobs in
[.github/workflows/ci.yml](.github/workflows/ci.yml) must pass on your PR.

## Commit messages and PRs

- Write commit messages that explain *why*, not just *what* — see recent
  history (`git log`) for the expected tone.
- Reference the issue your PR addresses with `Fixes #123` or `Closes #123`
  in the PR description so it's linked and closed automatically on merge.
- Keep the PR description scoped to what a reviewer needs: what changed and
  why, plus how you tested it.

## Reporting bugs

Open a GitHub issue with steps to reproduce, what you expected, and what
happened instead. Include relevant logs (`kubectl logs`, browser console,
control-plane output) where applicable.

## License

By contributing, you agree that your contributions will be licensed under
the project's [GPL-3.0 license](LICENSE).
