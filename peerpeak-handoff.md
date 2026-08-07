# Handoff Document: PeerPeak Avatar Lambda Image Processing (Issue #16)

## Context
Working on implementing AWS Lambda image processing for user profile avatars as part of the broader feature #13 "User profile avatars with S3 and Lambda".

## Current State

### Completed
1. **Lambda function** (`lambda/src/handler.py`) - Core image processing logic:
   - Triggered by S3 `ObjectCreated` events on `avatars/*/original/*`
   - Downloads original from S3
   - Validates/converts to RGB (handles RGBA, LA, P modes with white background compositing)
   - Generates 400x400 WebP (quality 85) → `avatars/{user_id}/avatar_400.webp`
   - Generates 100x100 WebP (quality 80) → `avatars/{user_id}/avatar_100.webp`
   - Uploads variants with atomic overwrite
   - Deletes original after successful variant upload

2. **SAM Template** (`lambda/template.yaml`) - Infrastructure as Code:
   - S3 bucket with encryption, versioning, public access config
   - Lambda function with Python 3.11 runtime
   - Pillow layer for image processing
   - S3 event trigger with prefix/suffix filters
   - IAM policies for S3 read/write

3. **Pillow Layer** (`lambda/layers/pillow/`) - Dependencies:
   - Requirements: `Pillow==10.4.0`
   - Installed in `python/` directory for Lambda layer

4. **Unit Tests** (`tests/test_lambda_handler.py`) - 17 tests covering:
   - `validate_and_convert_image`: JPEG, PNG, WebP, RGBA, palette mode, invalid data, unsupported format
   - `generate_thumbnail`: square resize, landscape/portrait center crop, quality settings
   - `process_record`: valid key, non-avatar key, invalid format, invalid image deletion
   - `lambda_handler`: multiple records, error handling

### Known Issue (Blocker)
**Test Failure**: `test_rgba_conversion` fails with `UnboundLocalError: cannot access local variable 'background'`

The issue is in `validate_and_convert_image()` function around line 166. The logic for handling RGBA/LA/P modes has a scoping bug where `background` variable is only defined inside the `if image.mode == "P":` block but referenced outside it.

**Current code structure (buggy):**
```python
if image.mode in ("RGBA", "LA", "P"):
    if image.mode == "P":
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode in ("RGBA", "LA"):
            background.paste(image, mask=image.split()[-1])
        else:
            background.paste(image)
    image = background  # UnboundLocalError for RGBA/LA modes!
```

**Fix needed:** Move `background = Image.new(...)` outside the `if image.mode == "P":` block so it's available for all transparency modes.

### Files to Reference
- Issue #16: https://github.com/cogdash/peerpeak/issues/16
- Parent Issue #13: https://github.com/cogdash/peerpeak/issues/13
- Lambda handler: `/home/panovo/projects/peerpeak/lambda/src/handler.py`
- SAM template: `/home/panovo/projects/peerpeak/lambda/template.yaml`
- Tests: `/home/panovo/projects/peerpeak/tests/test_lambda_handler.py`

## Next Steps
1. Fix the `UnboundLocalError` in `validate_and_convert_image()` 
2. Run tests to verify all 17 pass
3. Run type checking (if configured)
4. Consider adding integration test with moto for S3 operations
5. Update pyproject.toml if needed for Lambda dependencies

## Suggested Skills
- `/mcp:mattpocock:tdd` - For test-driven development approach to fix the bug
- `/mcp:mattpocock:skill_diagnosing_bugs` - For systematic debugging of the UnboundLocalError
- `/mcp:mattpocock:skill_code_review` - To review the Lambda implementation against the spec in issue #16

## Environment
- Python 3.13.5
- pytest 9.1.1
- Pillow 12.3.0 (installed in venv, 10.4.0 in Lambda layer)
- boto3 available
- Project root: `/home/panovo/projects/peerpeak`
