<!-- Choose labels using the checkbox groups below. Keep the markers intact.
Guide: https://github.com/di-rs/sanctuary/blob/master/CONTRIBUTING.md -->

## Intent

<!-- State the problem, desired outcome, and relevant constraints in one or two
sentences. Link a related issue if applicable. -->

Choose one primary type.

<!-- labels:type -->

- [ ] `type:feature` — Add or extend supported behavior.
- [ ] `type:fix` — Correct incorrect behavior.
- [ ] `type:refactor` — Restructure implementation without intended behavior changes.
- [ ] `type:performance` — Improve runtime, memory use, or throughput.
- [ ] `type:docs` — Change documentation only.
- [ ] `type:tests` — Change tests, fixtures, or reference generators only.
- [ ] `type:dependencies` — Update dependencies or lockfiles.
- [ ] `type:maintenance` — Change CI, packaging, development tooling, or repository policy.

<!-- /labels:type -->

## What Changed

<!-- Describe the final behavior and key changes in a few concise bullets.
Include material limitations, breaking changes, or follow-up work here.
For compatibility/API work, name the reference and affected CLI/library behavior;
link updated contracts or audit records when relevant. -->

## Risk Assessment

<!-- State Low, Medium, or High with a concrete reason: what could break and who
or what is affected. Mention mitigation or accepted regressions when relevant.
A short sentence is enough. -->

Choose one risk level and explain it above.

<!-- labels:risk -->

- [ ] `risk:low` — Narrow, readily reversible change with limited consequences if incorrect.
- [ ] `risk:medium` — Runtime or shared behavior changes with a bounded impact.
- [ ] `risk:high` — Potential data loss, trust-boundary changes, privileged operations, or difficult recovery.

<!-- /labels:risk -->

## Impact

<!-- Describe the expected effect on the repository as a whole after merge.
Quantify relevant outcomes, such as CI duration, failure rate, resource usage,
dependency count, or maintenance effort, with a baseline and expected change.
Distinguish measured results from estimates; if no useful metric is available,
state the observable outcome and how it can be verified. Explain consequences
for contributors, consumers, or ongoing maintenance, including trade-offs.
Keep this focused on outcomes rather than repeating implementation details. -->

Select all applicable impacts, or None alone.

<!-- labels:impact -->

- [ ] `impact:breaking` — Incompatible change to supported CLI, API, schema, or configuration behavior.
- [ ] `impact:security` — Changes authentication, permissions, isolation, or sensitive data handling.
- [ ] `impact:persistence` — Changes saved files, history, databases, storage formats, or recovery.
- [ ] `impact:performance` — Changes a hot path or makes a performance claim requiring evidence.
- [ ] `impact:cross-platform` — Changes OS-dependent filesystems, permissions, signals, terminals, or platform APIs.
- [ ] `impact:none` — None of the above.

<!-- /labels:impact -->

## Testing/Validation

<!-- Summarize checks and outcomes in one or two short bullets. Mention material
failures or unverified behavior. For performance claims or hot-path changes, link
benchmark evidence or state why it is unavailable. Omit logs, test counts, and
repeated runs. This reports completed verification; it does not request new checks. -->
