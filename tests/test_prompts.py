from prompts import chapter as chapter_prompts
from prompts import syllabus as syllabus_prompts
from prompts import quiz as quiz_prompts

class TestSyllabusPrompts:
    def test_system_prompt_is_nonempty(self):
        result = syllabus_prompts.system_prompt(days=30, hours=2)
        assert isinstance(result, str) and len(result) > 50

    def test_system_prompt_contains_days(self):
        result = syllabus_prompts.system_prompt(days=45, hours=3)
        assert "45 days" in result

    def test_system_prompt_contains_hours(self):
        result = syllabus_prompts.system_prompt(days=30, hours=2)
        assert "2 hours" in result

    def test_user_prompt_contains_skill(self):
        result = syllabus_prompts.user_prompt("Python Programming", 30, 2)
        assert "Python Programming" in result

    def test_user_prompt_contains_days(self):
        result = syllabus_prompts.user_prompt("SQL", 60, 1)
        assert "60" in result

    def test_user_prompt_contains_hours(self):
        result = syllabus_prompts.user_prompt("SQL", 30, 3)
        assert "3" in result

class TestChapterPrompts:
    def test_system_prompt_is_nonempty(self):
        result = chapter_prompts.system_prompt()
        assert isinstance(result, str) and len(result) > 200

    def test_system_prompt_contains_all_block_types(self):
        prompt = chapter_prompts.system_prompt()
        for block in [
            "heading",
            "paragraph",
            "code",
            "bullet_list",
            "numbered_list",
            "table",
            "note",
            "quote",
            "divider",
            "diagram",
        ]:
            assert block in prompt, f"Block type '{block}' missing from chapter prompt"

    def test_system_prompt_contains_mermaid(self):
        assert "mermaid" in chapter_prompts.system_prompt()

    def test_system_prompt_specifies_block_count(self):
        prompt = chapter_prompts.system_prompt()
        assert "8" in prompt and "14" in prompt

    def test_user_prompt_contains_task_title(self):
        result = chapter_prompts.user_prompt("Intro to Variables", "Python", "Learn variables")
        assert "Intro to Variables" in result

    def test_user_prompt_contains_skill(self):
        result = chapter_prompts.user_prompt("Loops", "JavaScript", "For loops")
        assert "JavaScript" in result

    def test_user_prompt_contains_description(self):
        result = chapter_prompts.user_prompt("Loops", "JavaScript", "For loops and while loops")
        assert "For loops and while loops" in result

    def test_non_technical_prompt_forbids_code_blocks(self):
        prompt = chapter_prompts.system_prompt(is_technical=False)
        assert "DOMAIN CONSTRAINT" in prompt
        assert "MUST NOT include any 'code' blocks" in prompt

    def test_non_technical_example_heavy_uses_list_variant(self):
        prompt = chapter_prompts.system_prompt(is_technical=False, style="example_heavy")
        assert "DOMAIN CONSTRAINT" in prompt
        # The non-technical example_heavy variant should not mention 'code' block as an option
        style_section = prompt.split("MANDATORY STYLE RULES")[1]
        assert "'code' block" not in style_section

    def test_technical_prompt_has_no_domain_constraint(self):
        prompt = chapter_prompts.system_prompt(is_technical=True)
        assert "DOMAIN CONSTRAINT" not in prompt

    def test_none_is_technical_has_no_domain_constraint(self):
        prompt = chapter_prompts.system_prompt(is_technical=None)
        assert "DOMAIN CONSTRAINT" not in prompt

