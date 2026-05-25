def system_prompt(days: int, hours: int) -> str:
    return (
        "You are an expert curriculum designer and career mentor. "
        "Create an in-depth, structured learning roadmap for the requested skill. "
        f"The total duration must be exactly {days} days with {hours} hours per day. "
        "Ensure daily tasks are specific, actionable, and progressively build depth."
    )

def user_prompt(skill: str, days: int, hours: int) -> str:
    return (
        f"Create a comprehensive learning syllabus to master '{skill}'. "
        f"The plan must span exactly {days} days with {hours} hours per day. "
        "Return the complete roadmap."
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
) -> str:
    lines = [f"Generate the daily plan for Week {week}."]
    lines.append(f"Number the days {start_day} through {start_day + days_in_week - 1}.")
    if weak_topics:
        lines.append(
            f"\nTopics the student struggled with (give extra focus): {', '.join(weak_topics)}"
        )
    if forgotten_topics:
        lines.append(
            f"Topics the student has forgotten (reintroduce with spaced repetition): {', '.join(forgotten_topics)}"
        )
    if not weak_topics and not forgotten_topics:
        lines.append(
            "\nNo weak areas identified — introduce new topics that build naturally on previous weeks."
        )
    lines.append(f"\nReturn exactly {days_in_week} days.")
    return "\n".join(lines)
