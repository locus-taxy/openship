"""Tests for onboarding routes, controllers, services, prompts, and LLM functions."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from models.onboarding_day import OnboardingDay
from models.onboarding_plan import OnboardingPlan
from models.onboarding_quiz_attempt import OnboardingQuizAttempt
from prompts import onboarding as onboarding_prompts
from services.llm import (
    OnboardingQuestion,
    StructuredOnboardingDayContent,
    generate_onboarding_day_content,
    generate_onboarding_plan,
    generate_onboarding_quiz,
)

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_plan(plan_id=1, user_id="1", role="Backend Engineer", quiz_questions=None):
    return OnboardingPlan(
        id=plan_id,
        user_id=user_id,
        role=role,
        company="Locus",
        status="generated",
        share_enabled=False,
        quiz_questions=quiz_questions,
    )

def _make_day(day_num=1, plan_id=1, content_blocks=None, completed=False):
    return OnboardingDay(
        id=day_num,
        plan_id=plan_id,
        day=day_num,
        topic=f"Topic {day_num}",
        task=f"Task {day_num}",
        content_blocks=content_blocks,
        completed=completed,
    )

def _make_attempt(plan_id=1, user_id="1", score=80, correct=8, total=10):
    return OnboardingQuizAttempt(
        id=1,
        plan_id=plan_id,
        user_id=user_id,
        score=score,
        correct=correct,
        total=total,
        answers=json.dumps({"0": "a"}),
    )

def _patch_session(target="services.onboarding.Session"):
    patcher = patch(target)
    mock_cls = patcher.start()
    session_mock = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=session_mock)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return patcher, session_mock

# ── prompts ──────────────────────────────────────────────────────────────────

class TestOnboardingPrompts:
    def test_plan_system_prompt_contains_role(self):
        result = onboarding_prompts.plan_system_prompt("Backend Engineer")
        assert "Backend Engineer" in result

    def test_plan_user_prompt_contains_company_and_docs(self):
        result = onboarding_prompts.plan_user_prompt("SWE", "Locus", "some docs")
        assert "Locus" in result
        assert "some docs" in result

    def test_day_content_system_prompt_contains_role_and_company(self):
        result = onboarding_prompts.day_content_system_prompt("SDET", "Locus")
        assert "SDET" in result
        assert "Locus" in result

    def test_day_content_user_prompt_contains_day_and_topic(self):
        result = onboarding_prompts.day_content_user_prompt(
            3, "Architecture", "Read docs", "Locus", "docs"
        )
        assert "Day 3" in result
        assert "Architecture" in result

    def test_quiz_system_prompt_contains_role_and_company(self):
        result = onboarding_prompts.quiz_system_prompt("PM", "Locus")
        assert "PM" in result
        assert "Locus" in result

    def test_quiz_user_prompt_contains_topics(self):
        result = onboarding_prompts.quiz_user_prompt("Locus", ["Topic A", "Topic B"], 10, "docs")
        assert "Topic A" in result
        assert "Topic B" in result

# ── LLM service ──────────────────────────────────────────────────────────────

class TestStructuredOnboardingDayContent:
    def test_model_validate_json_bytes_input(self):
        raw = b'{"blocks": [{"type": "paragraph", "content": "hello"}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        assert len(result.blocks) == 1

    def test_model_validate_json_str_input(self):
        raw = '{"blocks": [{"type": "paragraph", "content": "hello"}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        assert result.blocks[0].content == "hello"

    def test_filter_removes_empty_paragraphs(self):
        raw = '{"blocks": [{"type": "paragraph", "content": ""}, {"type": "paragraph", "content": "real"}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        assert len(result.blocks) == 1
        assert result.blocks[0].content == "real"

    def test_raises_if_all_blocks_empty(self):
        raw = '{"blocks": [{"type": "paragraph", "content": ""}]}'
        with pytest.raises(Exception):
            StructuredOnboardingDayContent.model_validate_json(raw)

    def test_keeps_divider_always(self):
        raw = '{"blocks": [{"type": "divider"}, {"type": "paragraph", "content": "x"}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        types = [b.type for b in result.blocks]
        assert "divider" in [t.value if hasattr(t, "value") else t for t in types]

    def test_filters_empty_bullet_list(self):
        raw = '{"blocks": [{"type": "bullet_list", "items": []}, {"type": "paragraph", "content": "x"}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        assert len(result.blocks) == 1

    def test_keeps_bullet_list_with_items(self):
        raw = '{"blocks": [{"type": "bullet_list", "items": ["a", "b"]}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        assert len(result.blocks) == 1

    def test_filters_empty_table(self):
        raw = '{"blocks": [{"type": "table", "headers": [], "rows": []}, {"type": "paragraph", "content": "x"}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        assert len(result.blocks) == 1

    def test_keeps_table_with_data(self):
        raw = '{"blocks": [{"type": "table", "headers": ["A"], "rows": [["val"]]}]}'
        result = StructuredOnboardingDayContent.model_validate_json(raw)
        assert len(result.blocks) == 1

class TestOnboardingQuestion:
    def test_normalize_correct_answer_lowercase(self):
        q = OnboardingQuestion(
            question="Q",
            option_a="A",
            option_b="B",
            option_c="C",
            option_d="D",
            correct_answer="B",
            explanation="Because",
        )
        assert q.correct_answer == "b"

    def test_normalize_correct_answer_strips_space(self):
        q = OnboardingQuestion(
            question="Q",
            option_a="A",
            option_b="B",
            option_c="C",
            option_d="D",
            correct_answer="  C  ",
            explanation="Because",
        )
        assert q.correct_answer == "c"

class TestGenerateOnboardingPlan:
    def _mock_days(self):
        days = []
        for i in range(1, 8):
            d = MagicMock()
            d.model_dump.return_value = {"day": i, "topic": f"T{i}", "task": f"Task{i}"}
            days.append(d)
        return days

    def test_returns_7_day_dicts_on_success(self):
        mock_response = MagicMock()
        mock_response.days = self._mock_days()
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            mock_build.return_value.chat.completions.create.return_value = mock_response
            result = generate_onboarding_plan("BE", "Locus", "docs", "openai", "k")
        assert result is not None
        assert len(result) == 7

    def test_returns_none_if_not_7_days(self):
        mock_response = MagicMock()
        mock_response.days = self._mock_days()[:5]
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            mock_build.return_value.chat.completions.create.return_value = mock_response
            result = generate_onboarding_plan("BE", "Locus", "docs", "openai", "k")
        assert result is None

    def test_returns_none_on_generic_exception(self):
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=Exception("boom")),
            patch("services.llm._raise_if_provider_error"),
        ):
            result = generate_onboarding_plan("BE", "Locus", "docs", "openai", "k")
        assert result is None

    def test_re_raises_http_exception(self):
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=HTTPException(status_code=401)),
        ):
            with pytest.raises(HTTPException):
                generate_onboarding_plan("BE", "Locus", "docs", "openai", "k")

class TestGenerateOnboardingDayContent:
    def _make_response(self):
        block = MagicMock()
        block.type = "paragraph"
        response = MagicMock(spec=StructuredOnboardingDayContent)
        response.blocks = [block]
        return response

    def test_returns_content_on_success(self):
        response = self._make_response()
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            mock_build.return_value.chat.completions.create.return_value = response
            result = generate_onboarding_day_content(
                "BE", "Locus", 1, "Topic", "Task", "docs", "openai", "k"
            )
        assert result is response

    def test_returns_none_if_no_blocks(self):
        response = MagicMock(spec=StructuredOnboardingDayContent)
        response.blocks = []
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            mock_build.return_value.chat.completions.create.return_value = response
            result = generate_onboarding_day_content(
                "BE", "Locus", 1, "Topic", "Task", "docs", "openai", "k"
            )
        assert result is None

    def test_uses_gemini_max_tokens(self):
        response = self._make_response()
        with (
            patch("services.llm._require_settings", return_value=("gemini", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}) as mock_tok,
        ):
            mock_build.return_value.chat.completions.create.return_value = response
            generate_onboarding_day_content("BE", "Locus", 2, "T", "T", "d", "gemini", "k")
        mock_tok.assert_called_with("gemini", 32768)

    def test_uses_openai_max_tokens(self):
        response = self._make_response()
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}) as mock_tok,
        ):
            mock_build.return_value.chat.completions.create.return_value = response
            generate_onboarding_day_content("BE", "Locus", 2, "T", "T", "d", "openai", "k")
        mock_tok.assert_called_with("openai", 16384)

    def test_returns_none_on_generic_exception(self):
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=Exception("boom")),
            patch("services.llm._raise_if_provider_error"),
        ):
            result = generate_onboarding_day_content("BE", "Locus", 1, "T", "T", "d", "openai", "k")
        assert result is None

    def test_re_raises_http_exception(self):
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=HTTPException(status_code=403)),
        ):
            with pytest.raises(HTTPException):
                generate_onboarding_day_content("BE", "Locus", 1, "T", "T", "d", "openai", "k")

class TestGenerateOnboardingQuiz:
    def _make_question(self, correct="a"):
        q = MagicMock(spec=OnboardingQuestion)
        q.model_dump.return_value = {"question": "Q", "correct_answer": correct}
        return q

    def test_returns_list_of_dicts_on_success(self):
        response = MagicMock()
        response.questions = [self._make_question() for _ in range(10)]
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            mock_build.return_value.chat.completions.create.return_value = response
            result = generate_onboarding_quiz(
                "BE", "Locus", ["T1"], "docs", provider="openai", api_key="k"
            )
        assert result is not None
        assert len(result) == 10

    def test_returns_none_if_no_questions(self):
        response = MagicMock()
        response.questions = []
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client") as mock_build,
            patch("services.llm._token_kwargs", return_value={}),
        ):
            mock_build.return_value.chat.completions.create.return_value = response
            result = generate_onboarding_quiz(
                "BE", "Locus", ["T1"], "docs", provider="openai", api_key="k"
            )
        assert result is None

    def test_returns_none_on_generic_exception(self):
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=Exception("boom")),
            patch("services.llm._raise_if_provider_error"),
        ):
            result = generate_onboarding_quiz(
                "BE", "Locus", [], "docs", provider="openai", api_key="k"
            )
        assert result is None

    def test_re_raises_http_exception(self):
        with (
            patch("services.llm._require_settings", return_value=("openai", "k")),
            patch("services.llm._build_client", side_effect=HTTPException(status_code=401)),
        ):
            with pytest.raises(HTTPException):
                generate_onboarding_quiz("BE", "Locus", [], "docs", provider="openai", api_key="k")

# ── onboarding service ────────────────────────────────────────────────────────

class TestLoadDocs:
    def test_raises_if_dir_missing(self):
        from services.onboarding import _load_docs

        with patch("services.onboarding.DOCS_DIR") as mock_dir:
            mock_dir.exists.return_value = False
            with pytest.raises(HTTPException) as exc:
                _load_docs()
            assert exc.value.status_code == 500

    def test_raises_if_no_md_files(self):
        from services.onboarding import _load_docs

        with patch("services.onboarding.DOCS_DIR") as mock_dir:
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = []
            with pytest.raises(HTTPException) as exc:
                _load_docs()
            assert exc.value.status_code == 500

    def test_returns_concatenated_docs(self):
        from services.onboarding import _load_docs

        mock_path = MagicMock()
        mock_path.stem = "doc1"
        mock_path.read_text.return_value = "content"
        with patch("services.onboarding.DOCS_DIR") as mock_dir:
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = [mock_path]
            result = _load_docs()
        assert "doc1" in result
        assert "content" in result

    def test_role_filter_includes_only_relevant_files(self):
        from services.onboarding import _load_docs

        # backend role → prefixes 01, 02, 03, 04, 05, 07, 08, 11
        included = MagicMock()
        included.name = "01_backend_engineer_onboarding.md"
        included.stem = "01_backend_engineer_onboarding"
        included.read_text.return_value = "be content"

        excluded = MagicMock()
        excluded.name = "13_sdet_new_stack_checklist.md"
        excluded.stem = "13_sdet_new_stack_checklist"
        excluded.read_text.return_value = "sdet content"

        with patch("services.onboarding.DOCS_DIR") as mock_dir:
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = [included, excluded]
            result = _load_docs("Backend Engineer")

        assert "be content" in result
        assert "sdet content" not in result

    def test_unknown_role_loads_all_docs(self):
        from services.onboarding import _load_docs

        path1 = MagicMock()
        path1.name = "01_some.md"
        path1.stem = "01_some"
        path1.read_text.return_value = "doc1"

        path2 = MagicMock()
        path2.name = "13_other.md"
        path2.stem = "13_other"
        path2.read_text.return_value = "doc2"

        with patch("services.onboarding.DOCS_DIR") as mock_dir:
            mock_dir.exists.return_value = True
            mock_dir.glob.return_value = [path1, path2]
            result = _load_docs("Data Scientist")

        assert "doc1" in result
        assert "doc2" in result

class TestSelectDocPrefixes:
    def test_backend_role_includes_backend_prefixes(self):
        from services.onboarding import _select_doc_prefixes

        result = _select_doc_prefixes("Backend Engineer")
        assert "01" in result
        assert "08" in result
        assert "11" in result
        # workflow + OPA docs included
        assert "16" in result
        assert "17" in result
        assert "18" in result
        # common docs also included
        assert "07" in result
        # SDET docs excluded
        assert "13" not in result
        assert "14" not in result

    def test_sdet_role_includes_sdet_prefixes(self):
        from services.onboarding import _select_doc_prefixes

        result = _select_doc_prefixes("SDET Engineer")
        assert "06" in result
        assert "13" in result
        assert "14" in result
        # backend-specific excluded
        assert "01" not in result
        assert "11" not in result

    def test_devops_role_includes_devops_prefixes(self):
        from services.onboarding import _select_doc_prefixes

        result = _select_doc_prefixes("DevOps Engineer")
        assert "09" in result
        assert "10" in result
        assert "12" in result
        assert "13" not in result

    def test_unknown_role_returns_none(self):
        from services.onboarding import _select_doc_prefixes

        result = _select_doc_prefixes("Data Scientist")
        assert result is None

    def test_product_manager_role(self):
        from services.onboarding import _select_doc_prefixes

        result = _select_doc_prefixes("Product Manager")
        assert "15" in result
        assert "12" in result
        assert "01" not in result

    def test_qa_role_same_as_sdet(self):
        from services.onboarding import _select_doc_prefixes

        result = _select_doc_prefixes("QA Automation Engineer")
        assert "06" in result
        assert "13" in result
        assert "14" in result

class TestOnboardingService:
    def test_generate_plan_success(self):
        days_data = [{"day": i, "topic": f"T{i}", "task": f"Task{i}"} for i in range(1, 8)]
        plan = _make_plan()
        day_obj = _make_day()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = [day_obj] * 7
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_plan",
                    return_value=days_data,
                ),
            ):
                from services.onboarding import generate_plan

                result = generate_plan("1", "Backend Engineer", "Locus", "openai", "k", None)
            assert "plan" in result
            assert "days" in result
        finally:
            patcher.stop()

    def test_generate_plan_fails_if_llm_returns_none(self):
        patcher, session = _patch_session()
        try:
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_plan", return_value=None
                ),
            ):
                from services.onboarding import generate_plan

                with pytest.raises(HTTPException) as exc:
                    generate_plan("1", "Backend Engineer", "Locus", "openai", "k", None)
            assert exc.value.status_code == 500
        finally:
            patcher.stop()

    def test_get_plan_returns_plan_and_days(self):
        plan = _make_plan()
        days = [_make_day(i) for i in range(1, 8)]
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = days
            from services.onboarding import get_plan

            result = get_plan(1, "1")
            assert result["plan"]["id"] == 1
            assert len(result["days"]) == 7
        finally:
            patcher.stop()

    def test_get_plan_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import get_plan

            with pytest.raises(HTTPException) as exc:
                get_plan(99, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_plan_wrong_user(self):
        plan = _make_plan(user_id="999")
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            from services.onboarding import get_plan

            with pytest.raises(HTTPException) as exc:
                get_plan(1, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_day_content_plan_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import get_day_content

            with pytest.raises(HTTPException) as exc:
                get_day_content(99, 1, "1", "openai", "k", None)
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_day_content_returns_cached(self):
        plan = _make_plan()
        day = _make_day(content_blocks=json.dumps([{"type": "paragraph", "content": "cached"}]))
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.first.return_value = day
            from services.onboarding import get_day_content

            result = get_day_content(1, 1, "1", "openai", "k", None)
            assert "day" in result
        finally:
            patcher.stop()

    def test_get_day_content_generates_and_caches(self):
        plan = _make_plan()
        day = _make_day()
        content_mock = MagicMock()
        block = MagicMock()
        block.model_dump.return_value = {"type": "paragraph", "content": "new"}
        content_mock.blocks = [block]
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.first.return_value = day
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_day_content",
                    return_value=content_mock,
                ),
            ):
                from services.onboarding import get_day_content

                result = get_day_content(1, 1, "1", "openai", "k", None)
            assert "day" in result
        finally:
            patcher.stop()

    def test_get_day_content_fails_if_llm_returns_none(self):
        plan = _make_plan()
        day = _make_day()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.first.return_value = day
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_day_content",
                    return_value=None,
                ),
            ):
                from services.onboarding import get_day_content

                with pytest.raises(HTTPException) as exc:
                    get_day_content(1, 1, "1", "openai", "k", None)
            assert exc.value.status_code == 500
        finally:
            patcher.stop()

    def test_get_day_content_day_not_found(self):
        plan = _make_plan()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.first.return_value = None
            from services.onboarding import get_day_content

            with pytest.raises(HTTPException) as exc:
                get_day_content(1, 99, "1", "openai", "k", None)
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_list_plans_returns_list(self):
        plan = _make_plan()
        days = [_make_day(i, completed=(i <= 3)) for i in range(1, 8)]
        patcher, session = _patch_session()
        try:
            session.exec.return_value.all.side_effect = [[plan], days]
            from services.onboarding import list_plans

            result = list_plans("1")
            assert isinstance(result, list)
        finally:
            patcher.stop()

    def test_toggle_share_enables(self):
        plan = _make_plan()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            from services.onboarding import toggle_share

            result = toggle_share(1, "1", True)
            assert result["share_enabled"] is True
        finally:
            patcher.stop()

    def test_toggle_share_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import toggle_share

            with pytest.raises(HTTPException) as exc:
                toggle_share(99, "1", True)
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_public_plan_returns_when_shared(self):
        plan = _make_plan()
        plan.share_enabled = True
        days = [_make_day(i) for i in range(1, 8)]
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = days
            from services.onboarding import get_public_plan

            result = get_public_plan(1)
            assert "plan" in result
        finally:
            patcher.stop()

    def test_get_public_plan_returns_404_when_not_shared(self):
        plan = _make_plan()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            from services.onboarding import get_public_plan

            with pytest.raises(HTTPException) as exc:
                get_public_plan(1)
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_complete_day_sets_completed(self):
        plan = _make_plan()
        day = _make_day()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.first.return_value = day
            from services.onboarding import complete_day

            result = complete_day(1, 1, "1")
            assert result["day"]["completed"] is True
        finally:
            patcher.stop()

    def test_complete_day_plan_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import complete_day

            with pytest.raises(HTTPException) as exc:
                complete_day(99, 1, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_complete_day_not_found(self):
        plan = _make_plan()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.first.return_value = None
            from services.onboarding import complete_day

            with pytest.raises(HTTPException) as exc:
                complete_day(1, 99, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_delete_plan_success(self):
        plan = _make_plan()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            from services.onboarding import delete_plan

            result = delete_plan(1, "1")
            assert result["deleted"] is True
        finally:
            patcher.stop()

    def test_delete_plan_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import delete_plan

            with pytest.raises(HTTPException) as exc:
                delete_plan(99, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_final_quiz_plan_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import get_final_quiz

            with pytest.raises(HTTPException) as exc:
                get_final_quiz(99, "1", "openai", "k", None)
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_final_quiz_generates_and_caches(self):
        plan = _make_plan()
        days = [_make_day(i) for i in range(1, 8)]
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = days
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_quiz",
                    return_value=questions,
                ),
            ):
                from services.onboarding import get_final_quiz

                result = get_final_quiz(1, "1", "openai", "k", None)
            assert len(result["questions"]) == 10
            assert result["attempts"] == []
        finally:
            patcher.stop()

    def test_get_final_quiz_returns_cached_with_attempts(self):
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        plan = _make_plan(quiz_questions=json.dumps(questions))
        attempt = _make_attempt()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = [attempt]
            from services.onboarding import get_final_quiz

            result = get_final_quiz(1, "1", "openai", "k", None)
            assert len(result["questions"]) == 10
            assert len(result["attempts"]) == 1
        finally:
            patcher.stop()

    def test_get_final_quiz_fails_if_llm_returns_none(self):
        plan = _make_plan()
        days = [_make_day(i) for i in range(1, 8)]
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = days
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_quiz", return_value=None
                ),
            ):
                from services.onboarding import get_final_quiz

                with pytest.raises(HTTPException) as exc:
                    get_final_quiz(1, "1", "openai", "k", None)
            assert exc.value.status_code == 500
        finally:
            patcher.stop()

    def test_save_quiz_attempt_scores_correctly(self):
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        plan = _make_plan(quiz_questions=json.dumps(questions))
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            attempt = _make_attempt(score=100, correct=10)
            session.exec.return_value.first.return_value = attempt
            answers = {str(i): "a" for i in range(10)}  # all correct
            from services.onboarding import save_quiz_attempt

            result = save_quiz_attempt(1, "1", answers)
            assert result["score"] == 100
            assert result["correct"] == 10
        finally:
            patcher.stop()

    def test_save_quiz_attempt_no_quiz_yet(self):
        plan = _make_plan()  # no quiz_questions
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            from services.onboarding import save_quiz_attempt

            with pytest.raises(HTTPException) as exc:
                save_quiz_attempt(1, "1", {"0": "a"})
            assert exc.value.status_code == 400
        finally:
            patcher.stop()

    def test_save_quiz_attempt_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import save_quiz_attempt

            with pytest.raises(HTTPException) as exc:
                save_quiz_attempt(99, "1", {})
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_quiz_plan_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import get_quiz

            with pytest.raises(HTTPException) as exc:
                get_quiz(99, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_quiz_not_generated(self):
        plan = _make_plan()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            from services.onboarding import get_quiz

            with pytest.raises(HTTPException) as exc:
                get_quiz(1, "1")
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_get_quiz_returns_cached(self):
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        plan = _make_plan(quiz_questions=json.dumps(questions))
        attempt = _make_attempt()
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = [attempt]
            from services.onboarding import get_quiz

            result = get_quiz(1, "1")
            assert len(result["questions"]) == 10
            assert len(result["attempts"]) == 1
        finally:
            patcher.stop()

    def test_generate_quiz_plan_not_found(self):
        patcher, session = _patch_session()
        try:
            session.get.return_value = None
            from services.onboarding import generate_quiz

            with pytest.raises(HTTPException) as exc:
                generate_quiz(99, "1", "openai", "k", None)
            assert exc.value.status_code == 404
        finally:
            patcher.stop()

    def test_generate_quiz_already_exists(self):
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        plan = _make_plan(quiz_questions=json.dumps(questions))
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            from services.onboarding import generate_quiz

            with pytest.raises(HTTPException) as exc:
                generate_quiz(1, "1", "openai", "k", None)
            assert exc.value.status_code == 409
        finally:
            patcher.stop()

    def test_generate_quiz_success(self):
        plan = _make_plan()
        days = [_make_day(i) for i in range(1, 8)]
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = days
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_quiz",
                    return_value=questions,
                ),
            ):
                from services.onboarding import generate_quiz

                result = generate_quiz(1, "1", "openai", "k", None)
            assert len(result["questions"]) == 10
            assert result["attempts"] == []
        finally:
            patcher.stop()

    def test_generate_quiz_llm_fails(self):
        plan = _make_plan()
        days = [_make_day(i) for i in range(1, 8)]
        patcher, session = _patch_session()
        try:
            session.get.return_value = plan
            session.exec.return_value.all.return_value = days
            with (
                patch("services.onboarding._load_docs", return_value="docs"),
                patch(
                    "services.onboarding.llm_service.generate_onboarding_quiz", return_value=None
                ),
            ):
                from services.onboarding import generate_quiz

                with pytest.raises(HTTPException) as exc:
                    generate_quiz(1, "1", "openai", "k", None)
            assert exc.value.status_code == 500
        finally:
            patcher.stop()

# ── routes ────────────────────────────────────────────────────────────────────

class TestOnboardingRoutes:
    def test_list_plans_unauthenticated(self, anon_client):
        response = anon_client.get("/onboarding")
        assert response.status_code == 401

    def test_list_plans_authenticated(self, auth_client):
        with patch("controllers.onboarding.onboarding_service.list_plans", return_value=[]):
            response = auth_client.get("/onboarding")
        assert response.status_code == 200
        assert response.json() == []

    def test_generate_plan_unauthenticated(self, anon_client):
        response = anon_client.post("/onboarding/generate", json={"role": "SWE"})
        assert response.status_code == 401

    def test_generate_plan_success(self, auth_client):
        plan = _make_plan()
        days = [_make_day(i) for i in range(1, 8)]
        result = {"plan": plan.model_dump(), "days": [d.model_dump() for d in days]}
        with patch("controllers.onboarding.onboarding_service.generate_plan", return_value=result):
            response = auth_client.post("/onboarding/generate", json={"role": "SWE"})
        assert response.status_code == 200

    def test_get_plan_unauthenticated(self, anon_client):
        response = anon_client.get("/onboarding/1")
        assert response.status_code == 401

    def test_get_plan_success(self, auth_client):
        plan = _make_plan()
        days = [_make_day(i) for i in range(1, 8)]
        result = {"plan": plan.model_dump(), "days": [d.model_dump() for d in days]}
        with patch("controllers.onboarding.onboarding_service.get_plan", return_value=result):
            response = auth_client.get("/onboarding/1")
        assert response.status_code == 200

    def test_get_plan_not_found(self, auth_client):
        with patch(
            "controllers.onboarding.onboarding_service.get_plan",
            side_effect=HTTPException(status_code=404, detail="Not found"),
        ):
            response = auth_client.get("/onboarding/99")
        assert response.status_code == 404

    def test_get_day_content_unauthenticated(self, anon_client):
        response = anon_client.get("/onboarding/1/day/1")
        assert response.status_code == 401

    def test_get_day_content_success(self, auth_client):
        day = _make_day()
        with patch(
            "controllers.onboarding.onboarding_service.get_day_content",
            return_value={"day": day.model_dump()},
        ):
            response = auth_client.get("/onboarding/1/day/1")
        assert response.status_code == 200

    def test_complete_day_success(self, auth_client):
        day = _make_day(completed=True)
        with patch(
            "controllers.onboarding.onboarding_service.complete_day",
            return_value={"day": day.model_dump()},
        ):
            response = auth_client.post("/onboarding/1/day/1/complete")
        assert response.status_code == 200

    def test_delete_plan_unauthenticated(self, anon_client):
        response = anon_client.delete("/onboarding/1")
        assert response.status_code == 401

    def test_delete_plan_success(self, auth_client):
        with patch(
            "controllers.onboarding.onboarding_service.delete_plan", return_value={"deleted": True}
        ):
            response = auth_client.delete("/onboarding/1")
        assert response.status_code == 200

    def test_get_quiz_unauthenticated(self, anon_client):
        response = anon_client.get("/onboarding/1/quiz")
        assert response.status_code == 401

    def test_get_quiz_success(self, auth_client):
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        with patch(
            "controllers.onboarding.onboarding_service.get_quiz",
            return_value={"questions": questions, "attempts": []},
        ):
            response = auth_client.get("/onboarding/1/quiz")
        assert response.status_code == 200

    def test_submit_quiz_attempt_success(self, auth_client):
        result = {"attempt": {"id": 1, "score": 80}, "score": 80, "correct": 8, "total": 10}
        with patch(
            "controllers.onboarding.onboarding_service.save_quiz_attempt", return_value=result
        ):
            response = auth_client.post("/onboarding/1/quiz/attempt", json={"answers": {"0": "a"}})
        assert response.status_code == 200

    def test_toggle_share_unauthenticated(self, anon_client):
        response = anon_client.patch("/onboarding/1/share?enable=true")
        assert response.status_code == 401

    def test_toggle_share_success(self, auth_client):
        plan = _make_plan()
        plan.share_enabled = True
        with patch(
            "controllers.onboarding.onboarding_service.toggle_share", return_value=plan.model_dump()
        ):
            response = auth_client.patch("/onboarding/1/share?enable=true")
        assert response.status_code == 200

    def test_get_public_plan_success(self, anon_client):
        plan = _make_plan()
        plan.share_enabled = True
        days = [_make_day(i) for i in range(1, 8)]
        result = {"plan": plan.model_dump(), "days": [d.model_dump() for d in days]}
        with patch(
            "controllers.onboarding.onboarding_service.get_public_plan", return_value=result
        ):
            response = anon_client.get("/public/onboarding/1")
        assert response.status_code == 200

    def test_get_public_plan_not_found(self, anon_client):
        with patch(
            "controllers.onboarding.onboarding_service.get_public_plan",
            side_effect=HTTPException(status_code=404, detail="Not found"),
        ):
            response = anon_client.get("/public/onboarding/99")
        assert response.status_code == 404

    def test_generate_quiz_route_success(self, auth_client):
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        with patch(
            "controllers.onboarding.onboarding_service.generate_quiz",
            return_value={"questions": questions, "attempts": []},
        ):
            response = auth_client.post("/onboarding/1/quiz/generate")
        assert response.status_code == 200

    def test_generate_quiz_route_unauthenticated(self, anon_client):
        response = anon_client.post("/onboarding/1/quiz/generate")
        assert response.status_code == 401

    def test_get_final_quiz_controller(self):
        questions = [{"question": f"Q{i}", "correct_answer": "a"} for i in range(10)]
        user = MagicMock()
        user.id = 1
        with (
            patch("controllers.onboarding.get_user_provider_name", return_value="openai"),
            patch("controllers.onboarding.get_user_api_key", return_value="k"),
            patch("controllers.onboarding.get_user_model", return_value=None),
            patch(
                "controllers.onboarding.onboarding_service.get_final_quiz",
                return_value={"questions": questions, "attempts": []},
            ) as mock_svc,
        ):
            from controllers.onboarding import get_final_quiz

            result = get_final_quiz(1, user)
        assert len(result["questions"]) == 10
        mock_svc.assert_called_once()
