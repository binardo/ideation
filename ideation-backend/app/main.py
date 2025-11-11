from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
from openai import OpenAI
import asyncio
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

sessions = {}

class ProblemInput(BaseModel):
    problem: str

class ClarifyingAnswers(BaseModel):
    session_id: str
    answers: str

class ProblemStatementSelection(BaseModel):
    session_id: str
    problem_statement: str

class IdeaGenerationOptions(BaseModel):
    session_id: str
    persona: Optional[str] = None
    remove_constraints: bool = False
    add_constraints: bool = False
    custom_prompt: Optional[str] = None

class PrototypeRequest(BaseModel):
    session_id: str
    idea_ids: List[str]

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.post("/api/start-session")
async def start_session(input: ProblemInput):
    """Start a new ideation session and generate clarifying questions"""
    session_id = f"session_{len(sessions) + 1}"
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at helping people clarify their problems. Ask 3-5 insightful clarifying questions that will help understand the problem better and guide the ideation process. Be specific and thoughtful."},
                {"role": "user", "content": f"The user described their problem as: {input.problem}\n\nGenerate 3-5 clarifying questions to better understand their needs, constraints, target audience, and goals."}
            ],
            temperature=0.7
        )
        
        questions = response.choices[0].message.content
        
        sessions[session_id] = {
            "initial_problem": input.problem,
            "clarifying_questions": questions,
            "answers": None,
            "problem_statements": [],
            "selected_problem_statement": None,
            "ideas": [],
            "novel_ideas": [],
            "duplicate_ideas": []
        }
        
        return {
            "session_id": session_id,
            "questions": questions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/submit-answers")
async def submit_answers(input: ClarifyingAnswers):
    """Submit answers to clarifying questions and generate problem statements"""
    if input.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[input.session_id]
    session["answers"] = input.answers
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at formulating clear, actionable problem statements. Generate 4 distinct, well-specified problem statements that are open-ended and inspire creative solutions. Each should be 2-3 lines."},
                {"role": "user", "content": f"Initial problem: {session['initial_problem']}\n\nClarifying questions: {session['clarifying_questions']}\n\nUser's answers: {input.answers}\n\nGenerate 4 distinct problem statements (2-3 lines each) that capture different angles or aspects of this problem. Format each as a clear, open-ended statement that invites creative solutions."}
            ],
            temperature=0.8
        )
        
        statements_text = response.choices[0].message.content
        
        statements = []
        lines = statements_text.strip().split('\n')
        current_statement = []
        
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('*')):
                if current_statement:
                    statements.append(' '.join(current_statement))
                    current_statement = []
                cleaned = line.lstrip('0123456789.-*) ').strip()
                if cleaned:
                    current_statement.append(cleaned)
            elif line and current_statement:
                current_statement.append(line)
        
        if current_statement:
            statements.append(' '.join(current_statement))
        
        if len(statements) < 4:
            statements.extend([""] * (4 - len(statements)))
        statements = statements[:4]
        
        session["problem_statements"] = statements
        
        return {
            "problem_statements": statements
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/select-problem-statement")
async def select_problem_statement(input: ProblemStatementSelection):
    """Select a problem statement and start idea generation"""
    if input.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[input.session_id]
    session["selected_problem_statement"] = input.problem_statement
    session["ideas"] = []
    session["novel_ideas"] = []
    session["duplicate_ideas"] = []
    
    return {"status": "ready", "problem_statement": input.problem_statement}

@app.post("/api/generate-idea")
async def generate_idea(session_id: str, include_existing: bool = False, prompt_variation: int = 0):
    """Generate a single idea"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    problem_statement = session["selected_problem_statement"]
    
    prompts = [
        "Generate a creative and novel solution to this problem. Think outside the box.",
        "Approach this problem from a completely different angle. What's an unconventional solution?",
        "Think about how technology could solve this problem in an innovative way.",
        "Consider a simple, elegant solution that others might overlook.",
        "What would a radical, disruptive solution look like for this problem?"
    ]
    
    base_prompt = prompts[prompt_variation % len(prompts)]
    
    existing_ideas_text = ""
    if include_existing and session["novel_ideas"]:
        ideas_list = [f"- {idea['title']}: {idea['description']}" for idea in session["novel_ideas"][:10]]
        existing_ideas_text = f"\n\nExisting ideas (generate something DIFFERENT from these):\n" + "\n".join(ideas_list)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": f"You are a creative ideation expert. {base_prompt} Provide your response in this exact format:\nTitle: [Short catchy title]\nDescription: [2-3 lines describing how the idea would work]"},
                {"role": "user", "content": f"Problem statement: {problem_statement}{existing_ideas_text}\n\nGenerate ONE novel idea."}
            ],
            temperature=0.9
        )
        
        idea_text = response.choices[0].message.content.strip()
        
        lines = idea_text.split('\n')
        title = ""
        description = ""
        
        for line in lines:
            if line.startswith("Title:"):
                title = line.replace("Title:", "").strip()
            elif line.startswith("Description:"):
                description = line.replace("Description:", "").strip()
            elif description and line.strip():
                description += " " + line.strip()
        
        if not title:
            title = idea_text.split('\n')[0][:50]
        if not description:
            description = idea_text
        
        idea = {
            "id": f"idea_{len(session['ideas']) + 1}",
            "title": title,
            "description": description,
            "full_text": idea_text
        }
        
        session["ideas"].append(idea)
        
        return idea
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/check-uniqueness")
async def check_uniqueness(session_id: str, idea_id: str):
    """Check if an idea is unique compared to existing novel ideas"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    idea = next((i for i in session["ideas"] if i["id"] == idea_id), None)
    
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    
    if not session["novel_ideas"]:
        session["novel_ideas"].append(idea)
        return {"is_unique": True, "similar_to": None}
    
    try:
        existing_ideas_text = "\n".join([
            f"{i+1}. {idea['title']}: {idea['description']}" 
            for i, idea in enumerate(session["novel_ideas"])
        ])
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at comparing ideas. Determine if a new idea is substantially different from existing ideas or if it's very similar to one of them. Respond with 'UNIQUE' if it's different, or 'SIMILAR: [number]' if it's very similar to one of the existing ideas (provide the number)."},
                {"role": "user", "content": f"Existing ideas:\n{existing_ideas_text}\n\nNew idea:\n{idea['title']}: {idea['description']}\n\nIs this new idea unique or similar to an existing one?"}
            ],
            temperature=0.3
        )
        
        result = response.choices[0].message.content.strip().upper()
        
        if "UNIQUE" in result:
            session["novel_ideas"].append(idea)
            return {"is_unique": True, "similar_to": None}
        else:
            similar_idx = None
            for word in result.split():
                if word.isdigit():
                    similar_idx = int(word) - 1
                    break
            
            if similar_idx is not None and 0 <= similar_idx < len(session["novel_ideas"]):
                similar_idea = session["novel_ideas"][similar_idx]
                session["duplicate_ideas"].append({
                    "idea": idea,
                    "similar_to": similar_idea["id"]
                })
                return {"is_unique": False, "similar_to": similar_idea["id"]}
            else:
                session["novel_ideas"].append(idea)
                return {"is_unique": True, "similar_to": None}
    except Exception as e:
        session["novel_ideas"].append(idea)
        return {"is_unique": True, "similar_to": None}

