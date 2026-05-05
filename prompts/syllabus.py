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
