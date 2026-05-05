from typing import List

_DIFFICULTY_DESC = {
    "beginner": "recall and basic understanding",
    "intermediate": "application and problem-solving",
    "advanced": "analysis, edge cases, and trade-offs",
}

def system_prompt(skill: str, difficulty: str, num_topics: int) -> str:
    return (
        f"You are an expert educator creating a {difficulty}-level quiz for a student who "
        f"has just completed a {skill} course covering {num_topics} topics."
    )

def user_prompt(topics: List[str], num_questions: int, difficulty: str) -> str:
    difficulty_desc = _DIFFICULTY_DESC.get(difficulty, "recall and basic understanding")
    topics_list = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    return (
        f"The course covered these topics (in order):\n{topics_list}\n\n"
        f"Generate exactly {num_questions} multiple-choice questions.\n"
        f"Rules:\n"
        f"- Each question must have exactly 4 options with labels A, B, C, D\n"
        f"- Questions should test understanding across the breadth of the course topics\n"
        f"- Difficulty level: {difficulty} — focus on {difficulty_desc}\n"
        f"- Vary question types: definitions, code reasoning, best-practice selection, comparisons\n"
        f"- The explanation should clarify why the correct answer is right (1-2 sentences)"
    )
