def system_prompt() -> str:
    return (
        "You are a senior technical educator and blog writer. "
        "Write a detailed, beginner-friendly blog explaining the concept or task described. "
        "Focus on practical explanation, step-by-step instructions, examples, and insights. "
        "Return the response as clean HTML content with no CSS or extra metadata. "
        "While taking examples, make them relevant to the given skill and industry."
    )

def user_prompt(task_title: str, skill: str, task_description: str) -> str:
    return (
        f"Write a detailed blog about: {task_title}\n"
        f"Skill: {skill}\n"
        f"Task description: {task_description}"
    )
