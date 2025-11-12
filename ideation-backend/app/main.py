from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
from openai import OpenAI
import asyncio
from dotenv import load_dotenv
import uuid

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
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

sessions = {}
session_locks = {}

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
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are an innovation specialist helping a team work on a problem. Your role is to help them reframe and analyze their problem, which can shift their focus, enable them to view the problem from different angles, and encourage creative thinking. Ask 3-5 insightful clarifying questions that will help understand the problem better, identify stakeholders, current approaches, goals, resources, and constraints."},
                {"role": "user", "content": f"The user described their problem as: {input.problem}\n\nAsk 3-5 follow-up questions to better understand:\n- The specific topic or challenge\n- Key stakeholders or audience affected\n- Current approaches and their limitations\n- Goals and desired outcomes\n- Resources and constraints"}
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
            "duplicate_ideas": [],
            "generation_active": False,
            "inflight": 0,
            "generation_task": None
        }
        session_locks[session_id] = asyncio.Lock()
        
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
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are an expert at reframing problems to enable creative thinking. Generate 4 distinct problem statements that focus on real results, not particular methods. Frame them as quick, punchy, open-ended questions starting with 'How might we' or 'How can we'. Each should be 2-3 lines that inspire creative solutions from different angles."},
                {"role": "user", "content": f"Initial problem: {session['initial_problem']}\n\nClarifying questions: {session['clarifying_questions']}\n\nUser's answers: {input.answers}\n\nGenerate 4 distinct 'How might we' or 'How can we' questions (2-3 lines each) that reframe this problem from different perspectives. Focus on the real end goal, not specific methods. Make them open-ended to encourage diverse solutions."}
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

async def run_generation(session_id: str):
    """Background task to generate ideas concurrently"""
    if session_id not in sessions:
        return
    
    session = sessions[session_id]
    lock = session_locks[session_id]
    
    try:
        prompt_index = 0
        max_concurrent = 5
        
        while session.get("generation_active", False):
            tasks = []
            for i in range(max_concurrent):
                include_existing = (prompt_index % 2 == 0)
                variation = prompt_index % 5
                tasks.append(generate_single_idea_background(session_id, include_existing, variation, lock))
                prompt_index += 1
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            async with lock:
                total_ideas = len(session["ideas"])
                novel_count = len(session["novel_ideas"])
                duplicate_count = len(session["duplicate_ideas"])
                
                should_stop = False
                if novel_count >= 20:
                    should_stop = True
                elif total_ideas >= 30:
                    duplicate_percentage = (duplicate_count / total_ideas) * 100
                    if duplicate_percentage >= 60:
                        should_stop = True
                
                if should_stop:
                    session["generation_active"] = False
                    break
            
            await asyncio.sleep(0.5)
    except Exception as e:
        print(f"Error in generation task: {e}")
    finally:
        async with lock:
            session["generation_active"] = False

