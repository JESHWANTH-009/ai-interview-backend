import os
from dotenv import load_dotenv
import google.generativeai as genai
import json
import re

load_dotenv()

# Load API key properly
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Instantiate the model correctly
model = genai.GenerativeModel("gemini-2.0-flash")

class GeminiQuotaExceededError(Exception):
    """Raised when Gemini API quota is exceeded."""
    pass


# Extract text helper
def extract_text_from_response(response) -> str:
    try:
        if hasattr(response, 'text') and response.text:
            return response.text.strip()
        elif hasattr(response, 'parts') and response.parts:
            return response.parts[0].text.strip()
    except Exception as e:
        print(f"[ERROR] extract_text_from_response failed: {e}")
    return "Failed to extract valid response text from Gemini."


#Generate first question
async def generate_first_question(role: str, experience: str) -> str:
    prompt = (
        f"You are an AI Interview Coach specializing in {role} roles. "
        f"The candidate has {experience} of experience. "
        "Start the interview by asking a relevant first question. "
        "Keep the question concise and professional. Do not include any greetings or conversational fillers, just the question itself. "
        "Example: Tell me about your experience with Python development. "
        f"Candidate: {role}, Experience: {experience}. "
        "First question:"
    )
    try:
        response = await model.generate_content_async(prompt)
        return extract_text_from_response(response)
    except Exception as e:
        print(f"[ERROR] generate_first_question failed: {e}")
        return "Failed to generate the first question. Please try again later."


# Generate next question
async def generate_next_question(role: str, experience: str, conversation_history: list[dict]) -> str:
    instruction = (
        f"You are an AI Interview Coach specializing in {role} roles. "
        f"The candidate has {experience} of experience. "
        "Based on the conversation so far, ask a relevant and challenging next question. "
        "Do not greet the candidate or provide any feedback on their previous answer. "
        "Just ask the next question directly. If the interview seems complete, ask a concluding question or suggest ending."
    )
    try:
        chat = model.start_chat(history=conversation_history)
        response = await chat.send_message_async(instruction + "\n\nWhat is the next question?")
        return extract_text_from_response(response)
    except Exception as e:
        print(f"[ERROR] generate_next_question failed: {e}")
        return "Failed to generate the next question. Please try again later."


#Evaluate candidate's answer
def clean_json_block(text: str) -> str:
    if text.startswith("```json") or text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text)
        text = text.replace("```", "").strip()
    return text
SCORING_RUBRIC_V1 = {
    0: "Invalid / Copy-paste / Gibberish / Off-topic",
    1: "Extremely poor understanding or no structure",
    2: "Extremely poor understanding or no structure",
    3: "Extremely poor understanding or no structure",
    4: "Some relevance, lacks depth, major missing points",
    5: "Some relevance, lacks depth, major missing points",
    6: "Mostly correct with minor gaps or shallow explanations",
    7: "Mostly correct with minor gaps or shallow explanations",
    8: "Strong, clear answer with good structure, few small misses",
    9: "Strong, clear answer with good structure, few small misses",
    10: "Perfect, complete, well-structured and insightful answer"
}


STRICT_SYSTEM_PROMPT = (
    "You are an AI Interview Evaluator. Your job is to score technical answers (0–10 scale) using a strict, standardized rubric. "
    "You must provide accurate, fair, and explainable feedback.\n\n"
    "Your evaluation must avoid hallucination, be grounded only in the content of the answer, and must follow the definitions below.\n\n"
    "---\n\n"
    "Scoring Rubric Definitions:\n"
    "- 0 – Invalid / Irrelevant: Copied from question, Gibberish, Off-topic, Very short (under 10 words), No attempt to solve or address the question\n"
    "- 1 to 3 – Poor Answer: Lacks technical accuracy or understanding, Vague/generic, Missing key concepts, Just buzzwords\n"
    "- 4 to 5 – Shallow / Basic: Correct ideas but little detail, Misses edge cases, Poor structure, Uses terms but no explanation\n"
    "- 6 to 7 – Mostly Correct: Technically correct, Minor inaccuracies, Lacks depth/examples, Not fully structured\n"
    "- 8 to 9 – Strong: Technically sound, Good depth/clarity, Well-structured, Uses examples, Minor polish issues\n"
    "- 10 – Excellent/Expert: Complete, deep, clearly structured, Anticipates trade-offs, Demonstrates expertise, Explains with examples\n\n"
    "---\n\n"
    "Validation Rules:\n"
    "- If the answer is 80%+ similar to the question → score = 0\n"
    "- If irrelevant or off-topic → score = 0\n"
    "- If answer is too short (e.g., 'This is useful in frontend') → score = 1\n\n"
    "---\n\n"
    "Confidence Level Rules:\n"
    "- High: Answer is clearly relevant, technically correct, and well structured. AI detects 2 or more specific technical concepts used correctly. The structure is logical and shows applied understanding.\n"
    "- Medium: Answer is mostly relevant and partially correct. May lack full depth or structure. At least 1 valid concept or keyword is used correctly.\n"
    "- Low: Answer is vague, generic, off-topic, copied, or very short. AI cannot verify if the user truly understands the concept. No clear examples or reasoning are given.\n"
    "Never output 'High Confidence' if the answer is under 15 words or too generic.\n\n"
    "---\n\n"
    "ANTI-HALLUCINATION RULES:\n"
    "- Only evaluate based on the user's actual answer text.\n"
    "- Do not assume intent or infer unstated details.\n"
    "- If uncertain, lower the confidence or score accordingly.\n"
    "- Do not fabricate technologies, tools, projects, or explanations not explicitly mentioned.\n"
    "- Avoid over-praising or making assumptions about user expertise.\n"
    "- Never guess what the user *meant* — only respond to what they *said*.\n\n"
    "---\n\n"
    "Required Output:\n"
    "1. Score (0–10): Strictly follow rubric\n"
    "2. Reason for Score: Explain in ≤ 120 words\n"
    "3. Confidence Level: Low | Medium | High\n"
    "4. Red Flag Note (if any): Note if user copied question, gave generic buzzwords, or was off-topic\n\n"
    "You must be consistent across all responses. Do not guess user intent. Do not reward fluff. Focus on clarity, correctness, and completeness."
)

