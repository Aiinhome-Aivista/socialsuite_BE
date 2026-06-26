"""Content generation use-cases (captions, hashtags, suggestions)."""
import json
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
    try:
        return mistral.chat(system, user, temperature=0.7)
    except Exception as e:
        print(f"Failed to generate caption with AI: {e}")
        platform_lower = platform.lower() if platform else ""
        if platform_lower == "x":
            return f"Looking to elevate your approach? Here's the key: {brief}. Focus on what drives real impact. 🚀 #growth"
        elif platform_lower == "linkedin":
            return (
                f"Unlocking success with {brief} is all about strategy and execution.\n\n"
                "Here are three things to keep in mind:\n"
                "1️⃣ Clarity over complexity\n"
                "2️⃣ Focus on consistency\n"
                "3️⃣ Drive engagement through real discussions\n\n"
                "What are your thoughts on this? Let's discuss in the comments below!"
            )
        elif platform_lower == "instagram":
            return (
                f"✨ Ready to scale? Let's talk about: {brief}!\n\n"
                "Every post is an opportunity to connect and grow. Here is your reminder to keep creating, keep experimenting, and stay authentic. ❤️\n\n"
                "👇 Save this for later & tag a creator who needs to see this!"
            )
        elif platform_lower == "facebook":
            return (
                f"Let's dive into {brief} today! Community is at the heart of everything we do, and sharing these experiences helps us grow together.\n\n"
                "How do you handle this in your workspace? Share this post with your team!"
            )
        elif platform_lower == "youtube":
            return (
                f"In this video, we cover everything you need to know about {brief}.\n\n"
                "We break down practical strategies, workflows, and tools to help you succeed.\n\n"
                "🔔 Subscribe for more weekly updates, and hit the thumbs up if this helps!"
            )
        else:
            return f"Exploring {brief}. The best way to make progress is to start today! What is your biggest takeaway?"


def generate_hashtags(brief: str, platform: str, count: int = 10) -> list[str]:
    system = (
        "You are an SEO and Social Media Hashtag Expert. "
        "Generate highly relevant, trendy, and searchable hashtags. "
        "Output ONLY a comma-separated list of hashtags. No extra text, no bullet points."
    )
    user = f"Topic: {brief}\nPlatform: {platform}\nGive exactly {count} highly effective hashtags. Mix broad and niche tags."
    try:
        raw = mistral.chat(system, user, temperature=0.6, max_tokens=200)
        tags = [t.strip().lstrip("#") for t in raw.replace("\n", ",").split(",")]
        return ["#" + t for t in tags if t][:count]
    except Exception as e:
        print(f"Failed to generate hashtags with AI: {e}")
        words = [w.strip(".,!?;:()#").lower() for w in brief.split() if len(w) > 3] if brief else []
        words = [w for w in words if w.isalnum()]
        fallback_tags = words + ["socialmedia", "strategy", "growth", "marketing", platform.lower() if platform else "social"]
        seen = set()
        unique_tags = []
        for t in fallback_tags:
            if t not in seen:
                seen.add(t)
                unique_tags.append("#" + t)
        return unique_tags[:count]


def generate_ideas(org_id: int, topic: str, n: int = 5) -> list[str]:
    context = query_brand_context(org_id, topic, k=3)
    ctx = "\n".join(f"- {c}" for c in context) if context else "None."
    system = "You are a content strategist. Output a numbered list of post ideas only."
    user = f"Brand context:\n{ctx}\n\nTopic: {topic}\nGive {n} distinct post ideas."
    try:
        raw = mistral.chat(system, user, temperature=0.9)
        ideas = [line.lstrip("0123456789.).- ").strip() for line in raw.splitlines() if line.strip()]
        return [i for i in ideas if i][:n]
    except Exception as e:
        print(f"Failed to generate ideas with AI: {e}")
        return [
            f"Introduction to {topic or 'your topic'}: Key concepts & basic definitions.",
            f"Top 5 common mistakes to avoid when working with {topic or 'your topic'}.",
            f"A deep dive case study showcasing real-world results of {topic or 'your topic'}.",
            f"How to optimize your workflow when managing {topic or 'your topic'}.",
            f"The future of {topic or 'your topic'}: Trends and predictions to watch."
        ][:n]


def generate_analysis(platform: str, followers: int, likes: int, impressions: int, watch_time_seconds: int, demographics: dict) -> dict:
    system = (
        "You are an elite AI Social Media Growth Strategist and Brand Consultant.\n"
        "Your task is to analyze the performance metrics of a user's social media account and generate a highly custom, actionable, and data-driven growth strategy.\n"
        "You must return your output strictly in JSON format. Do not write any markdown wrappers (like ```json), introduction, or explanations outside the JSON structure.\n\n"
        "Expected JSON schema:\n"
        "{\n"
        "  \"healthScore\": <integer between 0 and 100 based on the metrics relative to typical performance metrics>,\n"
        "  \"overall\": \"<a 2-3 sentence sophisticated and analytical overview of their current growth state, platform presence, and core strategy>\",\n"
        "  \"improvements\": [\n"
        "    \"<actionable improvement point 1 with specific metrics/tactics>\",\n"
        "    \"<actionable improvement point 2 with specific metrics/tactics>\",\n"
        "    \"<actionable improvement point 3 with specific metrics/tactics>\"\n"
        "  ],\n"
        "  \"postIdea\": \"<a detailed, highly creative, and specific viral-worthy content idea for their next post, tailored to the platform>\",\n"
        "  \"bestTimeToPost\": \"<specific days and times, e.g. 'Tuesdays & Thursdays, 9:00 AM - 11:00 AM EST', optimized for this platform's audience>\"\n"
        "}"
    )

    user = (
        f"Please analyze the growth metrics for this account:\n"
        f"- Platform: {platform}\n"
        f"- Followers: {followers:,}\n"
        f"- Engagement (Likes/Interactions): {likes:,}\n"
        f"- Impressions/Reach: {impressions:,}\n"
        f"- Watch Time (seconds): {watch_time_seconds:,}\n"
        f"- Demographics Data: {json.dumps(demographics) if demographics else 'None'}\n\n"
        "Platform-specific context:\n"
        "Provide advanced, realistic recommendations. Avoid generic advice like 'post high quality content' or 'use hashtags'. Be highly specific, tactical, and copywriter-grade."
    )

    try:
        raw_response = mistral.chat(system, user, temperature=0.7, max_tokens=1000)

        # Remove code block formatting if present
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) > 2:
                cleaned = "\n".join(lines[1:-1])
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()

        data = json.loads(cleaned)
        # Validate structure
        required_keys = ["healthScore", "overall", "improvements", "postIdea", "bestTimeToPost"]
        for key in required_keys:
            if key not in data:
                raise KeyError(f"Missing required key: {key}")
        return data
    except Exception as e:
        print(f"Failed to generate or parse AI Analysis: {e}")
        # Generate simple fallback structured response
        return {
            "healthScore": 75,
            "overall": "The metrics show solid foundational engagement, but there is room for improvement in overall reach and consistent formatting across posts.",
            "improvements": [
                "Focus on platform-specific video formats (e.g. Reels/Shorts) to expand reach.",
                "Engage directly with community comments within the first hour of posting.",
                "Refine posting schedule based on active hours of your demographics."
            ],
            "postIdea": f"Create an interactive post sharing a key learning or industry insight that prompts user comments.",
            "bestTimeToPost": "Wednesdays at 11:30 AM EST"
        }
