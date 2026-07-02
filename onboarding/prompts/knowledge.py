def knowledge_system_prompt() -> str:
    return (
        "You answer an employee's question using ONLY the company documentation "
        "excerpts provided. Ground every claim in the excerpts.\n\n"
        "Rules:\n"
        "- If the excerpts don't contain the answer, say you don't have that "
        "information in the company docs. Never invent facts.\n"
        "- Be concise and specific; prefer the company's own terms, repo names, "
        "and tools as they appear in the excerpts.\n"
        "- Do not mention that you were given excerpts; just answer."
    )

def knowledge_user_prompt(question: str, context: str) -> str:
    return (
        f"--- COMPANY DOCUMENTATION ---\n{context}\n--- END DOCUMENTATION ---\n\n"
        f"Question: {question}\n\n"
        f"Answer using only the documentation above."
    )
