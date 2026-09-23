# Issue tracker: GitHub

Issues and PRDs for Google Ads Assets Studio live in https://github.com/Samuel-Ku/google-ads-assets-generator/issues. Use the `gh` CLI for all operations.

Repository: `Samuel-Ku/google-ads-assets-generator`. Pass `--repo Samuel-Ku/google-ads-assets-generator` explicitly on every `gh issue` or `gh pr` command; this workspace is not currently a Git clone.

## Conventions

- **Create an issue**: `gh issue create --repo Samuel-Ku/google-ads-assets-generator --title "..." --body "..."`. For multi-line bodies, write the exact text to a temporary UTF-8 file and pass `--body-file <path>`; preserve real newlines.
- **Read an issue**: `gh issue view --repo Samuel-Ku/google-ads-assets-generator <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --repo Samuel-Ku/google-ads-assets-generator --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment --repo Samuel-Ku/google-ads-assets-generator <number> --body "..."`
- **Apply / remove labels**: `gh issue edit --repo Samuel-Ku/google-ads-assets-generator <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close --repo Samuel-Ku/google-ads-assets-generator <number> --comment "..."`

Always target `Samuel-Ku/google-ads-assets-generator` explicitly. For `gh api`, use `repos/Samuel-Ku/google-ads-assets-generator/...`. Do not infer a repository from the current directory or another project. If CLI authentication fails, stop the external operation and request reauthentication; do not request that tokens be pasted into chat.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view --repo Samuel-Ku/google-ads-assets-generator <number> --comments` and `gh pr diff --repo Samuel-Ku/google-ads-assets-generator <number>` for the diff.
- **List external PRs for triage**: `gh pr list --repo Samuel-Ku/google-ads-assets-generator --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment --repo Samuel-Ku/google-ads-assets-generator`, `gh pr edit --repo Samuel-Ku/google-ads-assets-generator --add-label`/`--remove-label`, `gh pr close --repo Samuel-Ku/google-ads-assets-generator`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view --repo Samuel-Ku/google-ads-assets-generator 42` and fall back to `gh issue view --repo Samuel-Ku/google-ads-assets-generator 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view --repo Samuel-Ku/google-ads-assets-generator <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --repo Samuel-Ku/google-ads-assets-generator --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/Samuel-Ku/google-ads-assets-generator/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/Samuel-Ku/google-ads-assets-generator/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --repo Samuel-Ku/google-ads-assets-generator --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit --repo Samuel-Ku/google-ads-assets-generator <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment --repo Samuel-Ku/google-ads-assets-generator <n> --body "<answer>"`, then `gh issue close --repo Samuel-Ku/google-ads-assets-generator <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
