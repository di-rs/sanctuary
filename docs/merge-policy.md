# Maintain the default-branch merge policy

Sanctuary's [checked-in ruleset](../.github/rulesets/gitmoji-commits.json) defines
the required check names, their GitHub App IDs, and the allowed merge methods.
Maintainers should compare it with GitHub during weekly dependency maintenance
and after changes to rulesets, required-check workflows, or merge settings.
Resolve drift before the next merge. [Dependency maintenance](dependency-updates.md)

## Compare with GitHub

From the root of a current Sanctuary checkout, run this read-only check with
`uv` and the GitHub CLI (`gh`) on your path. Use a `gh` login with read access
to the repository. [GitHub CLI authentication](https://cli.github.com/manual/gh_auth_login)

```sh
uv run --locked python tools/repository_policy/check.py
```

The script reads the repository's default branch and all active rules that
apply to it. It collects required check name and app ID pairs and intersects
the merge methods allowed by those rules. It also compares the repository's
enabled merge methods independently with the checked-in policy. Check classic
branch protection, bypass lists, and review settings in GitHub when reconciling
a rule.
[GitHub rules API](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch) ·
[Rule layering](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets#about-rule-layering)

| Exit | Result |
| --- | --- |
| `0` | The compared settings match. |
| `1` | The report lists missing or unexpected checks, including their app sources, and any merge-method differences. |
| `2` | The comparison could not complete. Check the reported input, `gh auth status`, and network access, then retry. |

## Reconcile drift

1. Confirm the intended policy in the checked-in ruleset. Before adding or
   changing a required check, find a ready-for-review PR targeting the default
   branch. Use its head SHA to inspect exact check names, app IDs, and results.
   Replace `320` below with the PR number you are verifying. Each intended
   check should have a completed, successful run from the configured app on
   that commit. GitHub Actions uses app ID `15368` for Sanctuary's four checks.
   [Audit PR](https://github.com/di-rs/sanctuary/pull/320) ·
   [Check runs API](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference)

   ```sh
   pr=320
   sha=$(gh pr view "$pr" --repo di-rs/sanctuary --json headRefOid --jq .headRefOid) &&
     gh api --method GET --paginate \
       "repos/di-rs/sanctuary/commits/$sha/check-runs?per_page=100" \
       --jq '.check_runs[] | [.name, .app.id, .app.slug, .status, .conclusion, .details_url] | @tsv'
   ```

2. Ask a repository administrator to record the current ruleset and merge
   settings, then edit the active **Pull request merge policy** ruleset for the
   default branch in **Settings → Rules → Rulesets**. Set the required status
   checks to the exact names in the checked-in ruleset and select **GitHub Actions**
   as their expected source. Set **Allowed merge methods** under **Require a pull
   request before merging** to **Squash** only. Preserve unrelated rules and
   review requirements. [Active ruleset](https://github.com/di-rs/sanctuary/rules/25029558) ·
   [Available rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

3. In **Settings → General → Pull Requests**, the administrator enables
   **Allow squash merging** and disables **Allow merge commits** and **Allow
   rebase merging**. [GitHub merge methods](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github)

4. Run the comparison again and require exit `0`. On the verification PR,
   confirm GitHub marks all four checks as required and offers only squash
   when the PR is otherwise eligible to merge. Record the observed check links,
   head SHA, and comparison result in the maintenance PR. If the change blocks
   merges on an otherwise eligible PR, the administrator can restore the
   recorded settings, confirm the rollback, and correct the mismatch before
   trying again.
