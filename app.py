import os
import json
import uuid
import base64
from typing import Dict, List, Optional
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import google.generativeai as genai

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")

genai.configure(api_key=GEMINI_API_KEY)

# Initialize FastAPI app
app = FastAPI(title="Interview Practice Partner")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory session storage
sessions: Dict[str, dict] = {}

# Pydantic models for request/response
class StartInterviewRequest(BaseModel):
    role: str
    experience_level: str
    company_type: Optional[str] = "general"
    resume_text: Optional[str] = None

class AnswerRequest(BaseModel):
    session_id: str
    answer: str

class EndInterviewRequest(BaseModel):
    session_id: str

# Enhanced Prompt templates with human-like conversation
INTERVIEWER_SYSTEM_PROMPT = """You are an experienced professional interviewer named Alex conducting a {role} interview for a {experience_level} candidate at a {company_type} company.

YOUR PERSONALITY & STYLE:
- You're friendly yet professional, creating a comfortable atmosphere
- You listen actively and show genuine interest in the candidate's experiences
- You ask follow-up questions naturally, like a real conversation
- You occasionally share brief context or acknowledge good points (e.g., "That's interesting..." or "I see...")
- You vary your question style: sometimes direct, sometimes exploratory
- You don't sound robotic or use overly formal language

INTERVIEW APPROACH:
1. Ask ONE question at a time - keep it conversational (1-3 sentences)
2. Build on what the candidate just said - reference specific things they mentioned
3. Mix question types naturally:
   - Deep dives: "You mentioned X - can you walk me through how you approached that?"
   - Clarifications: "When you say Y, do you mean...?"
   - Challenges: "What would you do differently if you faced that situation again?"
   - Scenario-based: "How would you handle [specific situation]?"
4. Occasionally acknowledge their answers before asking the next question
   - "That makes sense. Now, let me ask you about..."
   - "Interesting approach. I'm curious though..."
   - "Got it. Building on that..."

{resume_context}

FOCUS AREAS FOR {role}:
{focus_areas}

CURRENT STAGE: Question {question_number} of approximately 8-10 questions

REMEMBER: You're having a conversation, not conducting an interrogation. Be human, be curious, be engaged.
"""

RESUME_CONTEXT_TEMPLATE = """
CANDIDATE'S RESUME HIGHLIGHTS:
{resume_summary}

USE THIS INFORMATION TO:
- Ask specific questions about projects, technologies, or experiences mentioned in their resume
- Probe deeper into achievements they've listed
- Ask for concrete examples from their work history
- Challenge claims or explore gaps tactfully
- Connect their background to the role they're interviewing for

Reference their resume naturally in your questions when relevant.
"""

FOCUS_AREAS = {
    "Software Engineer / SDE": """
- Problem-solving: Ask about algorithms, data structures, and how they think through technical challenges
- System design: For mid/senior, explore architecture decisions and scalability
- Code quality: Discuss testing, code review practices, debugging approaches
- Past projects: Deep dive into their most complex or proud projects
- Technologies: Discuss specific tools/frameworks they've used and why
- Collaboration: How they work with other engineers and cross-functional teams
- Learning: How they stay current and approach learning new technologies""",
    
    "Data Analyst / Data Scientist": """
- Analytical thinking: How they approach data problems and extract insights
- Technical skills: SQL, Python/R, statistical methods they've applied
- Data storytelling: How they communicate findings to non-technical stakeholders
- Tools & platforms: Experience with visualization tools, databases, ML frameworks
- Business impact: Examples of data-driven decisions they've influenced
- Methodology: Their approach to cleaning, analyzing, and validating data
- Curiosity: How they identify questions worth investigating""",
    
    "Sales / Business Development": """
- Sales approach: Their methodology and how they build relationships
- Objection handling: Real examples of difficult conversations and how they handled them
- Negotiation: Specific deals they've closed and the strategies used
- Metrics & achievement: Quota attainment, biggest wins, what drives their success
- Prospecting: How they identify and qualify leads
- Relationship building: Long-term client management approach
- Resilience: How they handle rejection and maintain motivation""",
    
    "Retail Associate / Customer Support": """
- Customer service philosophy: What great service means to them
- Conflict resolution: Specific examples of handling difficult customers
- Product knowledge: How they learn and share product information
- Teamwork: Working with colleagues during busy periods
- Problem-solving: Creative solutions they've found for customer issues
- Multitasking: Managing multiple priorities in fast-paced environments
- Empathy: Understanding and addressing customer needs"""
}

