# Handoff Document: PeerPeak Avatar API Implementation

## Context
Working on implementing backend API endpoints for user profile avatars (GitHub issue #15). The broader feature is tracked in issue #13: "Feat: User profile avatars with S3 and Lambda".

## Current State

### What's Been Done
- ✅ Created `S3Storage` class in `src/core/storage.py` with presigned POST generation, URL construction, object existence checks, and deletion
- ✅ Created `Avatar` model in `src/models/avatar.py` with status enum (PROCESSING, READY, FAILED)
- ✅ Created avatar router in `src/routers/avatar.py` with 4 endpoints:
  - `POST /api/avatar/presign` - Generate presigned POST for direct browser-to-S3 upload
  - `POST /api/avatar/complete` - Called after successful S3 upload, creates Avatar record
  - `GET /api/avatar/me` - Get current avatar variant URLs (checks S3 for variants)
  - `DELETE /api/avatar/me` - Remove avatar and all S3 objects
- ✅ Added `get_storage()` dependency in `src/core/dependencies.py`
- ✅ Added `require_auth_api()` in `src/core/auth.py` for API authentication (returns 401)
- ✅ Registered avatar router in `src/main.py` and `src/routers/__init__.py`
- ✅ Fixed datetime comparison bug in `get_current_user()` (timezone-aware vs naive)
- ✅ Tests in `tests/test_avatar.py` - 8/10 passing

### Test Failures (2 remaining)
1. **`test_get_ready_avatar`** - Mock `storage.object_exists` returns `False` instead of `True`
   - The test sets `mock_storage.object_exists.return_value = True` but the actual calls return `False`
   - Debug output shows `avatar_400_exists=False` and `avatar_100_exists=False`

2. **`test_delete_success`** - Mock `storage.delete_objects` not being called
   - `mock_storage.delete_objects.assert_called()` fails

### Root Cause Hypothesis
The mock patching in `tests/test_avatar.py` uses `patch("core.dependencies.get_storage")` but the avatar router imports `get_storage` from `core.dependencies` and uses it as a FastAPI dependency. The mock may not be properly applied to the dependency injection system.

## Next Steps
1. Fix the mock setup in `tests/test_avatar.py` - likely need to patch at the right location or use a different mocking strategy
2. Run full test suite to ensure no regressions
3. Run type checking (mypy/pyright if configured)
4. Code review

## Relevant Files
- `src/routers/avatar.py` - Main implementation
- `src/core/storage.py` - S3Storage class
- `src/models/avatar.py` - Avatar model
- `tests/test_avatar.py` - Tests (needs mock fixes)
- `src/core/dependencies.py` - get_storage dependency
- `src/core/auth.py` - require_auth_api
- GitHub issues: #13 (parent), #15 (current)

## Suggested Skills
- `skill_tdd` - For fixing the failing tests using test-driven approach
- `skill_diagnosing_bugs` - For debugging the mock/patching issues
- `skill_code_review` - For reviewing the implementation once tests pass

