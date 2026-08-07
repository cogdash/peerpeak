## Problem Statement

Users currently cannot upload profile avatars. The profile page shows only initials in a colored circle. Users want to personalize their profiles with custom images.

## Solution

Add user profile avatar support using S3/MinIO for storage with AWS Lambda for image processing. Users can upload any image format, which gets converted to WebP thumbnails (400px and 100px) via Lambda. Avatars are publicly accessible via direct S3 URLs, bypassing the backend for reads.

## User Stories

- [ ] As a registered user, I want to upload a profile avatar from the settings modal, so that my profile looks personalized
- [ ] As a user, I want to see my current avatar in the profile header and settings modal, so that I can confirm it looks correct
- [ ] As a user, I want to upload images in any common format (JPEG, PNG, WebP, GIF), so that I don't need to convert files manually
- [ ] As a user, I want my avatar to appear instantly after upload (showing the old one during processing), so that there's no broken image state
- [ ] As a user, I want the system to automatically generate optimized WebP thumbnails, so that page loads are fast
- [ ] As a user, I want to replace my avatar by uploading a new one, so that I can update my profile picture anytime
- [ ] As a user, I want to remove my avatar (revert to initials), so that I can have no image if I prefer
- [ ] As a developer, I want to use MinIO locally for development, so that I don't need AWS credentials for local work
- [ ] As a developer, I want to use AWS SAM CLI to test Lambda locally, so that I can verify image processing works before deploying

## Implementation Decisions

### Data Model
- New `Avatar` model (separate table, one-to-one with User) with fields:
  - `id` (PK, 24-char generated ID)
  - `user_id` (FK to User, unique)
  - `original_key` (S3 key of uploaded original)
  - `avatar_400_key` (S3 key of 400px WebP variant)
  - `avatar_100_key` (S3 key of 100px WebP variant)
  - `content_type` (original MIME type)
  - `file_size` (original file size in bytes)
  - `status` (enum: "processing", "ready", "failed")
  - `created_at`, `updated_at` (timestamps)
- User model gets a relationship to Avatar (optional, one-to-one)

### Storage (core/storage.py)
- New `S3Storage` class using `boto3`
- Configuration via environment variables:
  - `S3_ENDPOINT_URL` (MinIO: `http://localhost:9000`, AWS: empty)
  - `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`
  - `S3_BUCKET_NAME` (e.g., `peerpeak-avatars`)
  - `S3_REGION` (default: `us-east-1`)
  - `S3_PUBLIC_URL_BASE` (optional CDN domain)
- Single bucket with prefixes: `avatars/{user_id}/original/`, `avatars/{user_id}/avatar_400.webp`, `avatars/{user_id}/avatar_100.webp`
- Public read access on `avatars/*` prefix

### API Endpoints (new router or profile router)
1. `POST /api/avatar/presign` - Returns presigned POST data for direct browser-to-S3 upload
   - Input: `{ "content_type": "image/*" }` (accept any image type)
   - Validates content type is an image
   - Generates unique key: `avatars/{user_id}/original/{uuid}.{ext}`
   - Conditions: max 5MB, key prefix, any image content-type

2. `POST /api/avatar/complete` - Called after successful S3 upload
   - Input: `{ "key": "avatars/{user_id}/original/{uuid}.jpg" }`
   - Creates Avatar record with status="processing"
   - Returns `{ "status": "processing" }`

3. `GET /api/avatar/me` - Get current avatar variant URLs
   - Checks S3 for `avatar_400.webp` and `avatar_100.webp` existence (HEAD)
   - Returns `{ "status": "ready|processing|none", "avatar_400": "url", "avatar_100": "url" }`

4. `DELETE /api/avatar/me` - Remove avatar
   - Deletes S3 objects (original + variants)
   - Deletes Avatar record
   - Returns success

### Lambda Function (AWS SAM)
- Trigger: S3 `ObjectCreated` on `avatars/*/original/*`
- Runtime: Python 3.11 with Pillow layer
- Processing:
  1. Download original from S3
  2. Validate/convert to RGB
  3. Generate 400x400 WebP (quality 85) → `avatars/{user_id}/avatar_400.webp`
  4. Generate 100x100 WebP (quality 80) → `avatars/{user_id}/avatar_100.webp`
  5. Upload variants (atomic overwrite)
  6. Delete original
- SAM template with S3 bucket notification config

### Frontend (profile.html Alpine.js)
- Add avatar preview in Profile settings tab (click to select file)
- File input accepts `image/*`
- On select: show preview, request presigned POST, upload to S3
- On upload success: call `/api/avatar/complete`, start polling `/api/avatar/me` every 2s
- When status="ready": update avatar preview in settings modal and profile header
- No "processing" UI state (old avatar shows during Lambda execution due to S3 atomic overwrite)
- Max file size: 5MB enforced by presigned POST policy

### Docker Compose
- Add MinIO service for local development
- MinIO console on port 9001, API on 9000
- Bucket auto-created on startup

### Database Migration
- New Alembic migration for `avatar` table
- Foreign key to `user.id` with CASCADE delete
- Unique constraint on `user_id`

## Testing Decisions

### What Makes a Good Test
- Test external behavior (API contracts, user flows) not implementation details
- Use existing test patterns if any exist (currently no tests in codebase)
- Integration tests over unit tests for this feature

### Modules to Test
1. **S3Storage class** - presigned POST generation, URL construction, object existence checks
2. **Avatar API endpoints** - presign, complete, get, delete flows
3. **Avatar model** - CRUD operations, relationship with User
4. **Frontend integration** - Alpine.js component behavior (manual/E2E)
5. **Lambda function** - image processing logic (unit test with Pillow)

### Prior Art
- No existing tests in codebase - this will establish patterns
- Follow FastAPI testing patterns with `TestClient`
- Use pytest fixtures for database sessions
- Mock S3 with `moto` library for unit tests

## Out of Scope

- Avatar cropping/editing UI (user uploads full image, Lambda centers-crops to square)
- Multiple avatar support (only one current avatar per user)
- Private avatars (all avatars are public)
- CDN configuration (uses direct S3 URLs)
- Avatar moderation/reporting
- Animated avatar support (GIF → WebP loses animation)
- Batch upload or bulk operations

## Further Notes

- The atomic S3 overwrite ensures zero-downtime avatar updates - old avatar serves until new one is fully written
- Polling interval of 2s with 60s timeout balances responsiveness with Lambda cold starts
- MinIO local dev requires `mc` CLI or SDK to create bucket and set public policy
- SAM template should be in `infrastructure/` or project root
- Consider adding `boto3` and `moto` to pyproject.toml dependencies
- The `S3_PUBLIC_URL_BASE` allows future CloudFront/CDN integration without code changes

