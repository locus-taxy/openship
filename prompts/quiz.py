from typing import Dict, List, Optional

_QUIZ_JSON_SCHEMA = (
    '{"questions": [{'
    '"question": "...", '
    '"options": [{"label": "A", "text": "..."}, {"label": "B", "text": "..."}, '
    '{"label": "C", "text": "..."}, {"label": "D", "text": "..."}], '
    '"correct_option": "A", "explanation": "..."}]}'
)

def weekly_system_prompt(skill: str, week: int, num_topics: int) -> str:
    return (
        f"You are an expert educator creating a short week {week} quiz for a student "
        f"studying {skill}. The quiz covers {num_topics} topic(s) from this week only. "
        f"Return ONLY a raw JSON object (no markdown, no code fences) matching: {_QUIZ_JSON_SCHEMA}"
    )

def weekly_user_prompt(topics: List[str], num_questions: int) -> str:
    topics_list = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    return (
        f"Week topics:\n{topics_list}\n\n"
        f"Generate exactly {num_questions} multiple-choice questions.\n"
        f"Rules:\n"
        f"- Each question must have exactly 4 options with labels A, B, C, D\n"
        f"- Each question must test exactly ONE of the listed topics\n"
        f"- MANDATORY: include at least 1 question per topic — no topic may be skipped\n"
        f"- Spread any remaining questions evenly across the topics\n"
        f"- The explanation should clarify why the correct answer is right (1-2 sentences)"
    )

def final_system_prompt(skill: str, num_topics: int) -> str:
    return (
        f"You are an expert educator creating a personalised final quiz for a student "
        f"who has completed a {skill} course. The quiz targets {num_topics} topic(s) "
        f"the student found most difficult or has started to forget. "
        f"Return ONLY a raw JSON object (no markdown, no code fences) matching: {_QUIZ_JSON_SCHEMA}"
    )

def final_user_prompt(
    weak_topics: List[str],
    forgotten_topics: List[str],
    num_questions: int,
    topic_week_map: Optional[Dict[str, int]] = None,
) -> str:
    all_topics = list(dict.fromkeys(weak_topics + forgotten_topics))

    if topic_week_map:
        # Group topics by week so the LLM understands which belonged together
        by_week: Dict[int, List[str]] = {}
        ungrouped: List[str] = []
        for t in all_topics:
            w = topic_week_map.get(t)
            if w:
                by_week.setdefault(w, []).append(t)
            else:
                ungrouped.append(t)

        sections: List[str] = []
        for week in sorted(by_week):
            items = ", ".join(by_week[week])
            sections.append(f"Week {week}: {items}")
        if ungrouped:
            sections.append("Other: " + ", ".join(ungrouped))
        topics_block = "\n".join(sections)
        preamble = (
            "The student struggled with or is forgetting these topics "
            "(grouped by the week they were covered):\n" + topics_block
        )
    else:
        topics_list = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(all_topics))
        preamble = f"The student struggled with or is forgetting these topics:\n{topics_list}"

    return (
        f"{preamble}\n\n"
        f"Generate exactly {num_questions} multiple-choice questions.\n"
        f"Rules:\n"
        f"- Each question must have exactly 4 options with labels A, B, C, D\n"
        f"- Focus on the topics the student found hardest — weight weaker topics more heavily\n"
        f"- Vary question types: definitions, application reasoning, comparisons, edge cases\n"
        f"- The explanation should clarify why the correct answer is right (1-2 sentences)"
    )
