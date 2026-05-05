"""Tests for ProfileService CRUD operations.

Tests list, get, create, update, delete, default management,
import, and export methods on ProfileService.

Required deps: pip install -e ".[auth]"
"""

import json

import pytest

sqlmodel = pytest.importorskip(  # noqa: E402
    "sqlmodel", reason="auth deps not installed - pip install -e '.[auth]'"
)

from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from fast_app.models.db_models import ProfileCreate, User  # noqa: E402
from fast_app.services.auth import hash_password  # noqa: E402
from fast_app.services.profile_service import ProfileService  # noqa: E402


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine with all tables."""
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    """Provide a database session for tests."""
    with Session(engine) as sess:
        yield sess


@pytest.fixture
def test_user(session):
    """Create and return a test user."""
    user = User(email="test@example.com", hashed_password=hash_password("password"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def second_user(session):
    """Create and return a second test user for ownership checks."""
    user = User(email="other@example.com", hashed_password=hash_password("password"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def service():
    """Provide a ProfileService instance."""
    return ProfileService()


class TestListProfiles:
    def test_list_profiles_returns_profiles_for_user(self, service, session, test_user):
        data = ProfileCreate(name="General", profile_data={"name": "Test User"}, is_default=True)
        service.create_profile(data, test_user.id, session)

        profiles = service.list_profiles(test_user.id, session)
        assert len(profiles) == 1
        assert profiles[0].name == "General"

    def test_list_profiles_empty_when_no_profiles(self, service, session, test_user):
        profiles = service.list_profiles(test_user.id, session)
        assert profiles == []

    def test_list_profiles_only_returns_own_profiles(
        self, service, session, test_user, second_user
    ):
        data = ProfileCreate(name="User1 Profile", profile_data={"name": "User1"}, is_default=False)
        service.create_profile(data, test_user.id, session)

        profiles = service.list_profiles(second_user.id, session)
        assert len(profiles) == 0

    def test_list_profiles_returns_multiple(self, service, session, test_user):
        for i in range(3):
            data = ProfileCreate(
                name=f"Profile {i}",
                profile_data={"name": f"User{i}"},
                is_default=(i == 0),
            )
            service.create_profile(data, test_user.id, session)

        profiles = service.list_profiles(test_user.id, session)
        assert len(profiles) == 3


class TestGetProfile:
    def test_get_profile_returns_profile_by_id(self, service, session, test_user):
        data = ProfileCreate(name="Test", profile_data={"name": "Test"}, is_default=False)
        created = service.create_profile(data, test_user.id, session)

        result = service.get_profile(created.id, test_user.id, session)
        assert result is not None
        assert result.id == created.id
        assert result.name == "Test"

    def test_get_profile_returns_none_if_not_found(self, service, session, test_user):
        result = service.get_profile(9999, test_user.id, session)
        assert result is None

    def test_get_profile_returns_none_if_wrong_user(self, service, session, test_user, second_user):
        data = ProfileCreate(name="Owned", profile_data={"name": "Test"}, is_default=False)
        created = service.create_profile(data, test_user.id, session)

        result = service.get_profile(created.id, second_user.id, session)
        assert result is None


class TestCreateProfile:
    def test_create_profile_basic(self, service, session, test_user):
        data = ProfileCreate(name="General", profile_data={"name": "Test User"}, is_default=False)
        profile = service.create_profile(data, test_user.id, session)

        assert profile.id is not None
        assert profile.user_id == test_user.id
        assert profile.name == "General"
        assert json.loads(profile.profile_data) == {"name": "Test User"}
        assert profile.is_default is False

    def test_create_profile_with_default_flag(self, service, session, test_user):
        data = ProfileCreate(name="Default", profile_data={"name": "Test"}, is_default=True)
        profile = service.create_profile(data, test_user.id, session)

        assert profile.is_default is True

    def test_create_default_unsets_existing_default(self, service, session, test_user):
        first = ProfileCreate(name="First", profile_data={"name": "A"}, is_default=True)
        first_profile = service.create_profile(first, test_user.id, session)
        assert first_profile.is_default is True

        second = ProfileCreate(name="Second", profile_data={"name": "B"}, is_default=True)
        second_profile = service.create_profile(second, test_user.id, session)

        session.refresh(first_profile)
        assert first_profile.is_default is False
        assert second_profile.is_default is True

    def test_create_profile_uses_default_name(self, service, session, test_user):
        data = ProfileCreate(profile_data={"name": "Test"}, is_default=False)
        profile = service.create_profile(data, test_user.id, session)
        assert profile.name == "Default Profile"

    def test_create_profile_serializes_data_as_json(self, service, session, test_user):
        profile_data = {"name": "Test", "skills": ["Python", "SQL"], "experience": 5}
        data = ProfileCreate(name="Detailed", profile_data=profile_data, is_default=False)
        profile = service.create_profile(data, test_user.id, session)

        stored = json.loads(profile.profile_data)
        assert stored == profile_data


class TestUpdateProfile:
    def test_update_profile_basic(self, service, session, test_user):
        create_data = ProfileCreate(name="Original", profile_data={"name": "Old"}, is_default=False)
        created = service.create_profile(create_data, test_user.id, session)

        update_data = ProfileCreate(name="Updated", profile_data={"name": "New"}, is_default=False)
        updated = service.update_profile(created.id, test_user.id, update_data, session)

        assert updated is not None
        assert updated.name == "Updated"
        assert json.loads(updated.profile_data) == {"name": "New"}

    def test_update_profile_returns_none_if_not_found(self, service, session, test_user):
        data = ProfileCreate(name="X", profile_data={}, is_default=False)
        result = service.update_profile(9999, test_user.id, data, session)
        assert result is None

    def test_update_profile_returns_none_if_wrong_user(
        self, service, session, test_user, second_user
    ):
        create_data = ProfileCreate(name="Owned", profile_data={"name": "A"}, is_default=False)
        created = service.create_profile(create_data, test_user.id, session)

        update_data = ProfileCreate(name="Hacked", profile_data={"name": "B"}, is_default=False)
        result = service.update_profile(created.id, second_user.id, update_data, session)
        assert result is None

    def test_update_profile_set_default_unsets_other(self, service, session, test_user):
        first = ProfileCreate(name="First", profile_data={"name": "A"}, is_default=True)
        first_profile = service.create_profile(first, test_user.id, session)

        second = ProfileCreate(name="Second", profile_data={"name": "B"}, is_default=False)
        second_profile = service.create_profile(second, test_user.id, session)

        update_data = ProfileCreate(name="Second", profile_data={"name": "B"}, is_default=True)
        service.update_profile(second_profile.id, test_user.id, update_data, session)

        session.refresh(first_profile)
        assert first_profile.is_default is False


class TestDeleteProfile:
    def test_delete_profile_returns_true_on_success(self, service, session, test_user):
        data = ProfileCreate(name="ToDelete", profile_data={"name": "X"}, is_default=False)
        created = service.create_profile(data, test_user.id, session)

        result = service.delete_profile(created.id, test_user.id, session)
        assert result is True

        # Verify it's actually gone
        assert service.get_profile(created.id, test_user.id, session) is None

    def test_delete_profile_returns_false_if_not_found(self, service, session, test_user):
        result = service.delete_profile(9999, test_user.id, session)
        assert result is False

    def test_delete_profile_returns_false_if_wrong_user(
        self, service, session, test_user, second_user
    ):
        data = ProfileCreate(name="Owned", profile_data={"name": "X"}, is_default=False)
        created = service.create_profile(data, test_user.id, session)

        result = service.delete_profile(created.id, second_user.id, session)
        assert result is False

        # Verify profile still exists
        assert service.get_profile(created.id, test_user.id, session) is not None


class TestGetDefaultProfile:
    def test_get_default_profile_returns_default(self, service, session, test_user):
        data = ProfileCreate(name="Default", profile_data={"name": "Test"}, is_default=True)
        created = service.create_profile(data, test_user.id, session)

        result = service.get_default_profile(test_user.id, session)
        assert result is not None
        assert result.id == created.id
        assert result.is_default is True

    def test_get_default_profile_returns_none_if_no_default(self, service, session, test_user):
        data = ProfileCreate(name="NonDefault", profile_data={"name": "Test"}, is_default=False)
        service.create_profile(data, test_user.id, session)

        result = service.get_default_profile(test_user.id, session)
        assert result is None

    def test_get_default_profile_returns_none_if_no_profiles(self, service, session, test_user):
        result = service.get_default_profile(test_user.id, session)
        assert result is None


class TestImportProfile:
    def test_import_profile_from_file(self, service, session, test_user, tmp_path):
        profile_data = {"name": "Imported User", "skills": ["Python", "Go"]}
        json_file = tmp_path / "profile.json"
        json_file.write_text(json.dumps(profile_data), encoding="utf-8")

        profile = service.import_profile(
            str(json_file), test_user.id, session, name="Imported", is_default=False
        )

        assert profile.name == "Imported"
        assert json.loads(profile.profile_data) == profile_data
        assert profile.is_default is False

    def test_import_profile_with_default_flag(self, service, session, test_user, tmp_path):
        profile_data = {"name": "Default User"}
        json_file = tmp_path / "profile.json"
        json_file.write_text(json.dumps(profile_data), encoding="utf-8")

        profile = service.import_profile(
            str(json_file), test_user.id, session, name="My Default", is_default=True
        )

        assert profile.is_default is True

    def test_import_profile_file_not_found(self, service, session, test_user):
        with pytest.raises(FileNotFoundError):
            service.import_profile("/nonexistent/path.json", test_user.id, session)

    def test_import_profile_invalid_json(self, service, session, test_user, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            service.import_profile(str(bad_file), test_user.id, session)

    def test_import_profile_uses_default_name(self, service, session, test_user, tmp_path):
        profile_data = {"name": "Test"}
        json_file = tmp_path / "profile.json"
        json_file.write_text(json.dumps(profile_data), encoding="utf-8")

        profile = service.import_profile(str(json_file), test_user.id, session)
        assert profile.name == "Imported"


class TestExportProfile:
    def test_export_profile_returns_dict(self, service, session, test_user):
        profile_data = {"name": "Export User", "skills": ["Rust"]}
        data = ProfileCreate(name="Exportable", profile_data=profile_data, is_default=True)
        created = service.create_profile(data, test_user.id, session)

        exported = service.export_profile(created.id, test_user.id, session)
        assert exported is not None
        assert exported["name"] == "Exportable"
        assert exported["profile_data"] == profile_data
        assert exported["is_default"] is True
        assert "id" in exported
        assert "user_id" in exported
        assert "created_at" in exported
        assert "updated_at" in exported

    def test_export_profile_returns_none_if_not_found(self, service, session, test_user):
        result = service.export_profile(9999, test_user.id, session)
        assert result is None

    def test_export_profile_returns_none_if_wrong_user(
        self, service, session, test_user, second_user
    ):
        data = ProfileCreate(name="Owned", profile_data={"name": "X"}, is_default=False)
        created = service.create_profile(data, test_user.id, session)

        result = service.export_profile(created.id, second_user.id, session)
        assert result is None
