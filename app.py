import base64
import html
import json

import anthropic
import streamlit as st

st.set_page_config(page_title="Exam Prep – Matric & Inter", page_icon="📘", layout="wide")

# ---------- Config ----------
MODELS = {
    "Fast & cheap (Haiku)": "claude-haiku-5-5",
    "Better quality (Sonnet)": "claude-sonnet-5-5",
}
LANGS = {
    "English": "English",
    "اردو (Urdu)": "Urdu, written in Urdu script",
    "Roman Urdu": "Roman Urdu (Urdu written in English letters, e.g. 'Yeh jawab sahi hai kyun ke...')",
}
MAX_MB = 30

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# Urdu needs right-to-left + a proper font
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu&display=swap');
    .urdu { direction: rtl; text-align: right; font-family: 'Noto Nastaliq Urdu', serif;
            font-size: 1.15rem; line-height: 2.3; }
    </style>
    """,
    unsafe_allow_html=True,
)


def show(text: str, lang_key: str):
    """Render text; right-to-left if Urdu script is selected."""
    if lang_key.startswith("اردو"):
        st.markdown(f'<div class="urdu">{html.escape(text)}</div>', unsafe_allow_html=True)
    else:
        st.markdown(text)


# ---------- Claude helpers ----------
def build_chapter_block(uploaded):
    data = uploaded.getvalue()
    name = uploaded.name.lower()
    if name.endswith(".pdf"):
        block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(data).decode()},
        }
    elif name.endswith((".png", ".jpg", ".jpeg")):
        mt = "image/png" if name.endswith(".png") else "image/jpeg"
        block = {
            "type": "image",
            "source": {"type": "base64", "media_type": mt,
                       "data": base64.standard_b64encode(data).decode()},
        }
    else:
        block = {"type": "text", "text": data.decode("utf-8", errors="ignore")}
    # Cache the chapter so generating + grading doesn't re-pay full price
    block["cache_control"] = {"type": "ephemeral"}
    return block


def ask_json(system, instruction, chapter, model, max_tokens=4000):
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user",
                   "content": [chapter, {"type": "text", "text": instruction}]}],
    )
    text = msg.content[0].text
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


SYSTEM = (
    "You are a patient exam-prep tutor for Pakistani board students (Matric / SSC and "
    "Intermediate / HSSC; Punjab, Federal, Sindh, KP, Balochistan boards). "
    "Use ONLY the chapter provided as your source of truth. Never add facts that are not "
    "in the chapter. Output valid JSON only, with no text outside the JSON."
)

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Settings")
    level = st.selectbox("Class", ["9th", "10th", "11th (1st year)", "12th (2nd year)"])
    subject = st.text_input("Subject", placeholder="e.g. Physics, Biology, Pak Studies")
    lang_key = st.radio("Explain answers in", list(LANGS.keys()))
    model_label = st.selectbox("Quality", list(MODELS.keys()))
    model = MODELS[model_label]

# ---------- Main ----------
st.title("📘 Exam Prep from Your Own Textbook")
st.caption("Upload a chapter → get practice questions → get marked against your book.")

uploaded = st.file_uploader(
    "Upload chapter (PDF, photo of pages, or .txt)", type=["pdf", "png", "jpg", "jpeg", "txt"]
)

if uploaded:
    if uploaded.size > MAX_MB * 1024 * 1024:
        st.error(f"File is too big. Please keep it under {MAX_MB} MB (try splitting the chapter).")
        st.stop()

    # New file => reset state
    if st.session_state.get("file_id") != (uploaded.name, uploaded.size):
        st.session_state.file_id = (uploaded.name, uploaded.size)
        st.session_state.chapter = build_chapter_block(uploaded)
        st.session_state.pop("questions", None)
        st.session_state.pop("results", None)

    c1, c2, c3, c4 = st.columns(4)
    n_mcq = c1.number_input("MCQs", 0, 15, 5)
    n_short = c2.number_input("Short questions", 0, 10, 3)
    n_long = c3.number_input("Long questions", 0, 5, 1)
    difficulty = c4.selectbox("Difficulty", ["Easy", "Medium", "Board-exam level", "Hard"], index=2)

    if st.button("✨ Generate questions", type="primary"):
        instruction = f"""
