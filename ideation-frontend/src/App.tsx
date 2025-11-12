import { useState, useEffect } from 'react'
import './App.css'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Lightbulb, Heart, Trash2, Plus, Sparkles, ArrowLeft, ArrowRight, Code, X } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type Stage = 'problem' | 'clarifying' | 'statements' | 'ideation' | 'ideas' | 'prototypes'

interface Idea {
  id: string
  title: string
  description: string
  liked?: boolean
}

interface DuplicateIdea {
  idea: Idea
  similar_to: string
}

interface Prototype {
  idea_id: string
  idea_title: string
  prototypes: {
    spec_number: number
    spec: string
    html: string
  }[]
}

function App() {
  const [stage, setStage] = useState<Stage>('problem')
  const [sessionId, setSessionId] = useState<string>('')
  const [problem, setProblem] = useState('')
  const [questions, setQuestions] = useState('')
  const [answers, setAnswers] = useState('')
  const [problemStatements, setProblemStatements] = useState<string[]>(['', '', '', ''])
  const [selectedStatement, setSelectedStatement] = useState('')
  const [editingStatement, setEditingStatement] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [ideationProgress, setIdeationProgress] = useState({ total: 0, novel: 0, duplicates: 0, inflight: 0, generation_active: false })
  const [novelIdeas, setNovelIdeas] = useState<Idea[]>([])
  const [duplicateIdeas, setDuplicateIdeas] = useState<DuplicateIdea[]>([])
  const [_isGenerating, setIsGenerating] = useState(false)
  const [showSimilarIdeas, setShowSimilarIdeas] = useState<string | null>(null)
  const [showGenerateMore, setShowGenerateMore] = useState(false)
  const [prototypes, setPrototypes] = useState<Prototype[]>([])
  const [generatingPrototypes, setGeneratingPrototypes] = useState(false)
  const [viewingPrototype, setViewingPrototype] = useState<{ ideaId: string, prototypeIdx: number } | null>(null)
  const [selectedPersona, setSelectedPersona] = useState('')
  const [customPersona, setCustomPersona] = useState('')
  const [constraints, setConstraints] = useState<string[]>([])
  const [selectedConstraint, setSelectedConstraint] = useState('')

  const stages: Stage[] = ['problem', 'clarifying', 'statements', 'ideation', 'ideas', 'prototypes']
  const stageNames = {
    problem: 'Problem',
    clarifying: 'Clarify',
    statements: 'Define',
    ideation: 'Generate',
    ideas: 'Refine',
    prototypes: 'Prototype'
  }

  const currentStageIndex = stages.indexOf(stage)

  const startSession = async () => {
    if (!problem.trim()) return
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/start-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem })
      })
      const data = await response.json()
      setSessionId(data.session_id)
      setQuestions(data.questions)
      setStage('clarifying')
    } catch (error) {
      console.error('Error starting session:', error)
    }
    setLoading(false)
  }

  const submitAnswers = async () => {
    if (!answers.trim()) return
    setLoading(true)
    try {
      const response = await fetch(`${API_URL}/api/submit-answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, answers })
      })
      const data = await response.json()
      setProblemStatements(data.problem_statements)
      setStage('statements')
    } catch (error) {
      console.error('Error submitting answers:', error)
    }
    setLoading(false)
  }

  const selectStatement = async (statement: string) => {
    setSelectedStatement(statement)
    setLoading(true)
    try {
      await fetch(`${API_URL}/api/select-problem-statement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, problem_statement: statement })
      })
      setStage('ideation')
      setIsGenerating(true)
      await checkStatus()
    } catch (error) {
      console.error('Error selecting statement:', error)
      setLoading(false)
    }
  }

  const checkStatus = async () => {
    try {
      const response = await fetch(`${API_URL}/api/session-status/${sessionId}`)
      const data = await response.json()
      setIdeationProgress({
        total: data.total_ideas,
        novel: data.novel_ideas,
        duplicates: data.duplicate_ideas,
        inflight: data.inflight || 0,
        generation_active: data.generation_active || false
      })
      setNovelIdeas(data.novel_ideas_list)
      setDuplicateIdeas(data.duplicate_ideas_list)
      
      if (stage === 'ideation' && !data.generation_active && data.novel_ideas > 0) {
        setIsGenerating(false)
        setStage('ideas')
      }
      
      return data
    } catch (error) {
      console.error('Error checking status:', error)
      return { should_stop: false, novel_ideas: 0 }
    }
  }

  useEffect(() => {
    if (stage === 'ideation' && sessionId) {
      const interval = setInterval(checkStatus, 2000)
      return () => clearInterval(interval)
    }
  }, [stage, sessionId])

  const updateIdea = async (ideaId: string, title: string, description: string) => {
    try {
      await fetch(
        `${API_URL}/api/update-idea?session_id=${sessionId}&idea_id=${ideaId}&title=${encodeURIComponent(title)}&description=${encodeURIComponent(description)}`,
        { method: 'POST' }
      )
      setNovelIdeas(novelIdeas.map(i => i.id === ideaId ? { ...i, title, description } : i))
    } catch (error) {
      console.error('Error updating idea:', error)
    }
  }

  const deleteIdea = async (ideaId: string) => {
    try {
      await fetch(`${API_URL}/api/delete-idea?session_id=${sessionId}&idea_id=${ideaId}`, { method: 'POST' })
      setNovelIdeas(novelIdeas.filter(i => i.id !== ideaId))
    } catch (error) {
      console.error('Error deleting idea:', error)
    }
  }

  const likeIdea = async (ideaId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/like-idea?session_id=${sessionId}&idea_id=${ideaId}`, { method: 'POST' })
      const data = await response.json()
      setNovelIdeas(novelIdeas.map(i => i.id === ideaId ? { ...i, liked: data.liked } : i))
    } catch (error) {
      console.error('Error liking idea:', error)
    }
  }

  const addCustomIdea = async (title: string, description: string) => {
    try {
      const response = await fetch(
        `${API_URL}/api/add-idea?session_id=${sessionId}&title=${encodeURIComponent(title)}&description=${encodeURIComponent(description)}`,
        { method: 'POST' }
      )
      const idea = await response.json()
      setNovelIdeas([...novelIdeas, idea])
    } catch (error) {
      console.error('Error adding idea:', error)
    }
  }

  const generatePrototypes = async () => {
    const selectedIdeas = novelIdeas.filter(i => i.liked).map(i => i.id)
    if (selectedIdeas.length === 0) return

    setGeneratingPrototypes(true)
    try {
      const response = await fetch(`${API_URL}/api/generate-prototypes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, idea_ids: selectedIdeas })
      })
      const data = await response.json()
      setPrototypes(data.prototypes)
      setStage('prototypes')
    } catch (error) {
      console.error('Error generating prototypes:', error)
    }
    setGeneratingPrototypes(false)
  }

  const getSimilarIdeas = (ideaId: string) => {
    return duplicateIdeas.filter(d => d.similar_to === ideaId).map(d => d.idea)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-blue-50">
      <div className="fixed top-0 left-0 right-0 bg-white shadow-sm z-10">
        <div className="max-w-7xl mx-auto px-8 py-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-blue-600 bg-clip-text text-transparent">
              Ideation Studio
            </h1>
            {stage !== 'problem' && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const prevStage = stages[Math.max(0, currentStageIndex - 1)]
                  if (prevStage === 'ideation') {
                    setStage('statements')
                  } else {
                    setStage(prevStage)
                  }
                }}
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {stages.slice(0, -1).map((s, idx) => (
              <div key={s} className="flex items-center flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div
                    className={`w-full h-2 rounded-full transition-all duration-500 ${
                      idx < currentStageIndex
                        ? 'bg-gradient-to-r from-purple-500 to-blue-500'
                        : idx === currentStageIndex
                        ? 'bg-gradient-to-r from-purple-300 to-blue-300'
                        : 'bg-gray-200'
                    }`}
                  />
                  <span
                    className={`text-xs mt-1 font-medium transition-colors duration-300 ${
                      idx <= currentStageIndex ? 'text-purple-600' : 'text-gray-400'
                    }`}
                  >
                    {stageNames[s]}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="pt-32 pb-12 px-8">
        <div className="max-w-7xl mx-auto">
          {stage === 'problem' && (
            <div className="max-w-2xl mx-auto animate-in fade-in duration-500">
              <Card className="border-2 shadow-lg">
                <CardHeader>
                  <CardTitle className="text-3xl">What problem are you trying to solve?</CardTitle>
                  <CardDescription className="text-base">
                    Describe your challenge or opportunity in a few sentences
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Textarea
                    placeholder="Example: Our team struggles to collaborate effectively on creative projects..."
                    value={problem}
                    onChange={(e) => setProblem(e.target.value)}
                    className="min-h-32 text-base"
                  />
                  <Button
                    onClick={startSession}
                    disabled={!problem.trim() || loading}
                    className="mt-4 w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                    size="lg"
                  >
                    {loading ? <Spinner className="mr-2" /> : <Sparkles className="w-5 h-5 mr-2" />}
                    Start Ideation
                  </Button>
                </CardContent>
              </Card>
            </div>
          )}

          {stage === 'clarifying' && (
            <div className="max-w-3xl mx-auto animate-in fade-in duration-500">
              <Card className="border-2 shadow-lg">
                <CardHeader>
                  <CardTitle className="text-2xl">Let's clarify your problem</CardTitle>
                  <CardDescription>Answer these questions to help us understand better</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                    <p className="whitespace-pre-wrap text-gray-700">{questions}</p>
                  </div>
                  <Textarea
                    placeholder="Type your answers here..."
                    value={answers}
                    onChange={(e) => setAnswers(e.target.value)}
                    className="min-h-40 text-base"
                  />
                  <Button
                    onClick={submitAnswers}
                    disabled={!answers.trim() || loading}
                    className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                    size="lg"
                  >
                    {loading ? <Spinner className="mr-2" /> : <ArrowRight className="w-5 h-5 mr-2" />}
                    Continue
                  </Button>
                </CardContent>
              </Card>
            </div>
          )}

          {stage === 'statements' && (
            <div className="animate-in fade-in duration-500">
              <div className="text-center mb-8">
                <h2 className="text-3xl font-bold mb-2">Choose or refine a problem statement</h2>
                <p className="text-gray-600">Select one to start generating ideas, or edit to make it your own</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-6xl mx-auto">
                {problemStatements.map((statement, idx) => (
                  <Card
                    key={idx}
                    className="border-2 hover:border-purple-400 transition-all duration-300 hover:shadow-lg cursor-pointer"
                  >
                    <CardContent className="pt-6">
                      {editingStatement === idx ? (
                        <Textarea
                          value={statement}
                          onChange={(e) => {
                            const newStatements = [...problemStatements]
                            newStatements[idx] = e.target.value
                            setProblemStatements(newStatements)
                          }}
                          className="min-h-24 mb-4"
                          autoFocus
                        />
                      ) : (
                        <p className="text-gray-700 mb-4 min-h-24">{statement || 'Click to add your own...'}</p>
                      )}
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditingStatement(editingStatement === idx ? null : idx)}
                          className="flex-1"
                        >
                          {editingStatement === idx ? 'Done' : 'Edit'}
                        </Button>
                        <Button
                          onClick={() => selectStatement(statement)}
                          disabled={!statement.trim() || loading}
                          className="flex-1 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                        >
                          Generate Ideas
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {stage === 'ideation' && (
            <div className="max-w-2xl mx-auto animate-in fade-in duration-500">
              <Card className="border-2 shadow-lg">
                <CardHeader>
                  <CardTitle className="text-2xl">Generating Ideas</CardTitle>
                  <CardDescription>Our AI is exploring creative solutions...</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                    <p className="text-sm font-medium text-gray-700 mb-2">Problem Statement:</p>
                    <p className="text-gray-800">{selectedStatement}</p>
                  </div>
                  
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="font-medium">Total Ideas Generated</span>
                        <span className="text-purple-600 font-bold">{ideationProgress.total}</span>
                      </div>
                      <Progress value={(ideationProgress.total / 30) * 100} className="h-2" />
                    </div>

                    <div>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="font-medium">Novel Ideas</span>
                        <span className="text-green-600 font-bold">{ideationProgress.novel}</span>
                      </div>
                      <Progress value={(ideationProgress.novel / 15) * 100} className="h-2 bg-green-100" />
                    </div>

                    {ideationProgress.total > 10 && (
                      <div>
                        <div className="flex justify-between text-sm mb-2">
                          <span className="font-medium">Diversity Score</span>
                          <span className="text-blue-600 font-bold">
                            {Math.round(((ideationProgress.total - ideationProgress.duplicates) / ideationProgress.total) * 100)}%
                          </span>
                        </div>
                        <Progress
                          value={((ideationProgress.total - ideationProgress.duplicates) / ideationProgress.total) * 100}
                          className="h-2 bg-blue-100"
                        />
                      </div>
                    )}

                    {ideationProgress.generation_active && (
                      <div className="bg-purple-50 p-3 rounded-lg border border-purple-200">
                        <div className="flex justify-between items-center text-sm">
                          <span className="font-medium text-purple-700">Calls in Progress</span>
                          <span className="text-purple-600 font-bold">{ideationProgress.inflight}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-center py-8">
                    <Spinner className="w-12 h-12 text-purple-600" />
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {stage === 'ideas' && (
            <div className="animate-in fade-in duration-500">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <h2 className="text-3xl font-bold mb-2">Ideas</h2>
                  <p className="text-gray-600">
                    {novelIdeas.filter(i => i.liked).length} selected • {novelIdeas.length} total ideas
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setShowGenerateMore(true)}
                    className="border-purple-300 hover:bg-purple-50"
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    Generate More
                  </Button>
                  <Button
                    onClick={generatePrototypes}
                    disabled={novelIdeas.filter(i => i.liked).length === 0 || generatingPrototypes}
                    className="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
                  >
                    {generatingPrototypes ? <Spinner className="mr-2" /> : <Code className="w-4 h-4 mr-2" />}
                    Build Prototypes
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {novelIdeas.map((idea) => (
                  <Card
                    key={idea.id}
                    className={`border-2 transition-all duration-300 hover:shadow-lg ${
                      idea.liked ? 'border-purple-400 bg-purple-50' : 'border-gray-200 hover:border-purple-200'
                    }`}
                  >
                    <CardContent className="pt-4">
                      <div className="flex justify-between items-center mb-3">
                        <div className="flex items-center gap-2">
                          <Lightbulb className={`w-4 h-4 ${idea.liked ? 'text-purple-600' : 'text-gray-400'}`} />
                          {getSimilarIdeas(idea.id).length > 0 && (
                            <Badge 
                              variant="outline" 
                              className="text-xs px-1.5 py-0 h-5 cursor-pointer hover:bg-gray-100"
                              onClick={() => setShowSimilarIdeas(idea.id)}
                            >
                              {getSimilarIdeas(idea.id).length} similar
                            </Badge>
                          )}
                        </div>
                        <div className="flex gap-0.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => likeIdea(idea.id)}
                            className={`h-7 w-7 p-0 ${idea.liked ? 'text-red-500 hover:text-red-600' : 'text-gray-400 hover:text-red-500'}`}
                          >
                            <Heart className={`w-3.5 h-3.5 ${idea.liked ? 'fill-current' : ''}`} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => deleteIdea(idea.id)}
                            className="text-gray-400 hover:text-red-500 h-7 w-7 p-0"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
                      
                      <Input
                        value={idea.title}
                        onChange={(e) => updateIdea(idea.id, e.target.value, idea.description)}
                        className="font-semibold text-base mb-3 border-0 px-0 focus-visible:ring-0"
                      />
                      
                      <Textarea
                        value={idea.description}
                        onChange={(e) => updateIdea(idea.id, idea.title, e.target.value)}
                        className="text-base text-gray-700 min-h-32 border-0 px-0 focus-visible:ring-0 resize-none"
                      />
                    </CardContent>
                  </Card>
                ))}

                <Card className="border-2 border-dashed border-gray-300 hover:border-purple-400 transition-all duration-300 cursor-pointer">
                  <CardContent
                    className="pt-6 flex flex-col items-center justify-center min-h-64"
                    onClick={() => {
                      const title = prompt('Enter idea title:')
                      if (title) {
                        const description = prompt('Enter idea description:')
                        if (description) {
                          addCustomIdea(title, description)
                        }
                      }
                    }}
                  >
                    <Plus className="w-12 h-12 text-gray-400 mb-2" />
                    <p className="text-gray-500 font-medium">Add Custom Idea</p>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {stage === 'prototypes' && (
            <div className="animate-in fade-in duration-500">
              {viewingPrototype ? (
                <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
                  <div className="bg-white rounded-lg w-full h-full max-w-7xl max-h-screen flex flex-col">
                    <div className="p-4 border-b flex justify-between items-center">
                      <h3 className="font-semibold">
                        {prototypes.find(p => p.idea_id === viewingPrototype.ideaId)?.idea_title} - Prototype {viewingPrototype.prototypeIdx + 1}
                      </h3>
                      <Button variant="ghost" onClick={() => setViewingPrototype(null)}>
                        Close
                      </Button>
                    </div>
                    <div className="flex-1 overflow-hidden">
                      <iframe
                        srcDoc={prototypes.find(p => p.idea_id === viewingPrototype.ideaId)?.prototypes[viewingPrototype.prototypeIdx]?.html}
                        className="w-full h-full border-0"
                        title="Prototype"
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <div className="text-center mb-8">
                    <h2 className="text-3xl font-bold mb-2">Your Prototypes</h2>
                    <p className="text-gray-600">Interactive prototypes for your selected ideas</p>
                  </div>

                  <div className="space-y-8">
                    {prototypes.map((prototype) => (
                      <Card key={prototype.idea_id} className="border-2 shadow-lg">
                        <CardHeader>
                          <CardTitle className="text-xl">{prototype.idea_title}</CardTitle>
                          <CardDescription>3 different prototype variations</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {prototype.prototypes.map((proto, idx) => (
                              <Card
                                key={idx}
                                className="border hover:border-purple-400 transition-all cursor-pointer"
                                onClick={() => setViewingPrototype({ ideaId: prototype.idea_id, prototypeIdx: idx })}
                              >
                                <CardContent className="pt-6">
                                  <Badge className="mb-2">Prototype {proto.spec_number}</Badge>
                                  <p className="text-sm text-gray-600 line-clamp-3">{proto.spec}</p>
                                  <Button variant="outline" className="w-full mt-4">
                                    View Prototype
                                  </Button>
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <Dialog open={showSimilarIdeas !== null} onOpenChange={() => setShowSimilarIdeas(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Similar Ideas</DialogTitle>
            <DialogDescription>
              These ideas were flagged as similar to the selected one
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {showSimilarIdeas && getSimilarIdeas(showSimilarIdeas).map((idea) => (
              <Card key={idea.id} className="border">
                <CardContent className="pt-4">
                  <p className="font-semibold mb-1">{idea.title}</p>
                  <p className="text-sm text-gray-600">{idea.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showGenerateMore} onOpenChange={setShowGenerateMore}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Generate More Ideas</DialogTitle>
            <DialogDescription>
              Customize the ideation approach
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Persona Perspective</Label>
              <Select value={selectedPersona} onValueChange={setSelectedPersona}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a persona..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="visionary">Visionary Tech Leader (Elon Musk style)</SelectItem>
                  <SelectItem value="influencer">Social Media Influencer (Kim Kardashian style)</SelectItem>
                  <SelectItem value="scientist">Brilliant Scientist (Einstein style)</SelectItem>
                  <SelectItem value="investor">Strategic Investor (Warren Buffett style)</SelectItem>
                  <SelectItem value="custom">Custom Persona</SelectItem>
                </SelectContent>
              </Select>
              {selectedPersona === 'custom' && (
                <Input
                  placeholder="Describe the persona..."
                  value={customPersona}
                  onChange={(e) => setCustomPersona(e.target.value)}
                  className="mt-2"
                />
              )}
            </div>

            <div className="space-y-2">
              <Label>Constraints</Label>
              <Select value={selectedConstraint} onValueChange={(value) => {
                if (value && !constraints.includes(value)) {
                  setConstraints([...constraints, value])
                  setSelectedConstraint('')
                }
              }}>
                <SelectTrigger>
                  <SelectValue placeholder="Add a constraint..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="budget">Limited Budget</SelectItem>
                  <SelectItem value="time">Time Constraint</SelectItem>
                  <SelectItem value="tech">Existing Technology Only</SelectItem>
                  <SelectItem value="simple">Must Be Simple</SelectItem>
                  <SelectItem value="scalable">Must Be Highly Scalable</SelectItem>
                  <SelectItem value="privacy">Privacy-Focused</SelectItem>
                  <SelectItem value="sustainable">Environmentally Sustainable</SelectItem>
                </SelectContent>
              </Select>
              {constraints.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {constraints.map((constraint, idx) => (
                    <Badge key={idx} variant="secondary" className="gap-1">
                      {constraint}
                      <X 
                        className="w-3 h-3 cursor-pointer" 
                        onClick={() => setConstraints(constraints.filter((_, i) => i !== idx))}
                      />
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            <Button
              className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700"
              onClick={() => {
                setShowGenerateMore(false)
                setStage('ideation')
                setIsGenerating(true)
                checkStatus()
              }}
            >
              <Sparkles className="w-4 h-4 mr-2" />
              Generate Ideas
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default App
