from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

def _patch_session(session_mock):
    patcher = patch(
        "services.pricing_snapshot.Session",
        return_value=__import__("contextlib").nullcontext(session_mock),
    )
    patcher.start()
    return patcher

class TestCreatePricingSnapshot:
    def test_returns_id_on_success(self):
        from services.pricing_snapshot import create_pricing_snapshot

        session = MagicMock()
        session.refresh.side_effect = lambda obj: setattr(obj, "id", 42)

        with patch("services.pricing_snapshot.Session") as mock_session_cls:
            mock_session_cls.return_value.__enter__ = lambda s, *a: session
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = create_pricing_snapshot("openai", "gpt-4o-mini", 0.15, 0.60, "auto")

        assert result == 42
        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_returns_none_on_db_error(self):
        from services.pricing_snapshot import create_pricing_snapshot

        with patch("services.pricing_snapshot.Session") as mock_session_cls:
            mock_session_cls.return_value.__enter__ = MagicMock(
                side_effect=SQLAlchemyError("db error")
            )
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = create_pricing_snapshot("openai", "gpt-4o-mini", 0.15, 0.60, "auto")

        assert result is None