Class: {level}. Subject: {subject or 'as per chapter'}. Difficulty: {difficulty}.
Create {n_mcq} MCQs (4 options each), {n_short} short questions (2-3 line answers) and
{n_long} long questions (detailed answers), in the style of Pakistani board papers.
Write questions in the same language as the chapter.
Every question must be answerable from the chapter.

Return JSON:
{{"questions":[{{"id":1,"type":"mcq|short|long","question":"...",
"options":["...","...","...","..."],   // mcq only
"model_answer":"answer taken from the chapter","marks":1}}]}}
Marks: MCQ=1, short=2, long=5.
"""
        with st.spinner("Reading your chapter and writing questions..."):
            try:
                st.session_state.questions = ask_json(
                    SYSTEM, instruction, st.session_state.chapter, model)["questions"]
                st.session_state.pop("results", None)
            except Exception as e:
                st.error(f"Something went wrong: {e}")

# ---------- Quiz ----------
if st.session_state.get("questions"):
    st.divider()
    st.subheader("📝 Practice paper")
    questions = st.session_state.questions

    with st.form("quiz"):
        answers = {}
        for q in questions:
            st.markdown(f"**Q{q['id']}. ({q['marks']} mark{'s' if q['marks'] > 1 else ''})**")
            st.markdown(q["question"])
            key = f"ans_{q['id']}"
            if q["type"] == "mcq":
                answers[q["id"]] = st.radio("Choose one", q["options"], index=None,
                                            key=key, label_visibility="collapsed")
            else:
                h = 90 if q["type"] == "short" else 200
                answers[q["id"]] = st.text_area("Your answer", key=key, height=h,
                                                label_visibility="collapsed")
            st.write("")
        submitted = st.form_submit_button("✅ Check my answers", type="primary")

    if submitted:
        payload = [
            {"id": q["id"], "type": q["type"], "question": q["question"],
             "options": q.get("options"), "marks": q["marks"],
             "student_answer": answers.get(q["id"]) or "(no answer)"}
            for q in questions
        ]
        instruction = f"""
Mark these student answers strictly against the chapter.
{json.dumps(payload, ensure_ascii=False)}

Write ALL feedback text in: {LANGS[lang_key]}.
Keep technical terms/formulae in English where students would see them in the textbook.
Be encouraging but honest. Give partial marks for short/long answers.

Return JSON:
{{"results":[{{"id":1,"score":0,"max":1,"verdict":"correct|partly|incorrect",
"feedback":"what was right/wrong",
"correct_answer":"the correct answer per the chapter",
"explanation":"simple explanation of the concept",
"chapter_reference":"section/heading/page where this is in the chapter"}}],
"overall_comment":"short study advice"}}
"""
        with st.spinner("Checking against your chapter..."):
            try:
                st.session_state.results = ask_json(
                    SYSTEM, instruction, st.session_state.chapter, model, max_tokens=6000)
            except Exception as e:
                st.error(f"Something went wrong: {e}")

# ---------- Results ----------
if st.session_state.get("results"):
    res = st.session_state.results
    st.divider()
    total = sum(r["score"] for r in res["results"])
    maximum = sum(r["max"] for r in res["results"])
    st.subheader(f"🎯 Score: {total} / {maximum}")
    st.progress(total / maximum if maximum else 0)
    icons = {"correct": "✅", "partly": "🟡", "incorrect": "❌"}

    for r in res["results"]:
        q = next(x for x in st.session_state.questions if x["id"] == r["id"])
        with st.expander(f"{icons.get(r['verdict'], '•')} Q{r['id']} — {r['score']}/{r['max']}"):
            st.markdown(f"**Question:** {q['question']}")
            show(r["feedback"], lang_key)
            st.markdown("**Correct answer:**")
            show(r["correct_answer"], lang_key)
            st.markdown("**Explanation:**")
            show(r["explanation"], lang_key)
            st.caption(f"📖 In your chapter: {r['chapter_reference']}")

    st.info(res.get("overall_comment", ""))
    if st.button("🔁 New practice paper from same chapter"):
        st.session_state.pop("questions", None)
        st.session_state.pop("results", None)
        st.rerun()
