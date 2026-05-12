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

class TestQuizPrompts:
    def test_system_prompt_beginner(self):
        result = quiz_prompts.system_prompt("Python", "beginner", 30)
        assert isinstance(result, str) and len(result) > 50

    def test_system_prompt_contains_difficulty(self):
        result = quiz_prompts.system_prompt("Python", "intermediate", 30)
        assert "intermediate" in result

    def test_system_prompt_contains_skill(self):
        result = quiz_prompts.system_prompt("SQL", "advanced", 15)
        assert "SQL" in result

    def test_system_prompt_contains_num_topics(self):
        result = quiz_prompts.system_prompt("Python", "beginner", 30)
        assert "30" in result

    def test_user_prompt_contains_question_count(self):
        topics = ["Variables", "Loops", "Functions"]
        result = quiz_prompts.user_prompt(topics, 10, "beginner")
        assert "10" in result

    def test_user_prompt_contains_difficulty(self):
        result = quiz_prompts.user_prompt(["SELECT", "JOIN"], 12, "intermediate")
        assert "intermediate" in result

    def test_user_prompt_contains_topics(self):
        topics = ["Variables", "Loops"]
        result = quiz_prompts.user_prompt(topics, 10, "beginner")
        assert "Variables" in result and "Loops" in result
