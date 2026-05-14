from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest
from services.streak import record_activity, get_user_streak
from models.streak import UserStreak

def _patch_session(session_mock):
    patcher = patch("services.streak.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

def _make_streak(user_id="u1", current=0, longest=0, last_date=None):
    s = UserStreak(user_id=user_id)
    s.current_streak = current
    s.longest_streak = longest
    s.last_activity_date = last_date
    return s

class TestRecordActivity:
    def test_first_activity_sets_streak_to_1(self):
        streak = _make_streak(current=0, longest=0, last_date=None)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            today = date.today()
            result = record_activity("u1", today)
            assert result.current_streak == 1
        finally:
            patcher.stop()

    def test_consecutive_day_increments_streak(self):
        yesterday = date.today() - timedelta(days=1)
        streak = _make_streak(current=3, longest=5, last_date=yesterday)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = record_activity("u1", date.today())
            assert result.current_streak == 4
        finally:
            patcher.stop()

    def test_gap_resets_streak_to_1(self):
        two_days_ago = date.today() - timedelta(days=2)
        streak = _make_streak(current=5, longest=10, last_date=two_days_ago)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = record_activity("u1", date.today())
            assert result.current_streak == 1
        finally:
            patcher.stop()

    def test_same_day_is_idempotent(self):
        today = date.today()
        streak = _make_streak(current=3, longest=5, last_date=today)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = record_activity("u1", today)
            assert result.current_streak == 3  # unchanged
            session.add.assert_not_called()
        finally:
            patcher.stop()

    def test_future_date_rejected(self):
        streak = _make_streak(current=1, longest=1, last_date=date.today())
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            far_future = date.today() + timedelta(days=10)
            result = record_activity("u1", far_future)
            assert result.current_streak == 1  # unchanged
            session.add.assert_not_called()
        finally:
            patcher.stop()

    def test_backdated_event_rejected(self):
        yesterday = date.today() - timedelta(days=1)
        streak = _make_streak(current=3, longest=5, last_date=date.today())
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = record_activity("u1", yesterday)
            assert result.current_streak == 3  # unchanged
            session.add.assert_not_called()
        finally:
            patcher.stop()

    def test_longest_streak_updated_when_new_record(self):
        yesterday = date.today() - timedelta(days=1)
        streak = _make_streak(current=5, longest=5, last_date=yesterday)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = record_activity("u1", date.today())
            assert result.current_streak == 6
            assert result.longest_streak == 6
        finally:
            patcher.stop()

class TestGetUserStreak:
    def test_returns_zeros_when_no_streak(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_streak("u1")
            assert result == {"current_streak": 0, "longest_streak": 0, "last_activity_date": None}
        finally:
            patcher.stop()

    def test_returns_streak_data_when_found(self):
        streak = _make_streak(current=5, longest=10, last_date=date.today())
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = streak
        session.exec.return_value = exec_mock
        patcher = _patch_session(session)
        try:
            result = get_user_streak("u1")
            assert result["current_streak"] == 5
            assert result["longest_streak"] == 10
        finally:
            patcher.stop()
