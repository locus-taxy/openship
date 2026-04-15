Push the current branch to its remote, after verifying the branch is in a safe state to push.

## Steps

1. Run `git status` — confirm there are no uncommitted changes. If there are, stop and tell the user to commit first with `/commit`.
2. Run `git log --oneline origin/$(git branch --show-current)..HEAD` (or `git log --oneline -5` if no upstream is set) to show what commits will be pushed. Display these to the user.
3. Check the current branch name:
   - If the branch is `main` or `master`, warn the user explicitly and ask for confirmation before pushing.
   - For any other branch, proceed.
4. Check if an upstream is set:
   - If yes: run `git push`.
   - If no: run `git push -u origin <branch-name>` to set the upstream.
5. Report the result — confirm the push succeeded or explain any error.

## Rules

- Never use `--force` or `--force-with-lease` unless the user explicitly asks, and even then warn about the consequences.
- Never push to `main`/`master` without asking the user to confirm first.
- If the push is rejected due to diverged history, explain the situation — do not automatically rebase or reset.
- Do not create pull requests — use `gh pr create` manually or ask the user if they want one.

$ARGUMENTS