FEEDBACK_SYSTEM_PROMPT = """You are an expert interview coach named Sarah who provides constructive, specific feedback.

INTERVIEW DETAILS:
Role: {role}
Experience Level: {experience_level}
{resume_note}

CONVERSATION TRANSCRIPT:
{transcript}

PROVIDE COMPREHENSIVE FEEDBACK in the following JSON format:
{{
    "overall_score": <1-10, be honest but fair>,
    "dimension_scores": {{
        "communication_clarity": <1-10, how clearly they expressed ideas>,
        "confidence_structure": <1-10, answer organization and delivery confidence>,
        "technical_knowledge": <1-10, depth of expertise for the role>,
        "role_specific_skills": <1-10, skills unique to this position>
    }},
    "strengths": [
        "Specific strength with concrete example: 'When discussing [topic], you effectively demonstrated [skill] by [specific thing they said]'",
        "Another strength with example",
        "2-4 strengths total"
    ],
    "areas_to_improve": [
        "Specific improvement with actionable advice: 'When asked about [topic], your answer could be stronger by [specific suggestion]. For example, you could have [concrete example]'",
        "Another area with actionable steps",
        "2-4 areas total"
    ],
    "improved_answers": [
        {{
            "original_question": "The actual question asked",
            "their_answer": "What they actually said (keep it under 100 words)",
            "improved_answer": "A better version that addresses the same question with more structure/detail/clarity. Show them HOW to answer better."
        }},
        {{
            "original_question": "Another question they struggled with",
            "their_answer": "Their response",
            "improved_answer": "Enhanced version"
        }}
    ]
}}

EVALUATION GUIDELINES:
- Be honest but encouraging - this is practice, not a real interview
- Reference SPECIFIC things they said, not generic observations
- Score relative to the {experience_level} level expected
- If they referenced resume items well, acknowledge that
- If they were vague, note where they could have been more specific
- Highlight both what worked AND what would make them stand out more

Focus on actionable feedback that will genuinely help them improve."""

def get_gemini_model():
    """Initialize Gemini model"""
    return genai.GenerativeModel('gemini-2.5-flash')

def extract_resume_text(file_content: bytes, filename: str) -> str:
    """Extract text from uploaded resume (PDF or plain text)"""
    try:
        if filename.lower().endswith('.pdf'):
            # Use Gemini to extract text from PDF
            model = get_gemini_model()
            
            # Convert to base64
            import base64
            pdf_base64 = base64.b64encode(file_content).decode('utf-8')
            
            prompt = """Extract all text content from this resume/CV. 
            
Format the output to include:
- Contact information
- Work experience (with dates, roles, companies)
- Education
- Skills
- Projects
- Any other relevant sections

Keep the formatting clean and structured."""

            response = model.generate_content([
                {
                    "mime_type": "application/pdf",
                    "data": pdf_base64
                },
                prompt
            ])
            
            return response.text
        else:
            # Plain text file
            return file_content.decode('utf-8')
    except Exception as e:
        print(f"Error extracting resume: {e}")
        return ""

def analyze_resume_for_interview(resume_text: str, role: str) -> str:
    """Analyze resume and extract key points for interview"""
    if not resume_text or not resume_text.strip():
        return ""
    
    model = get_gemini_model()
    
    prompt = f"""Analyze this resume for a {role} interview. Extract key points that an interviewer should probe:

Resume:
{resume_text}

Provide a concise summary (150-200 words) covering:
1. Most relevant experiences for this {role} role
2. Key skills and technologies mentioned
3. Notable projects or achievements
4. Potential areas to explore deeper
5. Any gaps or points that need clarification

Format as a bullet-point summary that an interviewer can quickly reference."""
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error analyzing resume: {e}")
        return f"Resume uploaded - candidate has experience relevant to {role}"

def generate_initial_question(role: str, experience_level: str, company_type: str, resume_summary: str = "") -> str:
    """Generate the first interview question"""
    model = get_gemini_model()
    
    focus = FOCUS_AREAS.get(role, "General professional competencies")
    
    resume_context = ""
    if resume_summary:
        resume_context = f"\n\nCANDIDATE'S BACKGROUND:\n{resume_summary}\n\nConsider their background when crafting your opening question."
    
    prompt = f"""You're Alex, starting an interview for a {role} position ({experience_level} level) at a {company_type} company.
{resume_context}

Generate a natural, engaging opening question. Options:
1. If they have a resume: Ask about a specific project or experience from their background
2. Classic opener with a twist: "Walk me through your journey into {role} - what sparked your interest?"
3. Recent work: "Tell me about the most interesting {role}-related project you've worked on recently"

Choose the most appropriate approach. Keep it conversational and welcoming (2-3 sentences max).

Return ONLY the question, nothing else."""
    
    response = model.generate_content(prompt)
    return response.text.strip()