async def generate_single_idea_background(session_id: str, include_existing: bool, variation: int, lock: asyncio.Lock):
    """Generate a single idea in the background"""
    try:
        session = sessions[session_id]
        problem_statement = session["selected_problem_statement"]
        
        prompts = [
            "Generate a creative and novel solution to this problem. Think outside the box and diverge hard from conventional approaches.",
            "Approach this problem from a completely different angle. What's an unconventional solution that challenges assumptions?",
            "Think about how technology could solve this problem in an innovative way. Consider emerging technologies and future possibilities.",
            "Consider a simple, elegant solution that others might overlook. Focus on minimalism and user experience.",
            "What would a radical, disruptive solution look like for this problem? Think about complete paradigm shifts.",
            "How might we solve this if cost was no object? Dream big and think ambitiously.",
            "What if we had to solve this with zero technology? Focus on human-centered, low-tech approaches.",
            "How would a child approach this problem? Think playfully and creatively without constraints.",
            "Invert the problem: what if we did the exact opposite of the obvious solution? How could that work?",
            "Remove a core assumption: what if one fundamental constraint didn't exist? How would that change the solution?",
            "Domain transfer: how would this problem be solved in a completely different industry or field? Apply that approach here.",
            "Time-shift: imagine solving this problem 50 years in the future with advanced technology. What would that look like?",
            "Extreme user perspective: how would someone with very different needs (astronaut, child, elderly person) solve this?",
            "Combine random elements: merge two completely unrelated concepts to create a novel hybrid solution.",
            "First principles: break the problem down to fundamental truths and rebuild the solution from scratch.",
            "Constraint flip: what if we had to solve this with the opposite resources (more time but less money, or vice versa)?"
        ]
        
        base_prompt = prompts[variation % len(prompts)]
        
        existing_ideas_text = ""
        anti_similarity_text = ""
        if include_existing:
            async with lock:
                if session["novel_ideas"]:
                    import random
                    novel_sample = random.sample(session["novel_ideas"], min(7, len(session["novel_ideas"])))
                    ideas_list = [f"- {idea['title']}: {idea['description']}" for idea in novel_sample]
                    existing_ideas_text = f"\n\nExisting ideas (generate something DIFFERENT from these):\n" + "\n".join(ideas_list)
                    
                    if len(session["novel_ideas"]) >= 5:
                        themes = [idea['title'].split(':')[0] for idea in session["novel_ideas"][:5]]
                        anti_similarity_text = f"\n\nAvoid these themes and approaches: {', '.join(themes)}. Diverge significantly from these directions."
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": f"You are a creative ideation expert. {base_prompt} Provide your response in this exact format:\nTitle: [Short catchy title]\nDescription: [2-3 lines describing how the idea would work]"},
                {"role": "user", "content": f"Problem statement: {problem_statement}{existing_ideas_text}{anti_similarity_text}\n\nGenerate ONE novel idea that is substantially different from existing ideas."}
            ],
            temperature=1.1,
            top_p=0.9
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
        
        idea_id = str(uuid.uuid4())
        idea = {
            "id": idea_id,
            "title": title,
            "description": description,
            "full_text": idea_text
        }
        
        async with lock:
            session["ideas"].append(idea)
        
        await check_uniqueness_background(session_id, idea_id, lock)
        
    except Exception as e:
        print(f"Error generating idea: {e}")
    finally:
        async with lock:
            session["inflight"] = max(0, session.get("inflight", 1) - 1)

