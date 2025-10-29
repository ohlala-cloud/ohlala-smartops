# Branch Protection Setup Guide

This guide walks you through setting up branch protection rules for the Ohlala SmartOps repository on GitHub.

## Prerequisites

- Repository owner or admin access
- Repository pushed to GitHub

## Setting Up Branch Protection for `main`

### Step 1: Navigate to Branch Protection Settings

1. Go to your repository on GitHub: `https://github.com/ohlala-cloud/ohlala-smartops`
2. Click **Settings** tab
3. Click **Branches** in the left sidebar
4. Click **Add branch protection rule**

### Step 2: Configure Protection Rule

#### Branch Name Pattern

```
main
```

#### Protect Matching Branches

Enable the following settings:

##### ✅ Require a pull request before merging

- **Required approvals**: `1`
- ✅ **Dismiss stale pull request approvals when new commits are pushed**
- ✅ **Require review from Code Owners** (optional but recommended)
- ⬜ Require approval of the most recent reviewable push (optional)

##### ✅ Require status checks to pass before merging

- ✅ **Require branches to be up to date before merging**
- **Required status checks** (add as they appear after first CI run):
  - `code-quality`
  - `tests (Python 3.13)`
  - `security`
  - `build`

##### ✅ Require conversation resolution before merging

All PR conversations must be resolved before merging.

##### ✅ Require signed commits (Optional but Recommended)

Requires all commits to be signed with GPG/SSH keys.

##### ✅ Require linear history

**IMPORTANT**: This enforces squash or rebase merges and prevents merge commits.

##### ✅ Require deployments to succeed before merging (Optional)

If you have deployment checks configured.

##### ⬜ Lock branch (Do Not Enable)

This would prevent all pushes to the branch, including from admins.

##### ✅ Do not allow bypassing the above settings

Ensures that even administrators must follow the branch protection rules.

##### ⬜ Restrict who can dismiss pull request reviews (Optional)

##### ⬜ Allow specified actors to bypass required pull requests (Optional)

Only use for emergency hotfix access.

##### ✅ Restrict pushes that create matching branches

Limits who can create branches matching this name pattern.

##### ✅ Allow force pushes - Everyone (⚠️ DO NOT ENABLE)

Force pushes should never be allowed on `main`.

##### ✅ Allow deletions (⚠️ DO NOT ENABLE)

The `main` branch should never be deleted.

### Step 3: Save Protection Rule

Click **Create** or **Save changes** at the bottom of the page.

## Setting Up Repository Settings

### General Settings

Navigate to **Settings** → **General**:

#### Pull Requests

- ✅ **Allow squash merging**
  - Default message: `Pull request title and commit details`
- ⬜ **Allow merge commits** (DISABLE)
- ⬜ **Allow rebase merging** (DISABLE)
- ✅ **Always suggest updating pull request branches**
- ✅ **Automatically delete head branches**

This ensures all merges to `main` are squash merges, maintaining a clean linear history.

## Setting Up Required Workflows

### Enabling GitHub Actions

Navigate to **Settings** → **Actions** → **General**:

- **Actions permissions**: `Allow all actions and reusable workflows`
- **Workflow permissions**: `Read and write permissions`
- ✅ **Allow GitHub Actions to create and approve pull requests**

### Adding Status Checks

Status checks will appear automatically after your first CI workflow runs. You can then add them to the branch protection rule:

1. Make an initial commit and push to trigger CI
2. Wait for CI to complete
3. Go back to branch protection settings
4. Add the check names that appear to required status checks

## Configuring CODEOWNERS

The `.github/CODEOWNERS` file is already configured. To make it effective:

1. Create a GitHub team: `ohlala-smartops-maintainers`
2. Add repository maintainers to the team
3. The team will automatically be requested for review on all PRs

Alternatively, replace team references with individual usernames:

```
# In .github/CODEOWNERS
* @yourusername
```

## Setting Up Notifications

### For Pull Requests

Navigate to **Settings** → **Notifications** (personal settings):

- Configure how you want to be notified about PRs, reviews, and mentions

### For Status Checks

Navigate to repository **Settings** → **Integrations**:

- Configure notifications for failing CI checks

## Verification Checklist

After setup, verify the following:

- [ ] Cannot push directly to `main` branch
- [ ] Must create PR to merge to `main`
- [ ] PR requires at least 1 approval
- [ ] CI checks must pass before merge is allowed
- [ ] Only squash merge button is available
- [ ] Merge commits and rebase merges are disabled
- [ ] Feature branches are automatically deleted after merge
- [ ] CODEOWNERS are automatically added as reviewers

## Testing Branch Protection

### Test 1: Direct Push (Should Fail)

```bash
git checkout main
echo "test" >> test.txt
git add test.txt
git commit -m "test"
git push origin main
# Should fail with: "protected branch hook declined"
```

### Test 2: PR Workflow (Should Work)

```bash
git checkout -b test/branch-protection
echo "test" >> test.txt
git add test.txt
git commit -m "test: verify branch protection"
git push origin test/branch-protection
# Create PR on GitHub
# Verify:
# - CI runs automatically
# - Cannot merge until approved
# - Cannot merge until CI passes
# - Only squash merge available
```

## Troubleshooting

### CI Checks Not Appearing

- Ensure `.github/workflows/ci.yml` exists and is valid
- Push a commit to trigger the workflow
- Check **Actions** tab for workflow runs
- Status check names appear after first successful run

### Cannot Add Required Status Checks

- Status checks must run at least once before they can be added as required
- Make sure CI workflow has run successfully
- Check that the status check names match exactly

### CODEOWNERS Not Working

- Ensure team name is correct: `@ohlala-cloud/ohlala-smartops-maintainers`
- Or replace with individual GitHub usernames
- Team must have write access to the repository

## Additional Security Settings

### Enable Security Features

Navigate to **Settings** → **Security**:

- ✅ **Dependency graph**
- ✅ **Dependabot alerts**
- ✅ **Dependabot security updates**
- ✅ **Secret scanning**
- ✅ **Push protection** (prevents committing secrets)

### Configure Secrets

Navigate to **Settings** → **Secrets and variables** → **Actions**:

Add required secrets for CI/CD:

- `CODECOV_TOKEN` (if using Codecov)
- `PYPI_TOKEN` (if publishing to PyPI)

## Maintenance

### Regular Reviews

- Review branch protection rules quarterly
- Update required status checks as CI evolves
- Review and update CODEOWNERS as team changes

### Updating Protection Rules

To update protection rules:

1. Navigate to **Settings** → **Branches**
2. Click **Edit** on the protection rule
3. Make changes
4. Click **Save changes**

---

**Note**: These settings ensure a clean, protected git history with squash merges to main, as specified in the project requirements.
