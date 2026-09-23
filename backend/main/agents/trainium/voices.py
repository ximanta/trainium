"""Voice catalogue for persona speech.

Gemini ships thirty prebuilt voices named after stars and moons (Puck, Kore,
Vindemiatrix). None of them is documented as Indian, and the Gemini API has no
locale parameter: it detects language from the input text. What Google does
document is that style, tone and accent are steerable with a natural language
prompt, so an Indian accent is produced by prefixing the line with an accent
instruction rather than by picking an "Indian voice".

Two consequences shape this module:

  - Admins pick from `VOICE_CATALOGUE`, which gives each voice a name and a
    plain description. The astronomical id is what reaches the API, never the
    admin's eyes.
  - `accent_prompt` wraps the spoken line. Verified by listening: the model
    follows the instruction rather than reading it aloud, and the accent is
    convincing on both male and female voices.

Gender comes from the Cloud TTS voice table, which documents it; the Gemini API
page lists only the characteristic. Characteristics below are Google's own
words.
"""

from typing import Literal

Gender = Literal["female", "male"]


class Voice:
    """One selectable voice. `id` is the Gemini prebuilt voice name."""

    def __init__(self, id: str, label: str, gender: Gender, character: str, description: str):
        self.id = id
        self.label = label
        self.gender = gender
        self.character = character
        self.description = description

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "gender": self.gender,
            "character": self.character,
            "description": self.description,
        }


# A curated subset rather than all thirty. These are the ones that suit adult
# learners in a training room, balanced across gender so persona names can be
# matched sensibly. Labels describe how the voice sounds, since "Puck" tells an
# admin nothing.
VOICE_CATALOGUE: list[Voice] = [
    Voice("Kore", "Steady", "female", "Firm", "Composed and level. Reads as someone who thinks before speaking."),
    Voice("Leda", "Youthful", "female", "Youthful", "Young and light. Suits a fresh graduate in their first job."),
    Voice("Aoede", "Breezy", "female", "Breezy", "Relaxed and easy. Sounds unbothered by being called on."),
    Voice("Despina", "Smooth", "female", "Smooth", "Even and warm. Comfortable speaking up in a group."),
    Voice("Vindemiatrix", "Gentle", "female", "Gentle", "Soft spoken and hesitant. Fits a quiet learner."),
    Voice("Sulafat", "Warm", "female", "Warm", "Friendly and open. Sounds glad to be in the room."),
    Voice("Puck", "Upbeat", "male", "Upbeat", "Bright and eager. Suits an enthusiastic beginner."),
    Voice("Charon", "Measured", "male", "Informative", "Deliberate and clear. Reads as someone explaining their reasoning."),
    Voice("Orus", "Assertive", "male", "Firm", "Direct and confident. Fits a learner who pushes back."),
    Voice("Fenrir", "Energetic", "male", "Excitable", "Quick and animated. Sounds like they are racing ahead."),
    Voice("Iapetus", "Clear", "male", "Clear", "Precise and unhurried. Easy to follow."),
    Voice("Achird", "Friendly", "male", "Friendly", "Approachable and casual. Sounds like a peer."),
]

VOICE_BY_ID = {v.id: v for v in VOICE_CATALOGUE}

DEFAULT_VOICE_ID = "Kore"

# A line that exercises Indian classroom register, so the preview shows both the
# accent and the phrasing a trainer will actually hear.
PREVIEW_LINE = (
    "Sir, I have one doubt. In the ReAct loop, how does the agent decide when to stop calling tools?"
)


def accent_prompt(text: str, gender: Gender) -> str:
    """Wrap a line so the model speaks it in Indian English.

    The gender word keeps the accent instruction consistent with the voice, so
    a female voice is not asked to sound like a young man.
    """
    who = "woman" if gender == "female" else "man"
    return (
        f"Say this in a natural Indian English accent, as a young {who} from India "
        f"speaking in a corporate training session. Speak only the line itself:\n{text}"
    )


def accent_prompt_for_voice(text: str, voice_id: str) -> str:
    """Accent-wrap `text` for whichever voice is configured."""
    voice = VOICE_BY_ID.get(voice_id)
    return accent_prompt(text, voice.gender if voice else "female")
