from main.db import db

courses_collection = db["trainium_courses"]
teaching_graphs_collection = db["trainium_teaching_graphs"]
persona_templates_collection = db["trainium_persona_templates"]
scenarios_collection = db["trainium_scenarios"]
rubrics_collection = db["trainium_rubrics"]
simulations_collection = db["trainium_simulations"]
recordings_collection = db["trainium_recordings"]
transcripts_collection = db["trainium_transcripts"]
events_collection = db["trainium_events"]
evidence_collection = db["trainium_evidence"]
reports_collection = db["trainium_reports"]
analysis_jobs_collection = db["trainium_analysis_jobs"]

# Nine persona types (spec §12), each given a distinct Gemini TTS voice
# (architecture doc §7.2 seed mapping). org_id is None: these are system
# defaults available to every org.
PERSONA_TEMPLATE_SEED = [
    {
        "id": "persona_curious",
        "org_id": None,
        "name": "Priya",
        "type": "curious",
        "profile": "Asks relevant questions that connect to material already covered.",
        "voice_id": "Puck",
    },
    {
        "id": "persona_beginner",
        "org_id": None,
        "name": "Leo",
        "type": "beginner",
        "profile": "Needs concepts simplified and restated in plain terms.",
        "voice_id": "Leda",
    },
    {
        "id": "persona_skeptic",
        "org_id": None,
        "name": "Devon",
        "type": "skeptic",
        "profile": "Challenges assumptions and pushes back until the reasoning holds.",
        "voice_id": "Charon",
    },
    {
        "id": "persona_silent",
        "org_id": None,
        "name": "Tomas",
        "type": "silent",
        "profile": "Rarely participates unless directly drawn into the discussion.",
        "voice_id": "Vindemiatrix",
    },
    {
        "id": "persona_confused",
        "org_id": None,
        "name": "Amara",
        "type": "confused",
        "profile": "Misunderstands concepts and needs correction before moving on.",
        "voice_id": "Despina",
    },
    {
        "id": "persona_fast_learner",
        "org_id": None,
        "name": "Miriam",
        "type": "fast_learner",
        "profile": "Grasps material quickly and moves ahead of the current pace.",
        "voice_id": "Fenrir",
    },
    {
        "id": "persona_distracted",
        "org_id": None,
        "name": "Jordan",
        "type": "distracted",
        "profile": "Drifts off topic and asks adjacent, unrelated questions.",
        "voice_id": "Aoede",
    },
    {
        "id": "persona_hacker",
        "org_id": None,
        "name": "Sam",
        "type": "hacker",
        "profile": "Probes edge cases and asks what happens when things break.",
        "voice_id": "Orus",
    },
    {
        "id": "persona_senior_practitioner",
        "org_id": None,
        "name": "Elena",
        "type": "senior_practitioner",
        "profile": "Asks how the material applies to real business scenarios.",
        "voice_id": "Kore",
    },
]

# Scenario library (spec §16). script is a short directive summary; the full
# timed-directive format lands with the Director build in M3.
SCENARIO_SEED = [
    {
        "id": "scenario_difficult_learner",
        "name": "Difficult Learner",
        "kind": "difficult_learner",
        "script": "One persona is uncooperative and resistant to guidance throughout the session.",
    },
    {
        "id": "scenario_demo_failure",
        "name": "Demo Failure",
        "kind": "demo_failure",
        "script": "A live demo fails partway through and the trainer must recover without the material.",
    },
    {
        "id": "scenario_silent_classroom",
        "name": "Silent Classroom",
        "kind": "silent_classroom",
        "script": "All personas stay quiet unless the trainer actively prompts them.",
    },
    {
        "id": "scenario_time_pressure",
        "name": "Time Pressure",
        "kind": "time_pressure",
        "script": "The session runs on a compressed clock, forcing the trainer to cut content.",
    },
    {
        "id": "scenario_confused_group",
        "name": "Confused Group",
        "kind": "confused_group",
        "script": "Most personas misunderstand the core concept at the same time.",
    },
    {
        "id": "scenario_dominant_learner",
        "name": "Dominant Learner",
        "kind": "dominant_learner",
        "script": "One persona repeatedly takes over the discussion, crowding out the others.",
    },
    {
        "id": "scenario_off_topic",
        "name": "Off-topic Discussion",
        "kind": "off_topic",
        "script": "The group repeatedly pulls the conversation away from the agenda.",
    },
]


