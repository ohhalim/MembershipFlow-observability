# Branch workflow

## Repository bootstrap

The empty repository requires one initial commit on `main`. Create `develop` from that commit.
This is the only direct initialization exception. All later changes use pull requests.

## Issue work

1. Create an issue before changing code or infrastructure.
2. Create `<type>/<issue-number>/<keyword>` from the latest `develop`.
3. Open a pull request from the issue branch to `develop`.
4. Merge only after CI passes.

Allowed types: `feat`, `fix`, `refactor`, `chore`, `test`, `docs`, `setting`, `hotfix`, `perf`.

Example:

```text
setting/12/monitoring-compose -> develop
```

## Release

1. Create a release issue.
2. Open the release pull request directly from `develop` to `main`.
3. Do not create `release/*`, `codex/*`, or another intermediate branch.
4. Merge only after CI passes and the deployment scope is confirmed.

```text
develop -> main
```

Direct pushes to `develop` and `main` are prohibited after repository bootstrap.

