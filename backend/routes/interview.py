from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from agents.interview_agent import (
    generate_first_question,
    generate_next_question,
    evaluate_answer,
    generate_overall_feedback,
    GeminiQuotaExceededError
)
from firebase_admin import firestore
import asyncio
from auth import get_current_user_data
from datetime import datetime
import re

db = firestore.client()
router = APIRouter(prefix="/interview", tags=["Interview Flow"])

class InterviewRequest(BaseModel):
    role: str
    experience: str
    num_questions: int

class AnswerRequest(BaseModel):
    interview_id: str
    question_text: str
    answer_text: str

@router.post('/start')
async def start_interview(data: InterviewRequest, user_data: dict = Depends(get_current_user_data)):
    print(f"[DEBUG] Incoming data: role='{data.role}' experience='{data.experience}' num_questions='{data.num_questions}'")
    user_uid = user_data['uid']
    user_email = user_data['email']

    try:
        active_query = db.collection('interviews') \
            .where('user_uid', '==', user_uid) \
            .where('is_active', '==', True)
        active_docs = await asyncio.to_thread(active_query.stream)
        for doc in active_docs:
            await asyncio.to_thread(doc.reference.update, {"is_active": False, 'ended_at': datetime.utcnow()})

        first_question = await generate_first_question(data.role, data.experience)
        interview_data = {
            "user_uid": user_uid,
            "user_email": user_email,
            "role": data.role,
            "experience": data.experience,
            "num_questions": data.num_questions,
            "questions": [{
                "text": first_question,
                "timestamp": datetime.utcnow().isoformat(),
                "from_ai": True
            }],
            "answers": [],
            "evaluation": [],
            "is_active": True,
            "created_at": firestore.SERVER_TIMESTAMP
        }

        doc_ref = await asyncio.to_thread(lambda: db.collection('interviews').add(interview_data)[1])
        return {
            "message": "Interview started successfully",
            "interview_id": doc_ref.id,
            "first_question": first_question
        }
    except Exception as e:
        print(f"[ERROR] Interview creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/answer')
async def submit_answer(data: AnswerRequest, user_data: dict = Depends(get_current_user_data)):
    user_uid = user_data['uid']
    interview_ref = db.collection('interviews').document(data.interview_id)

    try:
        interview_doc = await asyncio.to_thread(interview_ref.get)
        if not interview_doc.exists:
            raise HTTPException(status_code=404, detail="Interview not found.")

        interview_data = interview_doc.to_dict()
        if interview_data.get('user_uid') != user_uid or not interview_data.get('is_active'):
            raise HTTPException(status_code=403, detail="Unauthorized or inactive interview.")

        questions = interview_data.get('questions', [])
        answers = interview_data.get('answers', [])
        evaluations = interview_data.get('evaluation', [])
        num_questions = interview_data.get('num_questions', 10)

        updated_answers = answers + [{
            "text": data.answer_text,
            "timestamp": datetime.utcnow().isoformat(),
            "from_ai": False
        }]

        # Evaluate the answer and store the result
        evaluation_feedback = await evaluate_answer(
            interview_data['role'],
            interview_data['experience'],
            data.question_text,
            data.answer_text
        )
        updated_evaluations = evaluations + [{
            "question": data.question_text,
            "answer": data.answer_text,
            "score": evaluation_feedback.get("score"),
            "reason": evaluation_feedback.get("reason"),
            "confidence": evaluation_feedback.get("confidence"),
            "red_flag": evaluation_feedback.get("red_flag"),
            "timestamp": datetime.utcnow().isoformat()
        }]

        # If all questions answered, do not generate next question, just update answers and evaluations
        if len(updated_answers) >= num_questions:
            await asyncio.to_thread(interview_ref.update, {
                "answers": updated_answers,
                "evaluation": updated_evaluations,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            return {
                "message": "Interview completed.",
                "next_question": None,
                "evaluation_feedback": evaluation_feedback
            }

        # Otherwise, generate next question
        # Prepare conversation history for next question
        conversation_history = []
        for i in range(len(questions)):
            conversation_history.append({"role": "model", "parts": [{"text": questions[i].get("text", "")}]})
            if i < len(answers):
                conversation_history.append({"role": "user", "parts": [{"text": answers[i].get("text", "")}]})
        conversation_history.append({"role": "user", "parts": [{"text": data.answer_text}]})

        next_question = await generate_next_question(
            interview_data['role'],
            interview_data['experience'],
            conversation_history
        )

        updated_questions = questions + [{
            "text": next_question,
            "timestamp": datetime.utcnow().isoformat(),
            "from_ai": True
        }]
        await asyncio.to_thread(interview_ref.update, {
            "answers": updated_answers,
            "evaluation": updated_evaluations,
            "questions": updated_questions,
            "updated_at": firestore.SERVER_TIMESTAMP
        })

        return {
            "message": "Answer submitted and next question generated successfully",
            "next_question": next_question,
            "evaluation_feedback": evaluation_feedback
        }

    except Exception as e:
        print(f"[ERROR] Error in /answer: {e}")
        raise HTTPException(status_code=500, detail="Something went wrong.")


@router.post("/next")
async def get_next_question_safeguarded(request: Request, user_data: dict = Depends(get_current_user_data)):
    # This route should not be used unless for manual testing
    data = await request.json()
    interview_id = data.get("interview_id")
    user_uid = user_data['uid']

    interview_ref = db.collection('interviews').document(interview_id)
    interview_doc = await asyncio.to_thread(interview_ref.get)
    if not interview_doc.exists:
        raise HTTPException(status_code=404, detail="Interview not found.")

    interview_data = interview_doc.to_dict()
    if interview_data.get('user_uid') != user_uid or not interview_data.get('is_active'):
        raise HTTPException(status_code=403, detail="Unauthorized or inactive interview.")

    questions = interview_data.get('questions', [])
    answers = interview_data.get('answers', [])
    num_questions = interview_data.get('num_questions', 10)

    if len(questions) >= num_questions:
        raise HTTPException(status_code=400, detail="Question limit reached. Interview already completed.")

    return {"message": "Manual next route should not be used in normal flow."}

@router.post('/end')
async def end_interview(request: Request, user_data: dict = Depends(get_current_user_data)):
    data = await request.json()
    interview_id = data.get("interview_id")
    user_uid = user_data['uid']
    interview_ref = db.collection('interviews').document(interview_id)
    interview_doc = await asyncio.to_thread(interview_ref.get)
    if not interview_doc.exists:
        raise HTTPException(status_code=404, detail="Interview not found.")
    interview_data = interview_doc.to_dict()
    if interview_data.get('user_uid') != user_uid:
        raise HTTPException(status_code=403, detail="Not authorized to end this interview.")
    await asyncio.to_thread(interview_ref.update, {
        'is_active': False,
        'ended_at': datetime.utcnow(),
        'updated_at': firestore.SERVER_TIMESTAMP
    })
    return {"message": "Interview marked as completed and inactive."}

@router.post("/overall-feedback")
async def overall_feedback(request: Request, user_data: dict = Depends(get_current_user_data)):
    data = await request.json()
    interview_id = data.get("interview_id")
    user_uid = user_data['uid']
    interview_ref = db.collection('interviews').document(interview_id)
    interview_doc = await asyncio.to_thread(interview_ref.get)
    if not interview_doc.exists:
        raise HTTPException(status_code=404, detail="Interview not found.")
    interview_data = interview_doc.to_dict()
    if interview_data.get('user_uid') != user_uid:
        raise HTTPException(status_code=403, detail="Not authorized to get feedback for this interview.")

    # Only use real questions, answers, and evaluations
    questions = interview_data.get('questions', [])
    answers = interview_data.get('answers', [])
    evaluations = interview_data.get('evaluation', [])
    num_answered = min(len(questions), len(answers), len(evaluations))
    feedback_input = {
        "role": interview_data.get('role', 'N/A'),
        "experience": interview_data.get('experience', 'N/A'),
        "questions": []
    }
    per_question_scores = []
    questions_array = []
    for i in range(num_answered):
        score = evaluations[i].get('score')
        per_question_scores.append(score)
        feedback_input['questions'].append({
            "question": questions[i].get('text', 'N/A'),
            "user_answer": answers[i].get('text', 'N/A'),
            "score": score,
            "score_reason": evaluations[i].get('reason'),
            "confidence": evaluations[i].get('confidence'),
            "red_flag": evaluations[i].get('red_flag')
        })
        questions_array.append({
            "question": questions[i].get('text', 'N/A'),
            "user_answer": answers[i].get('text', 'N/A'),
            "score": score
        })

    # Calculate average score
    if per_question_scores:
        avg_score = round(sum(per_question_scores) / len(per_question_scores), 1)
    else:
        avg_score = 0.0

    raw_feedback_text = await asyncio.to_thread(generate_overall_feedback, feedback_input)

    # Mark interview as inactive and set ended_at if not already
    if interview_data.get('is_active', True):
        await asyncio.to_thread(interview_ref.update, {
            'is_active': False,
            'ended_at': datetime.utcnow(),
            'overall_feedback': raw_feedback_text,
            'updated_at': firestore.SERVER_TIMESTAMP
        })
    else:
        await asyncio.to_thread(interview_ref.update, {
            'overall_feedback': raw_feedback_text,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

    return {
        "final_score": avg_score,
        "per_question_scores": per_question_scores,
        "overall_feedback": raw_feedback_text,
        "questions": questions_array
    }