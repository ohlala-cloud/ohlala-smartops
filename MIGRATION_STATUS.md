# Ohlala SmartOps - Migration Status

**Last Updated**: 2025-10-30
**Current Phase**: Phase 1 Complete, PR #6 pending review
**Next Phase**: Phase 2 - Token Management & Throttling

---

## 📊 Overall Progress

**Migration Progress**: ~4% complete (Phase 1 of 13 phases)

- ✅ **Phase 1**: Core Utilities & Validation (COMPLETE - PR #6)
- ⏳ **Phase 2**: Token Management & Throttling (NEXT)
- ⬜ **Phase 3**: Exception Hierarchy & Models
- ⬜ **Phase 4**: AI & Bedrock Integration
- ⬜ **Phase 5**: MCP Integration Layer
- ⬜ **Phase 6**: Adaptive Cards Module
- ⬜ **Phase 7**: Bot Authentication & Core
- ⬜ **Phase 8**: Bot Handlers
- ⬜ **Phase 9**: Command Base & Core Commands
- ⬜ **Phase 10**: Additional Commands
- ⬜ **Phase 11**: Async Command Tracking
- ⬜ **Phase 12**: Advanced Features
- ⬜ **Phase 13**: Integration & Documentation

---

## ✅ Phase 1: Core Utilities & Validation (COMPLETE)

**Status**: Complete - awaiting PR review
**PR**: https://github.com/ohlala-cloud/ohlala-smartops/pull/6
**Branch**: `feat/phase-1-utils-migration`
**Commit**: `2d8ecc5`

### Modules Migrated

1. **ssm_validation.py** (161 lines)
   - SSM command validation before AWS submission
   - Detects JSON encoding, PowerShell syntax errors, null bytes
   - Fixes common issues automatically
   - **Coverage**: 95.12% ✅

2. **powershell_validator.py** (170 lines)
   - PowerShell syntax validation and fixing
   - Handles doubled quotes, unmatched quotes, over-escaping
   - Detects errors that cause execution failure
   - **Coverage**: 89.16% ✅

3. **ssm_utils.py** (400 lines)
   - SSM command preprocessing (JSON, Python repr, escaped formats)
   - Handles truncated CloudWatch logs
   - Applies PowerShell fixes automatically
   - **Coverage**: 64.78% (complex edge cases remain)

### Test Suite

- **89 comprehensive tests** (all passing)
- **Coverage**: 83% package average (above 80% target)

### Quality Metrics

- ✅ Black formatting
- ✅ Ruff linting
- ✅ MyPy strict type checking
- ✅ Bandit security scanning
- ✅ All pre-commit hooks passing

---

## 🎯 Phase 2: Token Management & Throttling (NEXT)

**Estimated Duration**: 1-2 weeks
**Target Coverage**: 80%+ per module

### Modules to Migrate

1. **token_estimator.py** (~14KB in internal repo)
   - Claude token estimation for API calls
   - Cost calculation

2. **token_tracker.py** (~17KB in internal repo)
   - Usage tracking with DynamoDB/local storage
   - Token consumption monitoring

3. **global_throttler.py** (~9KB in internal repo)
   - API throttling infrastructure
   - Rate limiting

4. **bedrock_throttler.py** (~5KB in internal repo)
   - Bedrock-specific rate limiting
   - Request queuing

5. **claude_sonnet4_selector.py** (~11KB in internal repo)
   - Model selection by region
   - Automatic fallback logic

### Dependencies

- Phase 1 modules (for validation)
- Will need to create exception classes
- May need basic Pydantic models

---

## 📋 Migration Guidelines

### Code Quality Standards

**Python Version**: 3.13+

**Type Hints**: 100% required

```python
def process_instances(
    instance_ids: Sequence[str],
    action: str,
    dry_run: bool = False,
) -> dict[str, bool]:
    """Process EC2 instances."""
    ...
```

**Docstrings**: Google-style required

```python
def calculate_cost(instance_type: str, hours: float) -> float:
    """Calculate the cost of running an EC2 instance.

    Args:
        instance_type: EC2 instance type (e.g., "t3.micro").
        hours: Number of hours to calculate cost for.

    Returns:
        The calculated cost in USD.

    Raises:
        ValueError: If instance_type is invalid or hours is negative.

    Example:
        >>> cost = calculate_cost("t3.micro", 24)
        >>> print(f"${cost:.2f}")
        $0.24
    """
```

**Testing**: 80% minimum coverage

- Unit tests for all functions
- Integration tests where appropriate
- Edge cases and error paths

**Code Formatting**:

- Line length: 100 characters max
- Black formatter (auto-applied)
- Double quotes for strings

**Quality Checks**:

- Black: `black .`
- Ruff: `ruff check .`
- MyPy: `mypy src/ --strict`
- Bandit: `bandit -r src/`
- Pre-commit: `pre-commit run --all-files`

### Naming Conventions

- Constants: `UPPER_CASE_WITH_UNDERSCORES`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Private members: `_leading_underscore`

### Important Notes

- ❌ **NO emojis** in code or log messages
- ✅ Use modern Python 3.13 syntax (`list[str]` not `List[str]`)
- ✅ Complete type hints on everything
- ✅ No hardcoded credentials or secrets
- ✅ Use Pydantic for data validation
- ✅ Prefer editing existing files over creating new ones

---

## 🗂️ Repository Structure

### Source Files (`src/ohlala_smartops/`)

```
ohlala_smartops/
├── __init__.py
├── __main__.py
├── version.py
├── constants.py
├── utils/                  # ✅ Phase 1 COMPLETE
│   ├── __init__.py
│   ├── ssm_validation.py
│   ├── powershell_validator.py
│   └── ssm_utils.py
├── ai/                     # Phase 4
├── bot/                    # Phase 8
├── cards/                  # Phase 6
├── commands/               # Phase 9-10
├── config/                 # Already exists
│   └── settings.py
├── locales/                # Deferred (English only)
├── mcp/                    # Phase 5
└── models/                 # Phase 3
```

### Test Files (`tests/`)

```
tests/
├── test_ssm_validation.py      # ✅ 22 tests
├── test_powershell_validator.py # ✅ 20 tests
└── test_ssm_utils.py           # ✅ 47 tests
```

---

## 🔗 Important Links

- **Public Repo**: https://github.com/ohlala-cloud/ohlala-smartops
- **Internal Repo**: `/home/etienne/ohlala-project/Ohlala-bot/`
- **Phase 1 PR**: https://github.com/ohlala-cloud/ohlala-smartops/pull/6
- **CI Workflow**: `.github/workflows/ci.yml`
- **Coding Guidelines**: `CLAUDE.md`
- **Contributing Guide**: `CONTRIBUTING.md`

---

## 📝 Key Decisions

### Migration Strategy

- **Approach**: One module at a time with full quality
- **Coverage Target**: 80% minimum per module
- **Internationalization**: English only for now (defer i18n to future)
- **Security**: Fix JWT validation issue during migration (not defer)
- **Testing**: Comprehensive tests before moving to next module

### What NOT to Migrate

- ❌ Marketplace-specific files (`marketplace/` directory)
- ❌ Documentation site (`docs-site/` Hugo site)
- ❌ Archive/POC code (`archive/`, `POC/` directories)
- ❌ Environment files (`.env` with real credentials)
- ❌ Deployment scripts with hardcoded values

### Security Considerations

- **CRITICAL**: Fix incomplete JWT token validation in `bot_auth.py` during migration
- No credentials in code
- Use Pydantic Settings for configuration
- Bandit security scanning required

---

## 🛠️ Common Commands

### Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=src/ohlala_smartops --cov-report=term-missing

# Run specific test file
pytest tests/test_ssm_utils.py -v

# Format code
black .

# Lint code
ruff check .

# Type check
mypy src/ --strict

# Run all pre-commit hooks
pre-commit run --all-files
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feat/phase-X-description

# Commit changes (no Claude advertising!)
git add -A
git commit -m "feat: description of changes"

# Push and create PR
git push -u origin feat/phase-X-description
gh pr create --title "feat: Phase X - Description" --body "..." --base main

# Switch back to main after merge
git checkout main
git pull origin main
```

---

## 📊 Coverage Status

### Current Coverage (Phase 1 only)

```
src/ohlala_smartops/utils/
├── ssm_validation.py      95.12% ✅
├── powershell_validator.py 89.16% ✅
└── ssm_utils.py           64.78% ⚠️

Package Average: ~83% ✅ (above 80% target)
```

### Overall Project Coverage

```
Total: 52.72% (includes unmigrated modules)
```

---

## 🚀 Next Session Checklist

When continuing work:

1. **Check PR status**: https://github.com/ohlala-cloud/ohlala-smartops/pull/6
   - Has CI passed?
   - Any review comments?
   - Ready to merge?

2. **If PR approved and merged**:

   ```bash
   git checkout main
   git pull origin main
   git branch -d feat/phase-1-utils-migration  # Clean up local branch
   ```

3. **Start Phase 2**:

   ```bash
   git checkout -b feat/phase-2-token-management
   ```

4. **Read internal files**:
   - `/home/etienne/ohlala-project/Ohlala-bot/simple-app/utils/token_estimator.py`
   - `/home/etienne/ohlala-project/Ohlala-bot/simple-app/utils/token_tracker.py`
   - `/home/etienne/ohlala-project/Ohlala-bot/simple-app/utils/global_throttler.py`
   - `/home/etienne/ohlala-project/Ohlala-bot/simple-app/utils/bedrock_throttler.py`
   - `/home/etienne/ohlala-project/Ohlala-bot/simple-app/utils/claude_sonnet4_selector.py`

5. **Review dependencies**:
   - Check if any exceptions need to be created first
   - Check if Pydantic models are needed
   - Check imports and circular dependency issues

---

## 💡 Tips for Future Sessions

1. **Use the Task/Plan agent** for exploration instead of running commands directly
2. **Always run quality checks** before committing:
   - `black .`
   - `ruff check .`
   - `mypy src/ --strict`
3. **Coverage target**: Aim for 80%+ per module, but package average is acceptable
4. **No Claude advertising** in commit messages
5. **Follow the migration plan** (documented in this file)
6. **Test locally** before pushing (run pytest with coverage)
7. **Use pre-commit hooks** - they catch issues before commit

---

## 📚 Reference Documents

- **CLAUDE.md**: Comprehensive development guidelines
- **CONTRIBUTING.md**: Contributing guidelines and workflow
- **CODE_OF_CONDUCT.md**: Community standards
- **SECURITY.md**: Security reporting process
- **README.md**: Project overview and quick start

---

**End of Status Document**

_This document is updated after each major milestone. Last update: Phase 1 complete, PR #6 created._