def generate_followup_question(role: str, experience_level: str, company_type: str, 
                               conversation_history: List[dict], question_number: int,
                               resume_summary: str = "") -> str:
    """Generate a follow-up question based on conversation history"""
    model = get_gemini_model()
    
    focus = FOCUS_AREAS.get(role, "General professional competencies")
    
    # Build conversation context
    conversation_text = ""
    for turn in conversation_history[-3:]:  # Last 3 exchanges for context
        conversation_text += f"Alex: {turn['question']}\n"
        conversation_text += f"Candidate: {turn['answer']}\n\n"
    
    resume_context_section = ""
    if resume_summary:
        resume_context_section = RESUME_CONTEXT_TEMPLATE.format(resume_summary=resume_summary)
    
    system_prompt = INTERVIEWER_SYSTEM_PROMPT.format(
        role=role,
        experience_level=experience_level,
        company_type=company_type,
        focus_areas=focus,
        question_number=question_number,
        resume_context=resume_context_section
    )
    
    prompt = f"""{system_prompt}

RECENT CONVERSATION:
{conversation_text}

Based on their last answer, generate your next question. Consider:
- What they just said - any interesting points to explore?
- What haven't you asked about yet from the focus areas?
- Should you dig deeper or move to a new topic?
- If they were vague, can you ask for a specific example?
- Around question {question_number}, consider gradually increasing depth

Your response should feel natural, like you're genuinely interested in their answer.

Return ONLY your next question (1-3 sentences), nothing else."""
    
    response = model.generate_content(prompt)
    return response.text.strip()

def generate_feedback(role: str, experience_level: str, conversation_history: List[dict], resume_summary: str = "") -> dict:
    """Generate comprehensive interview feedback"""
    model = get_gemini_model()
    
    # Build full transcript
    transcript = ""
    for i, turn in enumerate(conversation_history, 1):
        transcript += f"Question {i}: {turn['question']}\n"
        transcript += f"Answer {i}: {turn['answer']}\n\n"
    
    resume_note = ""
    if resume_summary:
        resume_note = f"Note: Candidate provided a resume. Consider whether they effectively referenced their background."
    
    prompt = FEEDBACK_SYSTEM_PROMPT.format(
        role=role,
        experience_level=experience_level,
        transcript=transcript,
        resume_note=resume_note
    )
    
    response = model.generate_content(prompt)
    
    # Parse JSON response
    try:
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        feedback = json.loads(response_text)
        return feedback
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print(f"Response text: {response_text}")
        # Fallback
        return {
            "overall_score": 7,
            "dimension_scores": {
                "communication_clarity": 7,
                "confidence_structure": 7,
                "technical_knowledge": 7,
                "role_specific_skills": 7
            },
            "strengths": ["Completed the interview and provided thoughtful responses"],
            "areas_to_improve": ["Unable to generate detailed feedback - please try again"],
            "improved_answers": []
        }

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render home page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/interview/{session_id}", response_class=HTMLResponse)
async def interview_page(request: Request, session_id: str):
    """Render interview page"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return templates.TemplateResponse("interview.html", {
        "request": request,
        "session_id": session_id
    })

@app.get("/feedback/{session_id}", response_class=HTMLResponse)
async def feedback_page(request: Request, session_id: str):
    """Render feedback page"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    if not session.get("feedback"):
        raise HTTPException(status_code=400, detail="Interview not completed")
    
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "session_id": session_id,
        "feedback": session["feedback"]
    })

@app.post("/api/start-interview")
async def start_interview(
    role: str = Form(...),
    experience_level: str = Form(...),
    company_type: str = Form("general"),
    resume: Optional[UploadFile] = File(None)
):
    """Start a new interview session"""
    session_id = str(uuid.uuid4())
    
    # Process resume if uploaded
    resume_text = ""
    resume_summary = ""
    if resume:
        try:
            content = await resume.read()
            resume_text = extract_resume_text(content, resume.filename)
            if resume_text:
                resume_summary = analyze_resume_for_interview(resume_text, role)
        except Exception as e:
            print(f"Error processing resume: {e}")
    
    # Generate first question
    first_question = generate_initial_question(
        role,
        experience_level,
        company_type,
        resume_summary
    )
    
    # Create session
    sessions[session_id] = {
        "role": role,
        "experience_level": experience_level,
        "company_type": company_type,
        "resume_text": resume_text,
        "resume_summary": resume_summary,
        "conversation_history": [],
        "current_question": first_question,
        "question_count": 1,
        "feedback": None
    }
    
    return {
        "session_id": session_id,
        "question": first_question
    }

@app.post("/api/submit-answer")
async def submit_answer(request: AnswerRequest):
    """Submit an answer and get next question"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[request.session_id]
    
    # Store the Q&A pair
    session["conversation_history"].append({
        "question": session["current_question"],
        "answer": request.answer
    })
    
    # Generate next question
    session["question_count"] += 1
    next_question = generate_followup_question(
        session["role"],
        session["experience_level"],
        session["company_type"],
        session["conversation_history"],
        session["question_count"],
        session.get("resume_summary", "")
    )
    
    session["current_question"] = next_question
    
    return {
        "question": next_question,
        "question_number": session["question_count"]
    }

@app.post("/api/end-interview")
async def end_interview(request: EndInterviewRequest):
    """End interview and generate feedback"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[request.session_id]
    
    if not session["conversation_history"]:
        raise HTTPException(status_code=400, detail="No answers to evaluate")
    
    # Generate feedback
    feedback = generate_feedback(
        session["role"],
        session["experience_level"],
        session["conversation_history"],
        session.get("resume_summary", "")
    )
    
    session["feedback"] = feedback
    
    return {
        "feedback": feedback,
        "redirect_url": f"/feedback/{request.session_id}"
    }

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get session data"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return sessions[session_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)