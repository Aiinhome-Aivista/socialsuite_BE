"""Content generation use-cases (captions, hashtags, suggestions)."""
from app.services.ai.mistral import mistral
from app.services.ai.vector_store import query_brand_context

PLATFORM_HINTS = {
    "x": "Keep it under 280 characters. Punchy, witty, and conversational. Use a strong hook.",
    "linkedin": "Professional and insightful tone. Use clear spacing. Start with a thought-provoking statement and end with a question to drive comments. No excessive emojis.",
    "instagram": "Warm, trendy, and highly visual. Start with a catchy hook. Use bullet points or spacing for readability. Always include emojis. End with a clear Call to Action (CTA).",
    "facebook": "Friendly, relatable, and community-oriented. Medium length. Encourage tags and shares.",
    "youtube": "Write a highly engaging and SEO-optimized video description. Include a hook, a summary, and clear calls to action (subscribe, like).",
    "pinterest": "Keyword-rich, inspirational, and aesthetic. Describe the visual clearly and include a CTA to save or click the link.",
}


def generate_caption(org_id: int, brief: str, platform: str, tone: str = "friendly") -> str:
    context = query_brand_context(org_id, brief, k=4)
    context_block = "\n".join(f"- {c}" for c in context) if context else "None on file."
    system = (
        "You are an elite, highly-paid social media copywriter and marketing strategist. "
        "Your goal is to write highly engaging, structured, and viral-worthy content. "
        "Match the brand voice from the provided context. "
        "Output ONLY the caption text. Do not include any introductory or concluding remarks."
    )
    user = (
        f"Brand voice / past examples:\n{context_block}\n\n"
        f"Platform: {platform}\n"
        f"Platform Rules: {PLATFORM_HINTS.get(platform, '')}\n"
        f"Desired tone: {tone}\n"
        f"Brief: {brief}\n\n"
        "Requirements:\n"
        "1. Start with an attention-grabbing hook.\n"
        "2. Keep the body structured and easy to read.\n"
        "3. End with a strong Call to Action (CTA).\n\n"
        "Write the caption now:"
    )
    return mistral.chat(system, user, temperature=0.7)


def generate_hashtags(brief: str, platform: str, count: int = 10) -> list[str]:
    system = (
        "You are an SEO and Social Media Hashtag Expert. "
        "Generate highly relevant, trendy, and searchable hashtags. "
        "Output ONLY a comma-separated list of hashtags. No extra text, no bullet points."
    )
    user = f"Topic: {brief}\nPlatform: {platform}\nGive exactly {count} highly effective hashtags. Mix broad and niche tags."
    raw = mistral.chat(system, user, temperature=0.6, max_tokens=200)
    tags = [t.strip().lstrip("#") for t in raw.replace("\n", ",").split(",")]
    return ["#" + t for t in tags if t][:count]


def generate_ideas(org_id: int, topic: str, n: int = 5) -> list[str]:
    context = query_brand_context(org_id, topic, k=3)
    ctx = "\n".join(f"- {c}" for c in context) if context else "None."
    system = "You are a content strategist. Output a numbered list of post ideas only."
    user = f"Brand context:\n{ctx}\n\nTopic: {topic}\nGive {n} distinct post ideas."
    raw = mistral.chat(system, user, temperature=0.9)
    ideas = [line.lstrip("0123456789.).- ").strip() for line in raw.splitlines() if line.strip()]
    return [i for i in ideas if i][:n]
