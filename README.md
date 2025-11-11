# Ideation Studio

A comprehensive web application for AI-powered ideation that guides users through a structured process of generating, refining, and prototyping innovative ideas using LLMs.

## Features

- **Stepped Progress Navigation**: Visual progress bar guiding users through 5 stages
- **Problem Clarification**: AI-generated clarifying questions to understand the problem better
- **Problem Statement Generation**: 4 AI-generated problem statements with editing capabilities
- **Concurrent Idea Generation**: Parallel LLM calls with uniqueness checking and diversity tracking
- **Novel Ideas Management**: Post-it note UI with like, edit, delete, and similar ideas features
- **Generate More Ideas**: Options to generate ideas from different personas or with/without constraints
- **Prototype Generation**: Automatically generates 3 interactive HTML prototypes for each selected idea
- **Polished UI**: Modern design with animations, gradients, and responsive interactions

## Architecture

### Backend (FastAPI)
- **Location**: `ideation-backend/`
- **Framework**: FastAPI with Python 3.12
- **Dependencies**: OpenAI API, UV for package management
- **API Endpoints**:
  - `/api/start-session` - Initialize ideation session with clarifying questions
  - `/api/submit-answers` - Generate problem statements from answers
  - `/api/select-problem-statement` - Start idea generation
  - `/api/generate-idea` - Generate single idea with variations
  - `/api/check-uniqueness` - Check if idea is unique using LLM
  - `/api/session-status` - Get current ideation progress
  - `/api/update-idea`, `/api/delete-idea`, `/api/like-idea` - Manage ideas
  - `/api/generate-prototypes` - Generate interactive HTML prototypes

### Frontend (React + Vite)
- **Location**: `ideation-frontend/`
- **Framework**: React 18 with TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui pre-installed
- **Icons**: Lucide React
- **Build Tool**: Vite

## Setup Instructions

### Prerequisites
- Python 3.12+
- Node.js 18+
- UV (for Python dependency management) - Install from https://docs.astral.sh/uv/
- OpenAI API key

### Backend Setup

1. Navigate to the backend directory:
```bash
cd ideation-backend
```

2. Create a `.env` file with your OpenAI API key:
```bash
echo "OPENAI_API_KEY=your_api_key_here" > .env
```

3. Install dependencies:
```bash
uv sync
```

4. Start the development server:
```bash
uv run fastapi dev app/main.py
```

The backend will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd ideation-frontend
```

2. Create a `.env` file with the backend URL:
```bash
echo "VITE_API_URL=http://localhost:8000" > .env
```

3. Install dependencies:
```bash
npm install
```

4. Start the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Usage

1. **Start**: Enter your problem or challenge in the initial text box
2. **Clarify**: Answer AI-generated clarifying questions about your problem
3. **Define**: Choose or edit one of 4 AI-generated problem statements
4. **Generate**: Watch as the system generates novel ideas with real-time progress tracking
5. **Refine**: Review, edit, like, and manage your novel ideas in a post-it note interface
6. **Prototype**: Select your favorite ideas and generate 3 interactive HTML prototypes for each

## Deployment

### Frontend
The frontend is deployed at: https://idea-ideation-app-zaz7ic2g.devinapps.com

To deploy your own:
```bash
cd ideation-frontend
npm run build
# Deploy the dist/ folder to your hosting service
```

### Backend
The backend requires:
- OpenAI API key set as environment variable
- Python 3.12+ runtime
- FastAPI deployment (Fly.io, Railway, Render, etc.)

**Note**: There's currently a Fly.io region deprecation issue. Consider using alternative deployment services or manually configuring a different region.

## Technology Stack

### Backend
- FastAPI - Modern Python web framework
- OpenAI API (gpt-4o) - LLM for idea generation and analysis
- Pydantic - Data validation
- Python-dotenv - Environment variable management
- In-memory storage - Session data (resets on restart)

### Frontend
- React 18 - UI framework
- TypeScript - Type safety
- Vite - Build tool and dev server
- Tailwind CSS - Utility-first styling
- shadcn/ui - Pre-built UI components
- Lucide React - Icon library

## API Model

The application uses OpenAI's `gpt-4o` model for all LLM interactions:
- Clarifying questions generation
- Problem statement formulation
- Idea generation with prompt variations
- Uniqueness checking between ideas
- Prototype specification and HTML generation

## Development Notes

- **In-Memory Storage**: Session data is stored in memory and will be lost on server restart
- **Concurrent Generation**: The app makes 5 concurrent LLM calls during idea generation
- **Uniqueness Checking**: Each generated idea is checked against existing novel ideas using LLM
- **Stopping Criteria**: Idea generation stops when 75% of ideas are duplicates and >10 ideas generated
- **Prototype Generation**: Creates 3 distinct app specifications and HTML implementations per idea

## Project Structure

```
ideation/
├── ideation-backend/
│   ├── app/
│   │   └── main.py          # FastAPI application with all endpoints
│   ├── pyproject.toml        # Python dependencies
│   ├── uv.lock              # UV lock file
│   └── .env                  # Environment variables (create this)
│
└── ideation-frontend/
    ├── src/
    │   ├── App.tsx           # Main React application
    │   ├── App.css           # Styles
    │   └── components/ui/    # shadcn/ui components
    ├── package.json          # Node dependencies
    ├── vite.config.ts        # Vite configuration
    └── .env                  # Environment variables (create this)
```

## Contributing

This is a proof-of-concept application. For production use, consider:
- Adding persistent database storage
- Implementing user authentication
- Adding rate limiting for API calls
- Implementing proper error handling and logging
- Adding tests for both frontend and backend
- Optimizing LLM token usage

## License

MIT

## Author

Built by Devin for Andrew (@binardo)