class TestQuizPrompts:
    def test_weekly_system_prompt_contains_skill(self):
        result = quiz_prompts.weekly_system_prompt("Python", 1, 3)
        assert "Python" in result and isinstance(result, str)

    def test_weekly_system_prompt_contains_week(self):
        result = quiz_prompts.weekly_system_prompt("Python", 2, 3)
        assert "2" in result

    def test_weekly_system_prompt_contains_num_topics(self):
        result = quiz_prompts.weekly_system_prompt("Python", 1, 5)
        assert "5" in result

    def test_weekly_user_prompt_contains_question_count(self):
        result = quiz_prompts.weekly_user_prompt(["Variables", "Loops"], 5)
        assert "5" in result

    def test_weekly_user_prompt_contains_topics(self):
        result = quiz_prompts.weekly_user_prompt(["Variables", "Loops"], 5)
        assert "Variables" in result and "Loops" in result

    def test_final_system_prompt_contains_skill(self):
        result = quiz_prompts.final_system_prompt("SQL", 4)
        assert "SQL" in result

    def test_final_user_prompt_contains_weak_topics(self):
        result = quiz_prompts.final_user_prompt(["Loops"], ["Functions"], 10)
        assert "Loops" in result and "Functions" in result

    def test_final_user_prompt_deduplicates_topics(self):
        result = quiz_prompts.final_user_prompt(["Loops"], ["Loops"], 5)
        assert result.count("Loops") == 1

    def test_final_user_prompt_with_topic_week_map_groups_by_week(self):
        result = quiz_prompts.final_user_prompt(
            ["Variables", "Loops"],
            ["Functions"],
            10,
            topic_week_map={"Variables": 1, "Loops": 1, "Functions": 2},
        )
        assert "Week 1" in result
        assert "Week 2" in result
        assert "Variables" in result
        assert "Functions" in result

    def test_final_user_prompt_with_topic_week_map_ungrouped_topics(self):
        result = quiz_prompts.final_user_prompt(
            ["Variables"],
            ["Loops"],
            5,
            topic_week_map={"Variables": 1},  # Loops has no week mapping
        )
        assert "Week 1" in result
        assert "Other" in result
        assert "Loops" in result

class TestWeekPlanPrompts:
    def test_system_prompt_contains_skill(self):
        result = syllabus_prompts.week_plan_system_prompt("Python", 2, 4, 7)
        assert "Python" in result

    def test_system_prompt_contains_week_number(self):
        result = syllabus_prompts.week_plan_system_prompt("SQL", 3, 6, 5)
        assert "3" in result and "6" in result

    def test_system_prompt_contains_days_in_week(self):
        result = syllabus_prompts.week_plan_system_prompt("Rust", 1, 4, 7)
        assert "7" in result

    def test_system_prompt_is_nonempty_string(self):
        result = syllabus_prompts.week_plan_system_prompt("JavaScript", 1, 4, 5)
        assert isinstance(result, str) and len(result) > 50

    def test_user_prompt_contains_week_number(self):
        result = syllabus_prompts.week_plan_user_prompt(2, 8, 7, [], [])
        assert "2" in result

    def test_user_prompt_contains_day_range(self):
        result = syllabus_prompts.week_plan_user_prompt(2, 8, 7, [], [])
        assert "8" in result and "14" in result

    def test_user_prompt_mentions_weak_topics(self):
        result = syllabus_prompts.week_plan_user_prompt(1, 1, 7, ["Variables", "Loops"], [])
        assert "Variables" in result and "Loops" in result

    def test_user_prompt_mentions_forgotten_topics(self):
        result = syllabus_prompts.week_plan_user_prompt(1, 1, 7, [], ["Functions"])
        assert "Functions" in result

    def test_user_prompt_new_topics_message_when_no_weak_areas(self):
        result = syllabus_prompts.week_plan_user_prompt(1, 1, 7, [], [])
        assert "new" in result.lower()

    def test_user_prompt_contains_exact_days_count(self):
        result = syllabus_prompts.week_plan_user_prompt(3, 15, 5, [], [])
        assert "5" in result

    def test_user_prompt_remediation_mentions_score(self):
        result = syllabus_prompts.week_plan_user_prompt(
            2, 8, 7, ["Loops", "Functions"], [], prev_score=30, remediation_days=4
        )
        assert "30%" in result

    def test_user_prompt_remediation_mentions_review_days(self):
        result = syllabus_prompts.week_plan_user_prompt(
            2, 8, 7, ["Loops"], ["Decorators"], prev_score=40, remediation_days=3
        )
        assert "Loops" in result and "Decorators" in result

    def test_user_prompt_remediation_mentions_new_topics_for_remaining_days(self):
        result = syllabus_prompts.week_plan_user_prompt(
            2, 8, 7, [], [], prev_score=50, remediation_days=3
        )
        assert "new" in result.lower()
