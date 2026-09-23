# ai-review

A cheap AI first-pass code review, shared by every repository in the
organization. It reads a pull request's diff through the GitHub API and posts
what it finds as inline review comments in
[Conventional Comments](https://conventionalcomments.org) form, plus one
overview comment.

It is a first pass, not a review: it looks for obvious bugs — crashes,
unhandled errors, resource leaks, off-by-ones, breaches of the repo's own
documented conventions — and is told to say nothing rather than guess.

The pull request's code is never checked out or executed. Only the diff, and
the calling repo's conventions file, are sent to the model.

Lockfiles and vendored paths are filtered out of that diff — `EXCLUDE_REGEX`
sets which — and the model is told **which files were withheld**, because
silence is indistinguishable from absence. A filtered `package-lock.json` looks
exactly like a lockfile nobody updated, and a release bump then reads as a
clean install about to break: a blocking finding, on every release, always
wrong.

## Adding it to a repository

One file, `.github/workflows/ai-review.yml`:

```yaml
name: AI review
on:
  pull_request:
    types: [opened]
  workflow_dispatch:
    inputs:
      pr_number:
        description: PR number to review
        required: true
      model:
        description: Model ID override (blank = AI_REVIEW_MODEL)
        required: false
      effort:
        description: Reasoning effort override (blank = AI_REVIEW_EFFORT)
        required: false
permissions:
  contents: read
  pull-requests: write
concurrency:
  group: ai-review-${{ github.event.pull_request.number || inputs.pr_number }}
  cancel-in-progress: true
jobs:
  review:
    uses: dragonleech-code/ai-review/.github/workflows/ai-review.yml@v1
    with:
      pr_number: ${{ github.event.pull_request.number || inputs.pr_number }}
      model: ${{ inputs.model }}
      effort: ${{ inputs.effort }}
    secrets: inherit
```

`secrets: inherit` passes the organization's API key through. Nothing else is
needed: no key, no script, no model choice per repo.

## When it runs

- **Automatically** when a pull request is opened from a branch of the same
  repository. Drafts, Dependabot and fork PRs are skipped.
- **On demand** for anything else, including fork PRs, which GitHub gives no
  secrets. An admin of the calling repository runs:
  `gh workflow run ai-review.yml -f pr_number=123 [-f model=<id>]`.
  Dispatch requires admin because write access alone is enough to trigger and
  re-run workflows, and every run spends API credit.

## Configuration

Organization secrets and variables (Settings → Secrets and variables →
Actions). A repository-level value overrides the organization's.

| Name | Kind | Purpose |
| --- | --- | --- |
| `AI_REVIEW_API_KEY` | secret | Key for the provider. `OPENROUTER_API_KEY` is accepted as a fallback. |
| `AI_REVIEW_BASE_URL` | variable | API base URL. Default `https://openrouter.ai/api/v1`. |
| `AI_REVIEW_MODEL` | variable | Model ID as that provider names it. |
| `AI_REVIEW_EFFORT` | variable | `minimal`, `low`, `medium`, `high`, or `none`. Default `low`. |

Any OpenAI-compatible chat completions API works — OpenRouter, Gemini's
compatibility endpoint, OpenAI — so the provider is a variable, not a code
change.

### Choosing a model

Eight models were compared on two real pull requests: one clean, one carrying
six planted bugs. `openai/gpt-5.6-luna` caught all six and reported nothing on
the clean PR, at about $0.01 for a large PR. `google/gemini-3.1-pro-preview`
matched it at roughly ten times the cost. Everything else invented at least one
bug that did not exist.

Precision is what matters here: a confident, specific, wrong finding costs more
time than the review saves.

## Inputs

| Input | Required | Default | Purpose |
| --- | --- | --- | --- |
| `pr_number` | yes | — | PR to review, in the calling repository |
| `model` | no | `AI_REVIEW_MODEL` | Per-run model override |
| `effort` | no | `AI_REVIEW_EFFORT` | Per-run reasoning effort |
| `context_file` | no | `CLAUDE.md` | Repo conventions sent with the diff, skipped when absent |

The conventions file is read from the pull request's **base** commit, so a PR
cannot rewrite the instructions sent alongside its own diff.

### Point `context_file` at review-relevant rules, not at everything

`CLAUDE.md` is the default because most repositories have one, not because it
is the right file. In the repository this was built for it is 33.7 KB against a
2.5 KB diff — the conventions are **94% of the prompt**, and most of them are
about releases, branch protection and web server configuration, none of which a
diff can violate.

That is not only waste. A rule the reviewer cannot act on is a rule it can
misapply: a governance section forbidding mentions of AI produced a blocking
finding against a workflow whose job is to call an AI, on the grounds that the
workflow named it. The finding was impossible to act on and cost more than the
review saved.

So keep a separate, shorter file holding the rules whose violation is a real
failure — invariants, forbidden dependencies, unit conventions, the traps a
component can fall into — and point `context_file` at it:

```yaml
with:
  context_file: .github/review-conventions.md
```

Leave the process material where humans read it. The reviewer only needs what
a diff can break.

## Versioning

Callers pin `@v1`. The tag moves when the workflow changes, updating every
repository at once. The workflow checks out its own script at the same tag, so
both move together — bump the `ref:` in `.github/workflows/ai-review.yml` in
the same commit that cuts a new major tag.

## What it costs

Roughly $0.001–0.003 for a small PR and about $0.01 for a large one with
`gpt-5.6-luna`. Reasoning tokens bill as output and are not always reported
separately, so the script logs the full usage of every run.
