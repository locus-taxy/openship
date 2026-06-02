def system_prompt(days: int, hours: int) -> str:
    return (
        "You are an expert curriculum designer and career mentor. "
        "Create an in-depth, structured learning roadmap for the requested skill. "
        f"The total duration must be exactly {days} days with {hours} hours per day. "
        "Ensure daily tasks are specific, actionable, and progressively build depth.\n\n"
        "CRITICAL: Return ONLY a raw JSON object (no markdown, no code fences) with this exact structure:\n"
        "{\n"
        '  "months": [\n'
        "    {\n"
        '      "month": 1,\n'
        '      "title": "Month title",\n'
        '      "goal": "What the learner achieves this month",\n'
        '      "weeks": [\n'
        "        {\n"
        '          "week": 1,\n'
        '          "title": "Week title",\n'
        '          "days_range": "Days 1-7",\n'
        '          "daily_plan": [\n'
        '            {"day": 1, "topic": "Topic name", "task": "Specific actionable task"},\n'
        '            {"day": 2, "topic": "Topic name", "task": "Specific actionable task"}\n'
        "          ]\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Every field is required. Do not add extra fields. Number days continuously from 1."
    )

def user_prompt(skill: str, days: int, hours: int) -> str:
    return (
        f"Create a comprehensive learning syllabus to master '{skill}'. "
        f"The plan must span exactly {days} days with {hours} hours per day. "
        "Return the complete roadmap as a JSON object matching the structure in the system prompt."
    )

def week_plan_system_prompt(skill: str, week: int, total_weeks: int, days_in_week: int) -> str:
    return (
        f"You are an expert curriculum designer creating Week {week} of a {total_weeks}-week course on '{skill}'. "
        f"Generate a day-by-day learning plan for exactly {days_in_week} days. "
        "Prioritise reinforcing the student's weak and forgotten topics while introducing the next logical concepts. "
        "Each day must have a concise topic title and a specific, actionable task description. "
        "Return ONLY a raw JSON object (no markdown, no code fences) matching: "
        '{"days": [{"day": 1, "topic": "...", "task": "..."}]}'
    )

def week_plan_user_prompt(
    week: int,
    start_day: int,
    days_in_week: int,
    weak_topics: list,
    forgotten_topics: list,
    prev_score: int = 100,
    remediation_days: int = 0,
) -> str:
    lines = [f"Generate the daily plan for Week {week}."]
    lines.append(f"Number the days {start_day} through {start_day + days_in_week - 1}.")

    new_days = days_in_week - remediation_days

    if remediation_days > 0:
        review_topics = weak_topics + forgotten_topics
        review_str = ", ".join(review_topics) if review_topics else "previously covered topics"
        lines.append(f"\nThe student scored {prev_score}% on the previous week's quiz.")
        lines.append(
            f"Dedicate days {start_day} through {start_day + remediation_days - 1} "
            f"({remediation_days} day{'s' if remediation_days > 1 else ''}) to reviewing and reinforcing: "
            f"{review_str}."
        )
        if weak_topics:
            lines.append(f"Weak topics (lowest mastery first): {', '.join(weak_topics)}")
        if forgotten_topics:
            lines.append(
                f"Forgotten topics (needs spaced repetition): {', '.join(forgotten_topics)}"
            )
        lines.append(
            f"Days {start_day + remediation_days} through {start_day + days_in_week - 1} "
            f"({new_days} day{'s' if new_days > 1 else ''}) MUST introduce entirely new topics "
            f"that build on previous weeks — do NOT repeat reviewed topics here."
        )
    else:
        if weak_topics:
            lines.append(
                f"\nTopics the student found difficult (weave in reinforcement): {', '.join(weak_topics)}"
            )
        if forgotten_topics:
            lines.append(f"Topics that need spaced repetition: {', '.join(forgotten_topics)}")
        lines.append(
            f"\nAll {days_in_week} days should introduce new, progressively advanced topics "
            f"that build naturally on previous weeks."
        )

    lines.append(f"\nReturn exactly {days_in_week} days.")
    return "\n".join(lines)
