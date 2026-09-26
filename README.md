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
        description: Model ID override (blank = choose by filtered diff size)
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
- **Model choice follows the filtered diff size.** Diffs below 128 KiB use
  `openai/gpt-6-sol`; diffs from 128 KiB to below 256 KiB use
  `openai/gpt-5.6-terra`; larger diffs use `openai/gpt-6-luna`. A `model` input
  overrides this selection. An optional `AI_REVIEW_MAX_DIFF_BYTES` variable or
  `max_diff_bytes` workflow input can still skip diffs above a chosen limit.

Dispatch requires admin because write access alone is enough to trigger and
re-run workflows, and every run spends API credit.

## Configuration

Organization secrets and variables (Settings → Secrets and variables →
Actions). A repository-level value overrides the organization's.

| Name                 | Kind     | Purpose                                                               |
| -------------------- | -------- | --------------------------------------------------------------------- |
| `AI_REVIEW_API_KEY`  | secret   | Key for the provider. `OPENROUTER_API_KEY` is accepted as a fallback. |
| `AI_REVIEW_BASE_URL` | variable | API base URL. Default `https://openrouter.ai/api/v1`.                 |
| `AI_REVIEW_EFFORT`   | variable | `minimal`, `low`, `medium`, `high`, or `none`. Default `medium`.      |
| `AI_REVIEW_MAX_DIFF_BYTES` | variable | Optional limit on filtered diff bytes; unset means no limit. |

Any OpenAI-compatible chat completions API works — OpenRouter, Gemini's
compatibility endpoint, OpenAI. The automatic model IDs use OpenRouter names;
pass a `model` input with the provider's ID when using another endpoint.

### Choosing a model

Eight models were compared on two real pull requests: one clean, one carrying
six planted bugs. `openai/gpt-5.6-luna` caught all six and reported nothing on
the clean PR, at about $0.01 for a large PR. `google/gemini-3.1-pro-preview`
matched it at roughly ten times the cost. Everything else invented at least one
bug that did not exist.

Precision is what matters here: a confident, specific, wrong finding costs more
time than the review saves.

#### Re-measured 2026-09-22/23, after the prompt and context changes

Twelve models, thirteen runs, against a pull request carrying five planted defects —
an off-by-one, a timer leak, a dropped consumer handler, a px unit, and a
`clip-path` erasing a focus ring. Reasoning effort `medium` throughout.

"Mechanism" is whether the model explained one particular defect correctly;
see below, and note that it does not track the score, the price or the release
date.

| Model                           | Caught                    | Mechanism | Cost              |
| ------------------------------- | ------------------------- | --------- | ----------------- |
| `openai/gpt-6-sol`              | 5/5                       | correct   | $0.0212           |
| `anthropic/claude-opus-5.5`     | 5/5                       | correct   | $0.0540           |
| `openai/gpt-5.6-sol`            | 4/5                       | correct   | $0.0228           |
| `z-ai/glm-5.3-flash`            | 5/5                       | wrong     | $0.0011           |
| `openai/gpt-5.6-luna`           | 5/5                       | wrong     | $0.0038           |
| `anthropic/claude-haiku-4.5`    | 5/5 (4/5 on a second run) | wrong     | $0.0205           |
| `anthropic/claude-sonnet-5`     | 5/5                       | wrong     | $0.0284           |
| `google/gemini-3.1-pro-preview` | 5/5                       | wrong     | $0.0482           |
| `google/gemini-3.8-flash`       | 4/5                       | wrong     | $0.0095           |
| `minimax/minimax-m2.5`          | 4/5                       | wrong     | $0.0025           |
| `openai/gpt-6-luna`             | 4/5                       | wrong     | $0.0017           |
| `deepseek/deepseek-v4.1-flash`  | —                         | —         | timed out at 300s |

**Read this as a result about the prompt, not about the models.** Before the
context was pruned and the contradictions taken out of the system prompt,
nothing scored above 4/5 and `gpt-5.6-luna` swung between 3/5 and 5/5 on
identical runs. Afterwards half the field is perfect across a 44× price range,
and `claude-haiku-4.5` scored 4/5 and 5/5 on two identical runs. The spread
within a model is now larger than the spread between models, which means five
planted bugs no longer separate current models and this particular bar has
stopped being useful.

