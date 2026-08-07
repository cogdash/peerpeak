"""Tests for avatar API endpoints."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set test environment variables BEFORE importing app
os.environ["S3_ENDPOINT_URL"] = "http://localhost:9000"
os.environ["S3_ACCESS_KEY_ID"] = "minioadmin"
os.environ["S3_SECRET_ACCESS_KEY"] = "minioadmin"
os.environ["S3_BUCKET_NAME"] = "peerpeak-user-content"
os.environ["S3_REGION"] = "us-east-1"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

# Now import app and core modules
from src.main import app
from core.database import Base
from core.auth import create_session, hash_password, get_db
from models import User, Avatar, AvatarStatus, Session as SessionModel


# Create a test engine and session factory
test_engine = create_engine(
    "sqlite:///./test.db", connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id="testuser123",
        name="testuser",
        password=hash_password("password123"),
        display_name="Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def authenticated_client(test_user: User, db_session: Session) -> TestClient:
    """Create a test client with authenticated session."""
    client = TestClient(app)

    # Create a mock request with proper attributes
    mock_request = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.headers.get.return_value = "test-agent"

    session = create_session(db_session, test_user.id, mock_request)
    client.cookies.set("session_id", session.id)
    return client


@pytest.fixture
def mock_storage():
    """Mock S3Storage for testing."""
    with patch("routers.avatar.get_storage") as mock:
        storage = MagicMock()
        storage.generate_presigned_post.return_value = MagicMock(
            url="http://localhost:9000/peerpeak-user-content",
            fields={
                "key": "test-key",
                "policy": "test-policy",
                "signature": "test-sig",
            },
            key="avatars/testuser123/original/test.jpg",
        )
        storage.get_avatar_urls.return_value = {
            "avatar_400": "http://localhost:9000/peerpeak-user-content/avatars/testuser123/avatar_400.webp",
            "avatar_100": "http://localhost:9000/peerpeak-user-content/avatars/testuser123/avatar_100.webp",
        }
        storage.object_exists.return_value = False
        mock.return_value = storage
        yield storage


class TestPresignEndpoint:
    """Tests for POST /api/avatar/presign"""

    def test_presign_success(self, authenticated_client: TestClient, mock_storage):
        """Test successful presigned POST generation."""
        response = authenticated_client.post(
            "/api/avatar/presign", json={"content_type": "image/jpeg"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "fields" in data
        assert "key" in data
        assert data["key"].startswith("avatars/testuser123/original/")
        assert data["key"].endswith(".jpg")

    def test_presign_invalid_content_type(self, authenticated_client: TestClient):
        """Test presign with non-image content type."""
        response = authenticated_client.post(
            "/api/avatar/presign", json={"content_type": "application/pdf"}
        )
        assert response.status_code == 400
        assert "Content type must be an image" in response.json()["detail"]

    def test_presign_unauthenticated(self):
        """Test presign without authentication."""
        client = TestClient(app)
        response = client.post(
            "/api/avatar/presign", json={"content_type": "image/jpeg"}
        )
        assert response.status_code == 401  # Unauthorized


class TestCompleteEndpoint:
    """Tests for POST /api/avatar/complete"""

    def test_complete_success(
        self,
        authenticated_client: TestClient,
        test_user: User,
        db_session: Session,
        mock_storage,
    ):
        """Test successful avatar upload completion."""
        response = authenticated_client.post(
            "/api/avatar/complete",
            json={"key": "avatars/testuser123/original/test.jpg"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

        # Verify avatar record created
        avatar = db_session.query(Avatar).filter(Avatar.user_id == test_user.id).first()
        assert avatar is not None
        assert avatar.status == AvatarStatus.PROCESSING
        assert avatar.original_key == "avatars/testuser123/original/test.jpg"

    def test_complete_invalid_key(self, authenticated_client: TestClient):
        """Test complete with key not belonging to user."""
        response = authenticated_client.post(
            "/api/avatar/complete",
            json={"key": "avatars/otheruser/original/test.jpg"},
        )
        assert response.status_code == 400
        assert "Invalid key for this user" in response.json()["detail"]


class TestGetAvatarEndpoint:
    """Tests for GET /api/avatar/me"""

    def test_get_no_avatar(self, authenticated_client: TestClient, mock_storage):
        """Test get avatar when user has none."""
        mock_storage.object_exists.return_value = False
        response = authenticated_client.get("/api/avatar/me")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "none"
        assert data["avatar_400"] is None
        assert data["avatar_100"] is None

    def test_get_processing_avatar(
        self,
        authenticated_client: TestClient,
        test_user: User,
        db_session: Session,
        mock_storage,
    ):
        """Test get avatar when processing."""
        avatar = Avatar(
            user_id=test_user.id,
            original_key="avatars/testuser123/original/test.jpg",
            content_type="image/jpeg",
            file_size=100,
            status=AvatarStatus.PROCESSING,
        )
        db_session.add(avatar)
        db_session.commit()

        mock_storage.object_exists.return_value = False
        response = authenticated_client.get("/api/avatar/me")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

    def test_get_ready_avatar(
        self,
        authenticated_client: TestClient,
        test_user: User,
        db_session: Session,
        mock_storage,
    ):
        """Test get avatar when ready."""
        avatar = Avatar(
            user_id=test_user.id,
            original_key="avatars/testuser123/original/test.jpg",
            content_type="image/jpeg",
            file_size=100,
            status=AvatarStatus.READY,
            avatar_400_key="avatars/testuser123/avatar_400.webp",
            avatar_100_key="avatars/testuser123/avatar_100.webp",
        )
        db_session.add(avatar)
        db_session.commit()

        mock_storage.object_exists.return_value = True
        response = authenticated_client.get("/api/avatar/me")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["avatar_400"] is not None
        assert data["avatar_100"] is not None


class TestDeleteAvatarEndpoint:
    """Tests for DELETE /api/avatar/me"""

    def test_delete_success(
        self,
        authenticated_client: TestClient,
        test_user: User,
        db_session: Session,
        mock_storage,
    ):
        """Test successful avatar deletion."""
        avatar = Avatar(
            user_id=test_user.id,
            original_key="avatars/testuser123/original/test.jpg",
            content_type="image/jpeg",
            file_size=100,
            status=AvatarStatus.READY,
            avatar_400_key="avatars/testuser123/avatar_400.webp",
            avatar_100_key="avatars/testuser123/avatar_100.webp",
        )
        db_session.add(avatar)
        db_session.commit()

        response = authenticated_client.delete("/api/avatar/me")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Avatar deleted successfully"

        # Verify avatar record deleted
        avatar = db_session.query(Avatar).filter(Avatar.user_id == test_user.id).first()
        assert avatar is None

        # Verify delete_objects called
        mock_storage.delete_objects.assert_called()
        deleted_keys = mock_storage.delete_objects.call_args[0][0]
        assert "avatars/testuser123/original/test.jpg" in deleted_keys
        assert "avatars/testuser123/avatar_400.webp" in deleted_keys
        assert "avatars/testuser123/avatar_100.webp" in deleted_keys

    def test_delete_not_found(self, authenticated_client: TestClient):
        """Test delete when no avatar exists."""
        response = authenticated_client.delete("/api/avatar/me")
        assert response.status_code == 404
        assert "No avatar found" in response.json()["detail"]
