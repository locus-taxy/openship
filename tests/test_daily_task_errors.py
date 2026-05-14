from unittest.mock import MagicMock, patch
import pytest
from services.daily_task import add_content_to_db, add_blocks_to_db, mark_task_completed
from services.llm import ContentBlock, BlockType

def _patch_session(session_mock):
    patcher = patch("services.daily_task.Session")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher

class TestAddContentToDbErrors:
    def test_returns_false_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = add_content_to_db(newsletter="<p>html</p>", task_id=999)
            assert result is False
        finally:
            patcher.stop()

    def test_returns_false_on_db_exception(self):
        session = MagicMock()
        session.get.side_effect = Exception("DB error")
        patcher = _patch_session(session)
        try:
            result = add_content_to_db(newsletter="<p>html</p>", task_id=1)
            assert result is False
        finally:
            patcher.stop()

class TestMarkTaskCompletedErrors:
    def test_returns_false_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        patcher = _patch_session(session)
        try:
            result = mark_task_completed(999)
            assert result is False
        finally:
            patcher.stop()

    def test_returns_false_on_db_exception(self):
        session = MagicMock()
        session.get.side_effect = Exception("connection lost")
        patcher = _patch_session(session)
        try:
            result = mark_task_completed(1)
            assert result is False
        finally:
            patcher.stop()

class TestAddBlocksToDbErrors:
    def test_returns_false_on_db_exception(self):
        session = MagicMock()
        session.get.side_effect = Exception("write failed")
        block = ContentBlock(type=BlockType.PARAGRAPH, content="Hello")
        patcher = _patch_session(session)
        try:
            result = add_blocks_to_db(blocks=[block], task_id=1)
            assert result is False
        finally:
            patcher.stop()

    def test_returns_false_when_task_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        block = ContentBlock(type=BlockType.PARAGRAPH, content="Hello")
        patcher = _patch_session(session)
        try:
            result = add_blocks_to_db(blocks=[block], task_id=999)
            assert result is False
        finally:
            patcher.stop()
