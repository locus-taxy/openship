"""Tests for services/bandit.py."""

from unittest.mock import MagicMock, patch
import pytest
from services.bandit import (
    _beta_sample,
    _initialise_arms,
    sample_style,
    update_arm,
    get_current_style,
)
from models.content_style_arms import ContentStyleArm, CONTENT_STYLES

class TestBetaSample:
    def test_returns_float_between_0_and_1(self):
        for _ in range(20):
            result = _beta_sample(1.0, 1.0)
            assert 0.0 <= result <= 1.0

    def test_high_alpha_biases_toward_1(self):
        samples = [_beta_sample(100.0, 1.0) for _ in range(50)]
        assert sum(samples) / len(samples) > 0.8

    def test_high_beta_biases_toward_0(self):
        samples = [_beta_sample(1.0, 100.0) for _ in range(50)]
        assert sum(samples) / len(samples) < 0.2

class TestInitialiseArms:
    def _make_session(self, existing_styles=None):
        session = MagicMock()
        existing_styles = existing_styles or set()

        def exec_first():
            mock = MagicMock()
            # track call count to map to styles
            mock.first.return_value = None
            return mock

        call_count = [0]
        existing_arms = {
            style: ContentStyleArm(skill_id=1, user_id=1, style=style) for style in existing_styles
        }

        def side_effect(stmt):
            em = MagicMock()
            # Return existing arm for existing styles, None otherwise
            style = CONTENT_STYLES[call_count[0] % len(CONTENT_STYLES)]
            call_count[0] += 1
            em.first.return_value = existing_arms.get(style)
            return em

        session.exec.side_effect = side_effect
        return session

    def test_creates_4_arms_when_none_exist(self):
        session = self._make_session(existing_styles=set())
        arms = _initialise_arms(session, 1, 1)
        assert len(arms) == 4
        assert {a.style for a in arms} == set(CONTENT_STYLES)

    def test_skips_existing_arms(self):
        existing_styles = set(CONTENT_STYLES)
        session = self._make_session(existing_styles=existing_styles)
        arms = _initialise_arms(session, 1, 1)
        assert len(arms) == 4
        # No new arms were added
        session.add.assert_not_called()

class TestSampleStyle:
    def _patch_session(self, session_mock):
        patcher = patch("services.bandit.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def test_returns_valid_style_string(self):
        arms = [
            ContentStyleArm(skill_id=1, user_id=1, style=s, alpha=1.0, beta=1.0)
            for s in CONTENT_STYLES
        ]
        session = MagicMock()
        call_count = [0]

        def exec_side_effect(stmt):
            em = MagicMock()
            style = CONTENT_STYLES[call_count[0] % len(CONTENT_STYLES)]
            call_count[0] += 1
            em.first.return_value = arms[CONTENT_STYLES.index(style)]
            return em

        session.exec.side_effect = exec_side_effect
        patcher = self._patch_session(session)
        try:
            with patch("services.bandit._initialise_arms", return_value=arms):
                result = sample_style(1, 1)
            assert result in CONTENT_STYLES
        finally:
            patcher.stop()

class TestUpdateArm:
    def _patch_session(self, session_mock):
        patcher = patch("services.bandit.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def test_increments_alpha_when_improved(self):
        arm = ContentStyleArm(skill_id=1, user_id=1, style="balanced", alpha=1.0, beta=1.0)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = arm
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            update_arm(1, 1, "balanced", improved=True)
            assert arm.alpha == 2.0
            assert arm.beta == 1.0
        finally:
            patcher.stop()

    def test_increments_beta_when_not_improved(self):
        arm = ContentStyleArm(skill_id=1, user_id=1, style="balanced", alpha=1.0, beta=1.0)
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = arm
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            update_arm(1, 1, "balanced", improved=False)
            assert arm.alpha == 1.0
            assert arm.beta == 2.0
        finally:
            patcher.stop()

    def test_does_nothing_when_arm_not_found(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.first.return_value = None
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            update_arm(1, 1, "nonexistent", improved=True)  # should not raise
            session.commit.assert_not_called()
        finally:
            patcher.stop()

class TestGetCurrentStyle:
    def _patch_session(self, session_mock):
        patcher = patch("services.bandit.Session")
        mock_cls = patcher.start()
        mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return patcher

    def test_returns_balanced_when_no_arms_exist(self):
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = []
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_current_style(1, 1)
            assert result == "balanced"
        finally:
            patcher.stop()

    def test_returns_style_with_highest_alpha_ratio(self):
        arms = [
            ContentStyleArm(skill_id=1, user_id=1, style="balanced", alpha=2.0, beta=1.0),
            ContentStyleArm(skill_id=1, user_id=1, style="example_heavy", alpha=5.0, beta=1.0),
            ContentStyleArm(skill_id=1, user_id=1, style="theory_first", alpha=1.0, beta=3.0),
            ContentStyleArm(skill_id=1, user_id=1, style="reinforcement", alpha=1.0, beta=1.0),
        ]
        session = MagicMock()
        exec_mock = MagicMock()
        exec_mock.all.return_value = arms
        session.exec.return_value = exec_mock
        patcher = self._patch_session(session)
        try:
            result = get_current_style(1, 1)
            assert result == "example_heavy"  # 5/(5+1) = 0.833 is highest
        finally:
            patcher.stop()
