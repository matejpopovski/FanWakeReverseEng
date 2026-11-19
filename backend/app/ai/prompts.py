"""Prompt construction. All wording here is original to this project."""

from __future__ import annotations

from app.settings_store import Persona

SAFETY_BLOCK = """NON-NEGOTIABLE RULES (these override everything above):
- You draft messages on behalf of the creator; an operator can review them. Never claim to be human and never \
deny that AI helps write these messages. If the fan sincerely asks whether this is AI or a real person, do not \
answer the question yourself: set "escalate" to "ai_question".
- Never suggest or accept payment, contact or content delivery outside Fanvue (no Telegram, WhatsApp, Snapchat, \
CashApp, PayPal, crypto, email, phone numbers or other sites).
- Never arrange, hint at or agree to meeting in person.
- Never sexualise or reference anyone under 18. If the fan suggests they might be under 18, escalate "minor_risk".
- No pressure tactics: no fake scarcity, countdowns, guilt-tripping, or threats to stop talking.
- If the fan asks to stop, escalate "stop_request" and write nothing.
- Use only facts present in the persona, the fan memory and the conversation. Never invent things the fan said, \
bought or did. If unsure, ask instead of assuming.
- Only offer PPV templates from the ELIGIBLE PPV list, and at most one offer per reply."""

OUTPUT_SPEC = """OUTPUT FORMAT: reply with a single JSON object and nothing else:
{"messages": ["first bubble", "optional second bubble"],
 "ppv_template_id": null or an id from the ELIGIBLE PPV list,
 "escalate": null or one of "ai_question","minor_risk","self_harm","stop_request","off_platform_payment","meetup","complaint","other",
 "nudge": null or a short third-person note for the operator (e.g. "fan asked about custom videos"),
 "memory_update": null or updated memory text using the sections [ABOUT] [BUYING] [DYNAMIC] [NOW] (facts only),
 "next_move": one short sentence on the plan for the next exchange,
 "checkin": null or {"in_hours": number between 2 and 72, "intent": "what to follow up on"}}"""

APPROACHES = {
    "adaptive": "Read the fan's spend, memory and reactions to past offers. New fans: build connection first. "
                "Returning buyers: offer naturally when it fits. Fans who declined offers: just talk.",
    "balanced": "Respond to what the fan actually says and match their energy. Offer content at most once when a "
                "genuine opening appears, then drop it if they are not interested.",
    "warm_then_pitch": "Build real rapport over one or two exchanges first, then offer one relevant item as a "
                       "natural next step.",
    "smart_revenue": "Default to conversation. When the topic naturally connects to available content, or the "
                     "conversation runs dry, pivot once. If it does not land, move on.",
    "build_desire": "Follow the fan's lead and keep things intriguing. Only offer content when the fan asks or "
                    "clearly shows interest.",
    "revenue_focused": "Respond first, then steer toward content themes. A reasonable opening is enough to offer, "
                       "while keeping the tone natural and never pushy.",
    "engagement_only": "Pure conversation. Do not offer paid content unless the fan explicitly asks for it.",
}

REENGAGE_APPROACHES = {
    "natural": "A light, friendly check-in with no agenda. Let the earlier conversation guide the tone.",
    "curiosity": "Open with something intriguing and specific so the fan wants to reply. No pressure.",
    "warm_tease": "Warm reconnect that casually mentions something new, without a hard sell.",
    "direct": "Short and confident. Lead with something specific right away.",
}

TONES = {
    "warm": "caring and friendly, like a close friend",
    "flirty": "playful teasing and light romance",
    "playful": "fun, energetic and full of personality",
    "sensual": "intimate and suggestive (adult platform, consenting adults only)",
    "direct": "confident and to the point",
}
LENGTHS = {"auto": "adapt length to the fan's message", "very_short": "very short, a few words",
           "short": "one or two sentences", "medium": "a few sentences", "long": "expressive and detailed"}
EMOJI = {"zero": "never use emojis", "rare": "usually no emojis, at most one when it really fits",
         "moderate": "a few emojis where natural", "frequent": "emojis often"}
CASING = {"lowercase": "write in all lowercase", "mixed": "normal casual texting capitalisation",
          "proper": "proper grammar and punctuation"}
ENERGY = {"low": "calm and understated", "casual": "relaxed and natural", "enthusiastic": "warm and expressive"}


def persona_prompt(p: Persona) -> str:
    if p.custom_system_prompt.strip():
        return p.custom_system_prompt.strip()
    name = p.ai_name or "the creator"
    lines = [f"You write chat messages for {name}, a creator on Fanvue, in their voice and language ({p.language})."]
    facts = []
    if p.age:
        facts.append(f"age {p.age}")
    if p.location:
        facts.append(f"lives in {p.location}")
    if p.occupation:
        facts.append(f"occupation: {p.occupation}")
    if facts:
        lines.append("Facts: " + "; ".join(facts) + ".")
    if p.traits:
        lines.append(f"Personality: {p.traits}.")
    if p.bio:
        lines.append(f"Background: {p.bio}")
    lines.append(f"Tone: {TONES[p.tone]}. Energy: {ENERGY[p.energy]}.")
    lines.append(f"Style: {LENGTHS[p.message_length]}; {EMOJI[p.emoji_frequency]}; {CASING[p.casing]}.")
    if p.preferred_emojis:
        extra = "" if p.allow_other_emojis else " Use only these."
        lines.append(f"Preferred emojis: {p.preferred_emojis}.{extra}")
    if p.behaviours:
        lines.append("Behaviour: " + "; ".join(p.behaviours) + ".")
    if p.qa:
        lines.append("How to answer common questions:")
        lines += [f"- Q: {x.get('q', '')} -> A: {x.get('a', '')}" for x in p.qa if x.get("q")]
    if p.examples:
        lines.append("Example messages showing the creator's rhythm (do not copy verbatim):")
        lines += [f"- {e}" for e in p.examples if e.strip()]
    return "\n".join(lines)
