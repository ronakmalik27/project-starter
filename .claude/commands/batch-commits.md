# /batch-commits - consolidate related local commits before pushing

Run before pushing, ahead of /review-gate. Scope: commits on the current
branch not yet on its remote.

1. `git fetch` first so the upstream ref is current, then find what is not yet
   pushed: `git log --oneline @{u}..HEAD` if the branch has an upstream, else
   `git log --oneline $(git merge-base origin/main HEAD)..HEAD` on a fresh
   branch.
2. One commit, or every commit is already a separate, complete,
   independently-reviewable logical change: push as-is, nothing to batch.
3. Two or more commits that are really one logical change in progress (fixups,
   "address review comment", "typo", incremental steps toward the same
   PR-level goal): consolidate before pushing.
   - Check the worktree is clean first (`git status`): uncommitted staged or
     unstaged changes would silently ride along into the batched commit. Stash
     them (`git stash push -u`) or commit them separately first, never fold
     them in unnoticed.
   - Extract the trailers before touching any commit:
     `git log --format='%(trailers:key=Co-Authored-By)' <base>..HEAD | grep . | sort -u`
     gives every distinct co-author line across the commits being combined,
     ready to re-append - never drop one, only deduplicate identical ones. The
     `grep .` matters: a commit with no trailer emits a blank line, and
     `sort -u` alone would let one stray blank line survive.
   - If the ENTIRE unpushed range is one logical change: `git reset --soft
     <base>` (the upstream tip, or the merge-base with main on a fresh branch),
     then recommit with one conventional-commit message plus the extracted
     trailers appended.
   - If only SOME of the unpushed commits belong together while others are
     genuinely separate: `git rebase -i <base>` and mark the related ones
     `squash`, not `fixup` - `fixup` discards the commit message (and with it
     every trailer), while `squash` opens a combined message you can edit,
     where the extracted trailers go. Keep the rest as their own commits.
     `reset --soft` cannot do this selectively; it flattens the whole range.
   - Keep genuinely separate logical changes as separate commits. This is about
     not pushing five times for one change, not squashing unrelated work.
   - Verify after recommitting: `git log -1` should show every expected trailer.
4. Never rewrite commits already on the remote without an explicit go-ahead -
   force-push stays a confirm-first action. This only ever touches commits that
   have never been pushed.
5. Push once. The point: every push re-triggers CI, which bills at least a
   per-job minimum regardless of how small the diff is - one push per coherent
   unit of work, not one per commit.
