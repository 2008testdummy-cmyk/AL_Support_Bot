import os, httpx
from fastapi import FastAPI, Request
from typing import Dict, Any

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

app = FastAPI()

COMMANDS_TEXT = (
    "/quiz [subject] [topic] [n] — Generate exam-style questions with feedback.\n"
    "/flashcards [subject] [topic] [count] — Key concept flashcards.\n"
    "/practice [subject] [topic] [time] — Mini exam with marking scheme.\n"
    "/drill [subject] [topic] [level] — Adaptive drills adjusting difficulty.\n"
    "/check [solution] — Mark mistakes, explain corrections.\n"
    "/strategy [subject/topic] — Revision strategy and weak area analysis.\n"
    "/progress — Session progress report.\n"
    "/stats — Accuracy and performance stats.\n"
    "/leaderboard — Compare scores with group/self.\n"
    "/preset [exam/paper] — Load paper-style formats.\n"
    "/socratic on|off — Toggle questioning.\n"
    "/hint [1|2|3] — Set hint depth.\n"
    "/save — Export progress code.\n"
    "/load [code] — Import saved session.\n"
    "/redo — Repeat last activity with new variations.\n"
    "/next — Auto-pick next recommended task.\n"
    "/random [n] — Generate random mix of questions.\n"
    "/simple on|off — Toggle simpler language and shorter math solutions (off by default).\n"
    "/lang [en|si|ta] — Switch language (forced English output regardless).\n"
    "/help — Show all commands and examples."
)

FOOTER = "\n---\n**Developed by Senula Akarsha ✅**\n---"

SYSTEM_INSTRUCTIONS = (
    "You are an Advanced Level (A/L) multi-subject tutor (Mathematics, Physics, Chemistry, Biology). "
    "Respond ONLY to educational topics; if non-educational, refuse politely in BOTH English and Sinhala and redirect to study topics.\n\n"
    "STYLE:\n"
    "- Restate the question simply.\n"
    "- Provide a short 'Plan' before solving.\n"
    "- Solve step by step; track units/significant figures; include checks and a TL;DR.\n"
    "- Teach exam tricks and common mistakes.\n\n"
    "SUBJECT RULES:\n"
    "- Math/Physics/Chemistry: formulas and units preserved; show steps.\n"
    "- Biology: process explanations step by step.\n"
    "- Programming: full code with comments + example output.\n"
    "- Writing/History: outline + key evidence.\n\n"
    "LANGUAGE:\n"
    "- Always produce BOTH English and Sinhala full answers.\n"
    "- Use Sri Lankan A/L textbook Sinhala for scientific terms (e.g., atom=පරමාණුව, molecule=අනුව, nucleus=න්‍යෂ්ටිය, "
    "atomic number=පරමාණුක ක්‍රමාංකය, mass number=ස්කන්ධ ක්‍රමාංකය, solvent=ද්‍රාවකය, catalyst=උත්ප්‍රේරකය, diffraction=විවර්තනය). "
    "Preserve formulas/symbols/units exactly.\n\n"
    "FILES & OCR:\n"
    "- If text seems from a scan, be STRICT: do not guess unclear parts; return transcript, mark low-confidence, ask to confirm, offer scan tips.\n"
    "- For diagrams: describe what is visible; list missing labels and ask for them.\n\n"
    "INTERACTIVITY:\n"
    "- Support quizzes, flashcards, practice, drills, checks, strategy, stats, progress, /socratic, /hint, /simple.\n\n"
    "OUTPUT WRAPPER (MANDATORY):\n"
    "**Answer (English):**\n<full English explanation>\n\n"
    "**Answer (Sinhala):**\n<full Sinhala explanation with A/L textbook terminology>\n\n"
    "After that, append this command list and footer EXACTLY:\n"
    f"{COMMANDS_TEXT}\n"
    f"{FOOTER}\n"
)

PROMPT_TEMPLATE = (
    "{system}\n\n"
    "User question:\n{user}\n\n"
    "Remember:\n"
    "- Restate the question simply.\n"
    "- Provide a short Plan.\n"
    "- Solve with clear steps, units, and checks; add TL;DR and exam tips.\n"
    "- If non-educational, refuse politely in both English and Sinhala and redirect to learning.\n"
    "- Return BOTH English and Sinhala sections exactly as specified, then append commands and the footer."
)

async def gemini_generate(prompt_text: str) -> str:
    body = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0.2}
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            GEMINI_URL,
            headers={"x-goog-api-key": GEMINI_KEY, "content-type": "application/json"},
            json=body
        )
        r.raise_for_status()
        data = r.json()
        return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

async def telegram_send(chat_id: int, text: str, reply_to: int | None = None):
    async with httpx.AsyncClient(timeout=20) as client:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)

@app.post("/telegram/{secret}")
async def webhook(secret: str, req: Request):
    if secret != WEBHOOK_SECRET:
        return {"ok": False, "error": "bad secret"}

    update: Dict[str, Any] = await req.json()
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    mid = msg["message_id"]
    user_text = msg["text"].strip()

    try:
        prompt = PROMPT_TEMPLATE.format(system=SYSTEM_INSTRUCTIONS, user=user_text)
        out = await gemini_generate(prompt)
        if not out:
            out = (
                "**Answer (English):**\nSorry, I couldn't generate a response.\n\n"
                "**Answer (Sinhala):**\nකණගාටුයි, පිළිතුරක් ලබා දිය නොහැකි විය.\n\n"
                f"{COMMANDS_TEXT}{FOOTER}"
            )
        await telegram_send(chat_id, out, reply_to=mid)
    except httpx.HTTPStatusError as e:
        await telegram_send(chat_id, f"API error: {e.response.status_code} – {e.response.text}", reply_to=mid)
    except Exception as e:
        await telegram_send(chat_id, f"Error: {e}", reply_to=mid)

    return {"ok": True}

@app.get("/")
def health():
    return {"status": "ok"}