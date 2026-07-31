# Check commit messages

Checks every non-merge commit in a pull request.

## Policy

- Commit titles should be at most 50 characters and must not exceed 60.
- Commit descriptions should wrap at 72 characters. Ordinary text must not
  exceed 79 characters.
- `Assisted-by` and `Co-authored-by` trailers must not credit common AI models
  or coding tools. Human attribution remains allowed.

Long URLs, recognized trailers, quoted text, fenced code blocks, and long
unwrappable tokens are exempt from description wrapping.

## GitHub Actions usage

The action requires a checkout with complete history:

```yaml
check-commit-messages:
  if: github.event_name == 'pull_request'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v7.0.0
      with:
        fetch-depth: 0
        persist-credentials: false
    - uses: airlift/github-actions/check-commit-messages@<commit-sha> # v1
      with:
        base_ref: ${{ github.event.pull_request.base.ref }}
```

Consumers should pin the action to a complete commit SHA.

## Local commit hook

The same checker is available as a
[`pre-commit`](https://pre-commit.com/) `commit-msg` hook. Add this
configuration to the consuming repository:

```yaml
minimum_pre_commit_version: 4.4.0
repos:
  - repo: https://github.com/airlift/github-actions
    rev: <commit-sha>
    hooks:
      - id: check-commit-message
```

Install `pre-commit`, then install the hook in each checkout:

```bash
pre-commit install --hook-type commit-msg --install-hooks
```

The hook checks the proposed message before Git creates the commit. Consumers
should pin the hook to a complete commit SHA.
