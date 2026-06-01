def system_prompt(days: int, hours: int) -> str:
    return (
        "You are an expert curriculum designer and career mentor. "
        "Create an in-depth, structured learning roadmap for the requested skill. "
        f"The total duration must be exactly {days} days with {hours} hours per day. "
        "Ensure daily tasks are specific, actionable, and progressively build depth. "
        "Return a JSON object with a single key 'months' containing an array of month objects. "
        "Each month object must have: month (integer), title (string), goal (string), "
        "and weeks (array of week objects). "
        "Each week object must have: week (integer), title (string), days_range (string), "
        "and daily_plan (array of day objects). "
        "Each day object must have: day (integer), topic (string), task (string)."
    )

def user_prompt(skill: str, days: int, hours: int) -> str:
    return (
        f"Create a comprehensive learning syllabus to master '{skill}'. "
        f"The plan must span exactly {days} days with {hours} hours per day. "
        "Return the complete roadmap as a JSON object with a 'months' array."
    )