@app.get("/api/session-status/{session_id}")
async def get_session_status(session_id: str):
    """Get the current status of idea generation"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    total_ideas = len(session["ideas"])
    novel_count = len(session["novel_ideas"])
    duplicate_count = len(session["duplicate_ideas"])
    
    should_stop = False
    if total_ideas > 10:
        duplicate_percentage = (duplicate_count / total_ideas) * 100
        should_stop = duplicate_percentage >= 75
    
    return {
        "total_ideas": total_ideas,
        "novel_ideas": novel_count,
        "duplicate_ideas": duplicate_count,
        "should_stop": should_stop,
        "novel_ideas_list": session["novel_ideas"],
        "duplicate_ideas_list": session["duplicate_ideas"]
    }

@app.post("/api/generate-more-ideas")
async def generate_more_ideas(input: IdeaGenerationOptions):
    """Trigger generation of more ideas with specific options"""
    if input.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[input.session_id]
    session["generation_options"] = {
        "persona": input.persona,
        "remove_constraints": input.remove_constraints,
        "add_constraints": input.add_constraints,
        "custom_prompt": input.custom_prompt
    }
    
    return {"status": "ready"}

@app.post("/api/update-idea")
async def update_idea(session_id: str, idea_id: str, title: str, description: str):
    """Update an idea's title and description"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    for idea in session["novel_ideas"]:
        if idea["id"] == idea_id:
            idea["title"] = title
            idea["description"] = description
            return {"status": "updated"}
    
    raise HTTPException(status_code=404, detail="Idea not found")