**What did separate them was the reasoning, which the score does not see.** One
of the planted defects dropped a consumer's `onClick` by removing a `chain`
call. Every model that produced findings flagged it — eleven of the twelve,
since one timed out. Eight of those eleven explained it the same wrong way,
saying the `{...rest}` spread overwrote the handler. It does not — `onClick` is
destructured out of `rest`, so the handler is discarded rather than overridden,
and the line that would have shown this was outside the diff's three lines of
context. Three models said so correctly: `claude-opus-5.5` and both `gpt-*-sol`
models, none of them having been shown that line.

That split is the useful finding, because it tracks nothing else in the table.
Both `sol` models got it right and both `luna` models got it wrong, at the same
vendor; `claude-sonnet-5` got it wrong at the same price as `gpt-6-sol`, which
got it right; and the cheapest model in the table and the dearest are on
opposite sides of it. Recall, price and release date all fail to predict it.

Right finding, wrong mechanism, eight times over, matters more than the tally: it
says a model can reach the correct fix by matching a familiar pattern rather
than reading the code, and that a finding's stated reasoning deserves less
trust than the finding itself.

**It matters most when an agent, not a person, resolves the comments.** A human
reads a wrong explanation, shrugs and applies the obvious fix. An agent reasons
from the explanation it was given: told that a spread overwrote a handler, the
repair is to reorder the spread, which in this case fixes nothing. The runs
above survive that only because the `suggestion` field happened to carry the
right code. Where review comments are resolved automatically, prefer a model
from the "correct" column and keep a person on anything marked `blocking`.

**Recall is saturated; precision is not measured.** Every run above was against
a diff carrying five real defects, which is the condition where a model is
least likely to invent one. The original comparison's finding — that most
models report bugs that do not exist — is what chose the default, and nothing
in the table re-tests it. A clean-PR control was attempted and was not sound:
the pull request chosen had a deliberate licensing change in it, both models
tried flagged that one line, and whether they were wrong is a judgement rather
than a fact. Scoring false positives needs several uncontroversial pull
requests — a dependency bump, a docs-only change — and has not been done.

The small-diff tier uses **`openai/gpt-6-sol` at `medium`**. It is the
only model that scored 5/5 and explained the mechanism correctly, and it does
so at 39% of the cost of the other model that managed both. `medium` is the
only effort level with evidence behind it: both `luna` models went 3/5 to 4/5
on moving to it, and every 5/5 above was measured there. `high` is untested.

Two things that recommendation does not rest on. Precision is still unmeasured,
so the original eight-model result remains the only evidence that any model
here stays quiet on a clean pull request. And each cell is a single run, on a
bar that no longer separates models by score — `claude-haiku-4.5` scored 4/5
and 5/5 on two identical runs.

`z-ai/glm-5.3-flash` is the value candidate at a twentieth of the cost, and is
not recommended, for two reasons beyond the wrong mechanism: it is an
open-weights model served by some thirty providers at differing quantizations,
so a run does not reach a fixed target, and this script pins no provider.
Pinning one is a prerequisite for taking it seriously, not a refinement.

## Inputs

| Input          | Required | Default            | Purpose                                                  |
| -------------- | -------- | ------------------ | -------------------------------------------------------- |
| `pr_number`    | yes      | —                  | PR to review, in the calling repository                  |
| `model`        | no       | Size-based choice  | Per-run model override                                   |
| `effort`       | no       | `AI_REVIEW_EFFORT` | Per-run reasoning effort                                 |
| `context_file` | no       | `CLAUDE.md`        | Repo conventions sent with the diff, skipped when absent |
| `max_diff_bytes` | no     | No limit           | Optional skip limit after excluded paths are removed    |

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

About $0.02 a review with `gpt-6-sol` at `medium` — measured over a dozen runs
on a small pull request, where the prompt was roughly 3,000 tokens in and 1,300
out. A large diff costs more in proportion to the diff alone, since the
conventions file is a fixed cost paid on every review.

Two things move this more than the size of the pull request. Reasoning effort
is the main lever: the same model on the same diff cost $0.0017 at `low` and
$0.0038 at `medium`, and reasoning tokens bill as output whether or not the
provider reports them separately, so the script logs the full usage of every
run. And the conventions file dominates a small review — pruning it here took
the prompt from 8,998 tokens to 3,073, which was a larger saving than any
change of model.
