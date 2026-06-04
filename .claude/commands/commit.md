Stage and commit all current changes with a well-formed commit message.

## Steps

1. Run `git status` to see what has changed.
2. Run `git diff` (staged and unstaged) to understand the nature of the changes.
3. Run `git log --oneline -5` to match the existing commit message style.
4. Stage relevant files with `git add` — prefer explicit file paths over `git add -A`. Never stage `.env`, secrets, or large binaries.
5. Write a commit message that:
   - Uses an imperative-mood subject line under 72 characters
   - Prefixes with one of: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
   - Adds a short body if the change needs a "why" explanation
   - Ends with the Co-Authored-By trailer
6. Commit using a HEREDOC to preserve formatting:

```bash
git commit -m "$(cat <<'EOF'
<subject line>

<optional body>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

7. Run `git status` after the commit to confirm it succeeded.

## Rules

- Never use `--no-verify` or skip hooks.
- Never amend a previous commit — always create a new one.
- Never commit if there is nothing staged.
- If a pre-commit hook fails, fix the issue and retry as a new commit.
- Do not push — use `/push` for that.

$ARGUMENTS
