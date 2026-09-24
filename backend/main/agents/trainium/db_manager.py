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
# One document per human rating of one session. Separate from the report so a
# second reviewer never overwrites the first: agreement needs both opinions,
# not a consensus that has already collapsed them.
reviews_collection = db["trainium_reviews"]

# Nine persona types (spec §12), each given a distinct Gemini TTS voice
# (architecture doc §7.2 seed mapping). org_id is None: these are system
# defaults available to every org.
#
# Profiles are written as behavioural direction, not labels, because the whole
# string is handed to the Director as the persona's character. Each says how
# the learner speaks, what they tend to ask about, and their English register.
# The default cohort is fresh engineering graduates from tier-2 Indian
# colleges, so the register notes matter: they are what stop every persona
# sounding like the same fluent American.
PERSONA_TEMPLATE_SEED = [
    {
        "id": "persona_curious",
        "org_id": None,
        "name": "Priya Sharma",
        "type": "curious",
        "profile": (
            "Engaged and genuinely interested. Asks questions that link what is on the "
            "slide back to something covered earlier, often starting with 'So does that "
            "mean...' or 'Is this similar to...'. Listens closely and builds on the "
            "trainer's own words rather than changing the subject. Speaks fluent but "
            "lightly formal Indian English, and is comfortable being the first to speak."
        ),
        "voice_id": "Leda",
    },
    {
        "id": "persona_beginner",
        "org_id": None,
        "name": "Rohit Verma",
        "type": "beginner",
        "profile": (
            "New to the subject and aware of it. Asks for plain restatement when jargon "
            "goes past him, usually as 'I did not follow the last part' or 'Can you "
            "please explain this term once more'. Needs analogies and concrete examples "
            "before abstractions land. Apologetic about interrupting and sometimes "
            "prefaces questions with an apology. Simple sentences, occasional hesitation."
        ),
        "voice_id": "Puck",
    },
    {
        "id": "persona_skeptic",
        "org_id": None,
        "name": "Arjun Nair",
        "type": "skeptic",
        "profile": (
            "Polite but not easily satisfied. Presses on claims that sound hand-waved, "
            "asking 'But how do we actually know that' or 'What is the evidence for this'. "
            "Will follow up a second time if the first answer dodges. Never rude, and "
            "accepts a good answer visibly. Confident, direct Indian English. Comfortable "
            "with silence while he waits for a real reply."
        ),
        "voice_id": "Orus",
    },
    {
        "id": "persona_silent",
        "org_id": None,
        "name": "Kavya Iyer",
        "type": "silent",
        "profile": (
            "Attentive but reluctant to speak. Almost never volunteers, and only responds "
            "when the trainer addresses her by name. When she does speak it is short, "
            "quiet and to the point, often just a few words. Understands more than she "
            "lets on, so her rare questions are sharp. Soft, hesitant delivery with pauses "
            "before answering."
        ),
        "voice_id": "Vindemiatrix",
    },
    {
        "id": "persona_confused",
        "org_id": None,
        "name": "Ananya Reddy",
        "type": "confused",
        "profile": (
            "Follows along but forms the wrong mental model and states it confidently, "
            "which is what makes her useful: the trainer has to notice and correct her. "
            "Conflates similar concepts, mixes up which step comes first, and says things "
            "like 'So this is the same as the previous one, no?'. Accepts correction "
            "readily once it is explained. Everyday conversational Indian English."
        ),
        "voice_id": "Despina",
    },
    {
        "id": "persona_fast_learner",
        "org_id": None,
        "name": "Meera Krishnan",
        "type": "fast_learner",
        "profile": (
            "Grasps the material well ahead of the pace and gets restless. Jumps to "
            "implications the trainer has not reached yet, asking 'Does this also work "
            "when...' or naming the next concept before it is introduced. Can derail the "
            "session by pulling it forward. Quick, clipped, fluent Indian English with "
            "little hesitation."
        ),
        "voice_id": "Sulafat",
    },
    {
        "id": "persona_distracted",
        "org_id": None,
        "name": "Vikram Joshi",
        "type": "distracted",
        "profile": (
            "Half present. Asks questions that are adjacent but off topic, often about a "
            "tool or company he half remembers, or something from a different module. "
            "Occasionally asks about something already answered while he was not "
            "listening. Not hostile, just drifting. Casual Indian English, sometimes "
            "starting mid-thought."
        ),
        "voice_id": "Achird",
    },
    {
        "id": "persona_hacker",
        "org_id": None,
        "name": "Sanjay Pillai",
        "type": "hacker",
        "profile": (
            "Thinks in failure modes. Asks what happens when the input is empty, the API "
            "times out, or two things run at once. Interested in limits and edge cases "
            "more than the happy path, and will ask 'What if it breaks here'. Practical "
            "rather than theoretical. Technical, informal Indian English, comfortable "
            "naming specific tools."
        ),
        "voice_id": "Iapetus",
    },
    {
        "id": "persona_senior_practitioner",
        "org_id": None,
        "name": "Deepa Menon",
        "type": "senior_practitioner",
        "profile": (
            "Has real delivery experience and filters everything through it. Asks how the "
            "material survives contact with an actual client or production system, often "
            "as 'In a real project, how would this work when...'. References constraints "
            "the fresher learners have not met: budgets, deadlines, legacy systems. "
            "Measured, professional Indian English. Speaks less often but with weight."
        ),
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



# Delivery competencies, scored only from the trainer's camera track. Kept as a
# separate rubric rather than added to the default one: a session recorded with
# the camera off should score the seven spoken competencies normally, not take
# zeros on criteria it never had the chance to demonstrate.
#
# Anchors describe what is visible at 1 frame per second, which is how Gemini
# samples video by default. Micro-expressions are deliberately absent: they are
# not reliably observable at that rate, and scoring them would be inventing
# detail the model cannot actually see.
VIDEO_RUBRIC_SEED = {
    "id": "rubric_delivery_v1",
    "org_id": None,
    "name": "Delivery and Presence",
    "description": (
        "How the trainer comes across on camera. Scored from the recording, so it "
        "only applies to sessions where the camera was on."
    ),
    "status": "published",
    "version": 1,
    "created_by": None,
    "competencies": [
        {
            "key": "eye_contact",
            "label": "Eye Contact",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Looks away from camera almost throughout, mostly reading.",
                "3": "Looks at camera intermittently but returns often to notes or slides.",
                "5": "Holds camera consistently, glancing away only briefly to reference material.",
            },
        },
        {
            "key": "posture_presence",
            "label": "Posture and Presence",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Slumped or drifting out of frame, low physical energy.",
                "3": "Steady and centred but static, with little variation.",
                "5": "Upright, well framed, with energy that suits the material.",
            },
        },
        {
            "key": "gesture_use",
            "label": "Gesture",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Hands out of frame or still throughout.",
                "3": "Occasional gestures, not clearly tied to what is being said.",
                "5": "Gestures illustrate the point being made, used purposefully.",
            },
        },
        {
            "key": "expression_warmth",
            "label": "Facial Expression",
            "scale_min": 1,
            "scale_max": 5,
            "anchors": {
                "1": "Flat throughout, no visible reaction to learners.",
                "3": "Some expression, though it rarely changes with the content.",
                "5": "Expression shifts with the material and responds visibly to learners.",
            },
        },
    ],
    "schema_version": 1,
}


async def seed_reference_data() -> None:
    # System templates (org_id None) are refreshed rather than inserted once, so
    # edits to the seed reach databases that already ran an older version. Only
    # these built-ins are overwritten; personas an org created are matched by a
    # different id and never touched.
    for persona in PERSONA_TEMPLATE_SEED:
        await persona_templates_collection.update_one(
            {"id": persona["id"]}, {"$set": persona}, upsert=True
        )
    for scenario in SCENARIO_SEED:
        await scenarios_collection.update_one(
            {"id": scenario["id"]}, {"$setOnInsert": scenario}, upsert=True
        )
    await rubrics_collection.update_one(
        {"id": DEFAULT_RUBRIC_SEED["id"]}, {"$setOnInsert": DEFAULT_RUBRIC_SEED}, upsert=True
    )
    await rubrics_collection.update_one(
        {"id": VIDEO_RUBRIC_SEED["id"]}, {"$set": VIDEO_RUBRIC_SEED}, upsert=True
    )