# === MAIN EVALUATION FUNCTION WITH STRICT RUBRIC AND GUARDRAILS (UPDATED) ===
async def evaluate_answer(role: str, experience: str, question: str, answer: str) -> dict:
    prompt = f"""
{STRICT_SYSTEM_PROMPT}

INPUT:
- Role: {role}
- Experience: {experience}
- Question: {question}
- Candidate's Answer: {answer}

OUTPUT (valid JSON only, no markdown):
{{
  "score": <integer 0-10>,
  "reason": "<≤120 words explanation for the score>",
  "confidence": "Low|Medium|High",
  "red_flag": "<note if copied, generic, or off-topic, else empty>"
}}
"""
    try:
        response = await model.generate_content_async(prompt)
        text = extract_text_from_response(response)
        cleaned_text = clean_json_block(text)
        feedback_dict = json.loads(cleaned_text)
        feedback_dict['score'] = int(feedback_dict.get('score', 0))
        return feedback_dict
    except json.JSONDecodeError as jde:
        print(f"[ERROR] JSON parsing failed: {jde} | Response: {text}")
        return {
            "score": 0,
            "reason": "Invalid response format from Gemini.",
            "confidence": "Low",
            "red_flag": "Invalid response format."
        }
    except Exception as e:
        print(f"[ERROR] evaluate_answer failed: {e}")
        return {
            "score": 0,
            "reason": f"Evaluation failed: {e}",
            "confidence": "Low",
            "red_flag": "Internal error occurred."
        }

def generate_overall_feedback(interview_data: dict) -> str:
    if not interview_data.get("questions"):
        return "No questions were answered during this interview."

    # Build a transcript for the AI to reference
    transcript = []
    per_question_scores_md = []
    for i, qa in enumerate(interview_data.get("questions", [])):
        transcript.append(f"Q{i+1}: {qa.get('question')}")
        answer = qa.get('user_answer', '').strip()
        if not answer or answer.lower() in ["n/a", "none", "", "-"]:
            transcript.append("Answer: (No answer provided)")
        else:
            transcript.append(f"Answer: {answer}")
        if qa.get('score') is not None:
            score = qa.get('score')
            reason = qa.get('score_reason', '')
            per_question_scores_md.append(f"- Q{i+1} Score: {score}/10" + (f" — {reason}" if reason else ""))
        if qa.get('evaluation_feedback'):
            transcript.append(f"Feedback: {qa.get('evaluation_feedback')}")
        transcript.append("")

    # Calculate average score for display
    scores = [qa.get('score') for qa in interview_data.get('questions', []) if qa.get('score') is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    prompt = f"""
You are an AI Interview Coach. Your job is to help candidates learn and grow after a technical interview. Your feedback should be supportive, educational, and motivating—like a mentor or coach, not a hiring manager.

Strictly base your feedback only on the actual answers and feedback provided below. Do not make assumptions or hallucinate details. If an answer was blank or invalid, mention it supportively and encourage the candidate to answer fully next time.

---

INTERVIEW CONTEXT:
Role: {interview_data.get('role', 'N/A')}
Experience: {interview_data.get('experience', 'N/A')}

TRANSCRIPT:
{chr(10).join(transcript)}

---

Please provide a markdown-formatted summary with the following sections:

**Summary of Your Interview Performance** (brief, encouraging tone)
**Your Strengths**
**Areas You Can Improve**
**What to Study Next**
**Final Score: {avg_score}/10** (based on accuracy, depth, clarity)
**Confidence in Feedback: High / Medium / Low**
**Recommended Next Steps** (study topics, practice tips)

**Per-Question Scores:**
{chr(10).join(per_question_scores_md)}

- Do NOT use language about hiring, rejection, or job decisions.
- Do NOT invent strengths/weaknesses not present in the answers.
- If the first answer was blank or invalid, say: "The first answer didn't provide enough information to assess your understanding. Make sure to write clearly and completely."
- Be positive, actionable, and focused on learning.
"""
    try:
        response = model.generate_content(prompt)
        return extract_text_from_response(response)
    except Exception as e:
        print(f"[ERROR] generate_overall_feedback failed: {e}")
        return "Failed to generate overall feedback due to an internal error."
