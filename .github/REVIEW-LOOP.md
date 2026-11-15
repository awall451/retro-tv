# The review loop

Every pull request the owner opens goes through three steps with no person involved, and
merges by itself when a fixed set of rules says it may. Pull requests from trusted authors
get the first and the third step.

1. **CodeRabbit reviews it** and rates how risky it is to merge.
2. **Claude answers the findings** (`workflows/coderabbit-fix.yml`). It checks each one
   against the code, fixes the real ones, and says why it left the others. One commit per
   round, two rounds at most. CodeRabbit reviews each fix again.
3. **The merge gate decides** (`workflows/merge-gate.yml`). It writes its reasons in one
   comment on the pull request, then merges or leaves the pull request for a person.

The gate is plain rules, no model. Every number below is in `merge-gate.json`.

## Layer 1: hard stops

Any one of these leaves the pull request for a person:

- it is a draft
- it was not opened by the repository owner or by someone listed under `trusted_authors`
- it goes into a branch other than the default branch
- CodeRabbit has not finished, or its review does not cover the latest commit
- CodeRabbit rates the merge risk or the security risk High or Critical
- a Critical or Major finding is still open
- another check failed or has not finished
- an automation file changed (`.github/`, CodeRabbit's settings, `CLAUDE.md`, `.gitignore`, `LICENSE`)
- more than two rounds of fixes, or the label `needs-human` is set
- it conflicts with the default branch

## Layer 2: the risk score

Six factors, added up.

| Factor | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Merge risk (CodeRabbit) | Minimal | Low | Moderate | |
| Security risk (CodeRabbit) | Minimal, Low | Moderate, or not rated | | |
| Size, code lines only | up to 500 | up to 2,000 | up to 5,000 | more |
| Spread | one area, few files | more than 10 code files | several areas | |
| Review history | clean first review | small findings, all fixed | a serious finding fixed, or a second round | a finding still open or not changed |
| Proof | checks ran and the change comes with tests | checks ran, no test changed | nothing ran the code | |

Size scores 0 when the change comes with tests. Docs, data files, lock files and minified
files never count toward size.

## Layer 3: a ceiling for each area

A pull request merges when its score is at or below the ceiling of the strictest area it
touches. A file belongs to the first area in `merge-gate.json` whose patterns match it.

| Area | Merges at or below |
|---|---|
| Docs, Markdown, images | 9 |
| Data files | 7 |
| App (`docker/web/app/`, `roku-tv/`) | 6 |
| Services and scripts (`ersatztv/`, `tools/`, the rest of `docker/`) | 5 |
| Device and deploy (`pi/`, `pi-image/`, compose, nginx, Dockerfile) | 3 |
| Automation | never |

## Other people's pull requests

Someone listed under `trusted_authors` in `merge-gate.json` is scored like the owner, and
their pull request merges by itself when it passes, also from their own copy (fork) of the
repository. Two things differ:

- Claude does not fix findings on their pull requests. It cannot push to someone else's
  copy, so the author answers CodeRabbit's findings.
- An author can mark a finding's thread as resolved on their own pull request. Trusting
  someone includes trusting them not to close a finding they have not dealt with.

Anyone not on the list is always left for a person.

## Changing it

- **Stricter or looser**: change a ceiling or a score in `merge-gate.json`.
- **Report only**: set `"mode": "dry-run"`. The gate then comments and merges nothing.
- **Teach the risk rating**: `merge_risk_instructions` in `.coderabbit.yaml` tells
  CodeRabbit what makes a change risky in this repository.
- **Stop one pull request**: add the label `needs-human`. Only a person takes it off.
- **Run a step by hand** (owner only): comment `/fix-review` or `/gate` on the pull request.

Changes to these files are never merged by the gate itself.

## What it needs

- The repository secret `CLAUDE_CODE_OAUTH_TOKEN`, made with `claude setup-token`.
- CodeRabbit installed on the repository.
- A branch rule on the default branch that requires the status `merge-gate` in place of
  an approving review. The owner can still merge anything by hand.

## Known limits

- Claude cannot run code in its job, so its fixes are read and syntax-checked only.
- The loop pushes with the workflow's own token, and GitHub starts no other workflow
  from such a push. In a repository with CI, the fix commits would not be tested.
- The risk ratings are CodeRabbit's opinion. The security rating is part of its
  Advanced plan; without it the factor reads "not rated".
