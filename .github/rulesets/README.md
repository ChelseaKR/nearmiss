# The committed branch ruleset

`main.json` is the ruleset live on `main`, captured from
`GET /repos/{owner}/{repo}/rulesets/18752849` on 2026-09-05.

It exists because branch protection is otherwise a setting with no evidence: it
lives in repository settings, it can be changed or removed without a commit, and
nothing in the history would show it. The README's CI/CD row claimed the gates
were merge-blocking while nothing committed said which ones were.

## What it does not claim

**The repository-admin role can bypass every rule, always.** That is in the file
as `bypass_actors`, faithfully, rather than omitted to make the posture read
better. A solo maintainer who cannot push to their own default branch has locked
themselves out rather than hardened anything, so this file is evidence of intent
rather than proof of enforcement against the owner.

## Four jobs run on a pull request and cannot block it

Capturing the live ruleset made this visible, and it is the reason the file is
worth committing:

| Job | Required? |
|---|---|
| `claims (docs-code claims-parity drift gate)` | **no** |
| `dco (Signed-off-by on every commit)` | no |
| `qgis-plugin (EXP-11 honest-symbology rules...)` | no |
| `build minimal public artifact` | no |

`claims` is the one that matters. It is the gate that catches a published claim
drifting from the code, and it currently reports that drift to nobody, because a
red `claims` does not stop a merge.

They are enumerated in `tests/test_ruleset.py`'s `NOT_REQUIRED` with a reason
each, so the list is reviewable rather than invisible, and a **fifth** one cannot
appear without the suite failing. Making a check required is a
repository-settings change, which this repository's own history says should be a
deliberate act rather than a side effect of a pull request, so nothing here
changes the live ruleset.

## What holds the file to the code

`tests/test_ruleset.py`, which reads the workflows rather than a hand-written
list:

- every pull-request job is required, or declared in `NOT_REQUIRED` with a reason;
- no required check names a job that cannot report, which would block every merge;
- no exemption outlives the job it excuses;
- nothing is both required and excused.

Matrix legs are expanded the way GitHub names them, so
`test (pytest, known-answer fixtures) (3.11)` matches rather than reading as
missing.

It deliberately does **not** compare against the live ruleset: a public-scope
token cannot read `bypass_actors`, and a check that silently drops a field it
could not read passes for the wrong reason. Re-capture with:

```sh
gh api repos/ChelseaKR/nearmiss/rulesets/18752849 \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({k: d[k] for k in ("name","target","enforcement","conditions","bypass_actors","rules")}, indent=2))' \
  > .github/rulesets/main.json
```