@app.post("/api/delete-idea")
async def delete_idea(session_id: str, idea_id: str):
    """Delete an idea"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    session["novel_ideas"] = [i for i in session["novel_ideas"] if i["id"] != idea_id]
    
    return {"status": "deleted"}

@app.post("/api/add-idea")
async def add_idea(session_id: str, title: str, description: str):
    """Add a new custom idea"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    idea = {
        "id": f"idea_custom_{len(session['novel_ideas']) + 1}",
        "title": title,
        "description": description,
        "full_text": f"{title}: {description}"
    }
    
    session["novel_ideas"].append(idea)
    
    return idea

@app.post("/api/like-idea")
async def like_idea(session_id: str, idea_id: str):
    """Toggle like on an idea"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    for idea in session["novel_ideas"]:
        if idea["id"] == idea_id:
            idea["liked"] = not idea.get("liked", False)
            return {"status": "toggled", "liked": idea["liked"]}
    
    raise HTTPException(status_code=404, detail="Idea not found")

@app.post("/api/generate-prototypes")
async def generate_prototypes(input: PrototypeRequest):
    """Generate prototype HTML apps for selected ideas"""
    if input.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[input.session_id]
    prototypes = []
    
    for idea_id in input.idea_ids:
        idea = next((i for i in session["novel_ideas"] if i["id"] == idea_id), None)
        if not idea:
            continue
        
        try:
            specs_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert product designer. Generate 3 distinct app specifications for implementing this idea. Each spec should describe a different approach to the user interface and interaction model. Be specific about features and user flow."},
                    {"role": "user", "content": f"Idea: {idea['title']}\nDescription: {idea['description']}\n\nGenerate 3 distinct app specifications, each with a different UI/UX approach."}
                ],
                temperature=0.8
            )
            
            specs_text = specs_response.choices[0].message.content
            
            specs = []
            current_spec = []
            for line in specs_text.split('\n'):
                if line.strip() and (line.strip()[0].isdigit() or line.strip().startswith('Spec')):
                    if current_spec:
                        specs.append('\n'.join(current_spec))
                    current_spec = [line]
                elif line.strip() and current_spec:
                    current_spec.append(line)
            if current_spec:
                specs.append('\n'.join(current_spec))
            
            idea_prototypes = []
            for i, spec in enumerate(specs[:3]):
                html_response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are an expert web developer. Create a complete, interactive single-page HTML application with inline CSS and JavaScript. Use modern, clean design with dummy data. Make it fully functional and interactive. Include multiple UI pages/views within the single HTML file using JavaScript to show/hide sections. Use Tailwind CSS via CDN for styling."},
                        {"role": "user", "content": f"Idea: {idea['title']}\nDescription: {idea['description']}\n\nApp Specification:\n{spec}\n\nCreate a complete, interactive HTML application that demonstrates this idea with dummy data and multiple views/pages. Make it visually appealing and fully functional."}
                    ],
                    temperature=0.7
                )
                
                html_content = html_response.choices[0].message.content
                
                if "```html" in html_content:
                    html_content = html_content.split("```html")[1].split("```")[0].strip()
                elif "```" in html_content:
                    html_content = html_content.split("```")[1].split("```")[0].strip()
                
                idea_prototypes.append({
                    "spec_number": i + 1,
                    "spec": spec,
                    "html": html_content
                })
            
            prototypes.append({
                "idea_id": idea_id,
                "idea_title": idea["title"],
                "prototypes": idea_prototypes
            })
            
        except Exception as e:
            print(f"Error generating prototype for {idea_id}: {e}")
            continue
    
    session["prototypes"] = prototypes
    
    return {"prototypes": prototypes}

@app.get("/api/get-prototypes/{session_id}")
async def get_prototypes(session_id: str):
    """Get generated prototypes for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    return {"prototypes": session.get("prototypes", [])}
