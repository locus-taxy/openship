from unittest.mock import MagicMock, patch
from sqlalchemy.exc import IntegrityError
from services.streak import _get_or_create_streak

class TestGetOrCreateStreak:
    def test_returns_existing_streak(self):
        session = MagicMock()
        existing = MagicMock()
        session.exec.return_value.first.return_value = existing
        result = _get_or_create_streak(session, "user-1")
        assert result is existing

    def test_creates_new_streak_when_none_exists(self):
        session = MagicMock()
        new_streak = MagicMock()
        # First call (lock query) returns None; second call (after flush) returns new_streak
        session.exec.return_value.first.side_effect = [None, new_streak]
        result = _get_or_create_streak(session, "user-1")
        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert result is new_streak

    def test_handles_integrity_error_on_concurrent_insert(self):
        session = MagicMock()
        new_streak = MagicMock()
        # First call returns None (not found), flush raises IntegrityError (race),
        # after rollback the second exec returns the streak
        session.exec.return_value.first.side_effect = [None, new_streak]
        session.flush.side_effect = IntegrityError("", {}, Exception())
        result = _get_or_create_streak(session, "user-1")
        session.rollback.assert_called_once()
        assert result is new_streak
