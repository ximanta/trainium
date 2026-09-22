# AI Trainer Simulator – Full Implementation Specification (V1)

## 1. Purpose

Build an AI-powered Trainer Simulator that allows trainers to practice delivering instructor-led training sessions in a simulated classroom populated by AI learner personas.

The simulator records the session, analyzes trainer performance using Gemini multimodal capabilities, and generates a detailed coaching and certification report.

---

# 2. Business Goals

## Problems

- Trainer quality varies significantly.
- Trainer certification requires manual observation.
- Trainers rarely get realistic practice.
- Feedback quality depends on reviewers.

## Outcomes

- Standardized trainer evaluation.
- Faster trainer onboarding.
- Repeatable trainer certification.
- AI-assisted coaching.

---

# 3. Product Vision

A trainer uploads course assets and enters a virtual classroom.

AI learner personas participate realistically.

The trainer teaches as if conducting a live session.

The entire session is recorded.

Video + audio + transcript + classroom events are analyzed.

A structured report is generated.

---

# 4. Key Design Principles

## Objective Driven

Simulation evaluates learning objectives, not slide completion.

## Director Controlled

Personas never independently decide to speak.

An invisible Classroom Director controls participation.

## Evidence Based

Every score must have timestamped evidence.

## Post Session Analysis

No deep scoring during delivery.

All assessment occurs after recording.

---

# 5. Users

## Trainer

Runs simulation.

## Training Manager

Reviews reports.

## Curriculum Owner

Uploads content.

## Coach

Provides guidance using generated reports.

---

# 6. Technology Stack

## Frontend

- React
- TypeScript
- WebRTC
- Tailwind

## Backend

- FastAPI
- Python 3.12

## Agent Framework

- LangGraph
- LangChain

## AI Models

- Gemini 2.5 Pro
- Gemini Video Understanding
- Gemini Flash (low-latency interactions)

## Storage

- PostgreSQL
- Redis
- S3 / Azure Blob

## Observability

- LangSmith
- OpenTelemetry

---

# 7. High-Level Architecture

```text
Trainer

    |
    v

Virtual Classroom UI

    |
    v

Observation Engine

    |
    v

Classroom Director

    |
    v

Persona Manager

    |
    v

Voice Interaction Layer

    |
    v

Recording Service
```

---

# 8. Course Ingestion Pipeline

## Inputs

Mandatory:

- PPTX

Optional:

- Instructor Guide
- Lab PDF
- Assessments
- Demo Guide
- Learning Objectives

---

## Extraction

Extract:

- slide text
- speaker notes
- diagrams
- headings
- screenshots

---

## LLM Processing

Generate:

- learning objectives
- concept graph
- prerequisite graph
- misconceptions
- expected questions
- difficulty map

---

# 9. Teaching Graph

Generated representation.

```json
{
  "module":"Agent Memory",
  "learning_objectives":[
    "Explain semantic memory",
    "Explain episodic memory"
  ]
}
```

Used by:

- personas
- director
- evaluation

---

# 10. Classroom Director

## Purpose

Controls realism.

Trainer never sees Director.

---

## Responsibilities

Determine:

- should anyone speak
- who speaks
- what is asked
- timing
- interruption behavior

---

## Director Inputs

- trainer transcript
- current objective
- elapsed time
- persona states
- event history

---

## Director Outputs

- learner question
- learner reaction
- confusion event
- silence

---

# 11. Persona Framework

Each persona contains:

## Profile

```json
{
  "name":"Ravi",
  "type":"Curious"
}
```

## Knowledge State

Current mastery.

## Emotional State

- engagement
- frustration
- confidence

## Session Memory

What trainer already taught.

---

# 12. Persona Types

### Curious

Relevant questions.

### Beginner

Needs simplification.

### Skeptic

Challenges assumptions.

### Silent

Rarely participates.

### Confused

Misunderstands concepts.

### Fast Learner

Moves ahead.

### Distracted

Off-topic behavior.

### Hacker

Edge-case questions.

### Senior Practitioner

Asks business applicability questions.

---

# 13. Session State Model

```python
class SessionState:

    current_topic

    learning_objective

    elapsed_time

    transcript

    persona_states

    events

    evidence
```

---

# 14. LangGraph Workflow

```text
START

Course Context

Observation

Director Decision

Persona Selection

Response Generation

Voice Output

Observation

END
```