# Default rubric (spec §24), seeded once so sessions have something to
# evaluate against out of the box. Admins can edit this or create new ones.
# Anchor text here is a starting point, not final: the architecture doc's
# guidance to write anchors with a real training manager still applies before
# this is relied on for certification decisions.
DEFAULT_RUBRIC_SEED = {
    "id": "rubric_default_v1",
    "org_id": None,
    "name": "Default Trainer Evaluation",
    "description": "Baseline rubric covering the seven core training competencies.",
    "status": "published",
    "version": 1,
    "created_by": None,
    "competencies": [
        {
            "key": "concept_explanation",
            "label": "Concept Explanation",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Explanations are inaccurate or missing.",
                "3": "Explanations are accurate but lack concrete examples.",
                "5": "Explanations are accurate and use at least one concrete analogy or example.",
            },
        },
        {
            "key": "learner_engagement",
            "label": "Learner Engagement",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Learners are rarely invited into the discussion.",
                "3": "Learners are occasionally invited into the discussion.",
                "5": "Learners are consistently and specifically drawn into the discussion.",
            },
        },
        {
            "key": "question_handling",
            "label": "Question Handling",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Questions are deflected or answered incorrectly.",
                "3": "Questions are answered correctly but without elaboration.",
                "5": "Questions are answered correctly, with elaboration tied to the material.",
            },
        },
        {
            "key": "demo_delivery",
            "label": "Demo Delivery",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Demo is skipped, fails, or is not recovered from.",
                "3": "Demo completes with minor issues.",
                "5": "Demo completes smoothly and reinforces the concept being taught.",
            },
        },
        {
            "key": "lab_facilitation",
            "label": "Lab Facilitation",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Learners are left without guidance during the lab.",
                "3": "Guidance is available but reactive only.",
                "5": "Guidance is proactive and tailored to individual learner progress.",
            },
        },
        {
            "key": "classroom_management",
            "label": "Classroom Management",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Disruptions or off-topic threads are not addressed.",
                "3": "Disruptions are addressed but interrupt the flow of the session.",
                "5": "Disruptions are addressed smoothly without losing session pace.",
            },
        },
        {
            "key": "time_management",
            "label": "Time Management",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Session significantly overruns or underruns the plan.",
                "3": "Session stays roughly on schedule with minor drift.",
                "5": "Session covers all planned material within the allotted time.",
            },
        },
    ],
}


async def ensure_indexes() -> None:
    await courses_collection.create_index([("org_id", 1), ("status", 1)])
    await courses_collection.create_index([("owner_id", 1)])
    await rubrics_collection.create_index([("org_id", 1), ("status", 1)])
    await teaching_graphs_collection.create_index(
        [("course_id", 1), ("version", -1)], unique=True
    )
    await simulations_collection.create_index([("trainer_id", 1), ("started_at", -1)])
    await simulations_collection.create_index([("org_id", 1), ("status", 1)])
    await simulations_collection.create_index([("course_id", 1)])
    await recordings_collection.create_index([("simulation_id", 1), ("track", 1)])
    await transcripts_collection.create_index([("simulation_id", 1)], unique=True)
    await events_collection.create_index([("simulation_id", 1), ("ts_s", 1)])
    await evidence_collection.create_index([("simulation_id", 1), ("competency", 1)])
    await reports_collection.create_index([("simulation_id", 1)], unique=True)
    await analysis_jobs_collection.create_index([("simulation_id", 1)])
    await analysis_jobs_collection.create_index([("status", 1), ("updated_at", 1)])


async def seed_reference_data() -> None:
    for persona in PERSONA_TEMPLATE_SEED:
        await persona_templates_collection.update_one(
            {"id": persona["id"]}, {"$setOnInsert": persona}, upsert=True
        )
    for scenario in SCENARIO_SEED:
        await scenarios_collection.update_one(
            {"id": scenario["id"]}, {"$setOnInsert": scenario}, upsert=True
        )
    await rubrics_collection.update_one(
        {"id": DEFAULT_RUBRIC_SEED["id"]}, {"$setOnInsert": DEFAULT_RUBRIC_SEED}, upsert=True
    )