async def check_uniqueness_background(session_id: str, idea_id: str, lock: asyncio.Lock):
    """Check if an idea is unique in the background"""
    try:
        session = sessions[session_id]
        
        async with lock:
            idea = next((i for i in session["ideas"] if i["id"] == idea_id), None)
            if not idea:
                return
            
            if not session["novel_ideas"]:
                session["novel_ideas"].append(idea)
                return
            
            existing_ideas_text = "\n".join([
                f"{i+1}. {idea['title']}: {idea['description']}" 
                for i, idea in enumerate(session["novel_ideas"])
            ])
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are an expert at comparing ideas. Rate the similarity between a new idea and existing ideas on a scale of 0-100, where 0 means completely different and 100 means identical. Respond with ONLY a number between 0-100, followed by a colon and the number of the most similar existing idea (if similarity >= 65). Format: 'SCORE: [number]' or 'SCORE: [number], SIMILAR_TO: [idea_number]'"},
                {"role": "user", "content": f"Existing ideas:\n{existing_ideas_text}\n\nNew idea:\n{idea['title']}: {idea['description']}\n\nRate the similarity (0-100) and identify the most similar existing idea if score >= 65."}
            ],
            temperature=0.2,
            top_p=0.2
        )
        
        result = response.choices[0].message.content.strip()
        
        similarity_score = 0
        similar_idx = None
        
        try:
            if "SCORE:" in result.upper():
                score_part = result.upper().split("SCORE:")[1].split(",")[0].strip()
                similarity_score = int(''.join(filter(str.isdigit, score_part)))
            
            if "SIMILAR_TO:" in result.upper():
                similar_part = result.upper().split("SIMILAR_TO:")[1].strip()
                similar_idx = int(''.join(filter(str.isdigit, similar_part))) - 1
        except (ValueError, IndexError):
            similarity_score = 0
        
        async with lock:
            if similarity_score >= 80 and similar_idx is not None and 0 <= similar_idx < len(session["novel_ideas"]):
                similar_idea = session["novel_ideas"][similar_idx]
                session["duplicate_ideas"].append({
                    "idea": idea,
                    "similar_to": similar_idea["id"],
                    "similarity_score": similarity_score
                })
            else:
                if similarity_score >= 65 and similar_idx is not None and 0 <= similar_idx < len(session["novel_ideas"]):
                    idea["similar_to"] = session["novel_ideas"][similar_idx]["id"]
                    idea["similarity_score"] = similarity_score
                session["novel_ideas"].append(idea)
    except Exception as e:
        print(f"Error checking uniqueness: {e}")
        async with lock:
            session["novel_ideas"].append(idea)

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
    session["generation_active"] = True
    session["inflight"] = 5
    
    task = asyncio.create_task(run_generation(input.session_id))
    session["generation_task"] = task
    
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
            model=MODEL,
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
            model=MODEL,
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
    lock = session_locks.get(session_id)
    
    if lock:
        async with lock:
            total_ideas = len(session["ideas"])
            novel_count = len(session["novel_ideas"])
            duplicate_count = len(session["duplicate_ideas"])
            inflight = session.get("inflight", 0)
            generation_active = session.get("generation_active", False)
    else:
        total_ideas = len(session["ideas"])
        novel_count = len(session["novel_ideas"])
        duplicate_count = len(session["duplicate_ideas"])
        inflight = session.get("inflight", 0)
        generation_active = session.get("generation_active", False)
    
    should_stop = False
    duplicate_percentage = 0
    if total_ideas > 10:
        duplicate_percentage = (duplicate_count / total_ideas) * 100
        should_stop = duplicate_percentage >= 75
    
    return {
        "total_ideas": total_ideas,
        "novel_ideas": novel_count,
        "duplicate_ideas": duplicate_count,
        "should_stop": should_stop,
        "inflight": inflight,
        "generation_active": generation_active,
        "duplicate_percentage": duplicate_percentage,
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
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert product designer and UX strategist. Generate 3 distinct, professional app specifications for implementing this idea. Each spec should describe a completely different approach to the user interface, interaction model, and user experience. Focus on creating diverse, innovative UX patterns that differentiate each prototype. Be specific about features, user flows, visual design approach, and interaction patterns."},
                    {"role": "user", "content": f"Idea: {idea['title']}\nDescription: {idea['description']}\n\nGenerate 3 distinct app specifications with significantly different UX approaches:\n1. First spec: Focus on one UX paradigm (e.g., dashboard-based, card-based, timeline-based)\n2. Second spec: Use a completely different interaction model (e.g., conversational, gesture-based, wizard-flow)\n3. Third spec: Explore an alternative visual and navigation approach (e.g., minimal, data-rich, gamified)\n\nFor each spec, describe the visual design, key features, user flow, and what makes it unique."}
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
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": "You are an expert web developer and UI designer. Create a complete, professional, slick single-page HTML application with inline CSS and JavaScript. The app must be visually stunning with smooth animations, transitions, and moments of joy. Use modern design principles with Tailwind CSS via CDN for styling. Include hover effects, fade-in animations, smooth transitions between views, and micro-interactions. Make it fully functional and interactive with realistic dummy data. The UI should feel polished and production-ready with attention to spacing, typography, colors, and visual hierarchy."},
                        {"role": "user", "content": f"Idea: {idea['title']}\nDescription: {idea['description']}\n\nApp Specification:\n{spec}\n\nCreate a complete, professional, slick HTML application that:\n- Implements the specification with high fidelity\n- Uses smooth animations and transitions (CSS transitions, fade-ins, slide-ins)\n- Has polished UI with proper spacing, typography, and visual hierarchy\n- Includes multiple views/pages with smooth navigation\n- Uses realistic dummy data that demonstrates the concept\n- Has hover effects and micro-interactions for delight\n- Feels production-ready and professional\n\nMake it visually stunning and a pleasure to use."}
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