---

# 15. Simulation Modes

## Practice

Visible coaching.

## Certification

Director hidden.

## Scenario Mode

Specific teaching challenge.

---

# 16. Scenario Library

### Difficult Learner

### Demo Failure

### Silent Classroom

### Time Pressure

### Confused Group

### Dominant Learner

### Off-topic Discussion

---

# 17. Voice Interaction

## Trainer

Human voice.

## Learners

TTS generated.

Possible providers:

- Gemini TTS
- Azure Speech

---

# 18. Classroom Dynamics Rules

### Default

Single learner interaction.

### Rare

Multiple learners.

### Very Rare

Group discussion.

Goal:

Match real classroom behavior.

---

# 19. Event Engine

Injects:

- confusion
- disengagement
- interruptions
- demo issues

---

# 20. Recording Architecture

Capture:

## Webcam

Trainer video.

## Audio

Trainer voice.

## Screen

Slides and demos.

## Events

Timeline events.

---

# 21. Session Artifacts

```text
session.mp4

transcript.json

events.json

report.json
```

---

# 22. Transcript Generation

Pipeline:

Video

→ Audio Extraction

→ Speech-to-Text

→ Speaker Attribution

→ Structured Transcript

---

# 23. Gemini Analysis Pipeline

## Stage 1

Transcript Review

Evaluate:

- explanations
- pacing
- clarity

---

## Stage 2

Video Review

Evaluate:

- confidence
- eye contact
- energy
- engagement

---

## Stage 3

Pedagogy Review

Evaluate:

- objective coverage
- misconceptions
- sequencing

---

## Stage 4

Evidence Extraction

Generate timestamped evidence.

---

# 24. Evaluation Framework

## Concept Explanation

## Learner Engagement

## Question Handling

## Demo Delivery

## Lab Facilitation

## Classroom Management

## Time Management

---

# 25. Scoring Rubric

Range:

1-5

### 1

Poor

### 2

Needs Improvement

### 3

Acceptable

### 4

Strong

### 5

Excellent

---

# 26. Evidence Model

Every score requires evidence.

Example:

```json
{
  "time":"12:45",
  "competency":"Question Handling",
  "evidence":"Provided analogy explaining memory types"
}
```

---

# 27. Report Structure

## Executive Summary

## Competency Breakdown

## Strengths

## Improvement Areas

## Timeline Replay

## Coaching Plan

---

# 28. Database Schema

## users

## courses

## simulations

## recordings

## reports

## personas

## events

---

# 29. API Endpoints

## Course Upload

POST /courses

## Start Session

POST /simulation/start

## End Session

POST /simulation/end

## Generate Report

POST /report/generate

## Get Report

GET /report/{id}

---

# 30. Storage Model

PostgreSQL

- metadata

Redis

- session state

Blob Storage

- recordings

---

# 31. Security

- JWT auth
- Role based access
- Signed recording URLs
- Encryption at rest

---

# 32. Observability

Track:

- latency
- token usage
- persona decisions
- report generation time

LangSmith traces required.

---

# 33. Deployment

Frontend

React SPA

Backend

FastAPI containers

AI Services

Gemini APIs

Storage

Managed cloud services

---

# 34. MVP Scope

Include:

- PPT ingestion
- 5 personas
- Classroom Director
- Voice interaction
- Recording
- Transcript generation
- Gemini evaluation
- Report generation

---

# 35. Phase 2

- Avatars
- Real-time coaching
- Multi-language support
- Custom personas

---

# 36. Phase 3

- Enterprise certification
- Benchmarking
- Trainer leaderboard
- Organization analytics

---

# 37. Success Metrics

- Trainer adoption
- Certification reduction effort
- Repeat usage
- Trainer score improvement
- Report usefulness rating

---

# 38. Open Questions

- Exact simulation duration strategy
- Voice provider selection
- Avatar roadmap
- Human calibration process
- Certification governance

---

# 39. Recommended MVP Duration

30-minute simulation.

Represents key learning objectives from a 2-hour course.

Focus on critical teaching moments rather than complete delivery.

---

# 40. Final Recommendation

Build the platform as:

- Objective-driven
- LangGraph orchestrated
- Director-controlled
- Gemini-assessed
- Evidence-based

The recorded video and transcript become the source of truth for all evaluation and coaching.
