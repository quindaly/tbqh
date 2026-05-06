"""Prompt templates for LLM orchestration."""

INTAKE_EXTRACTION_SYSTEM = """You are an assistant that analyzes a group description for a social discussion app.
Given the user's free-text description of their group and a safety policy, extract structured information
and generate follow-up multiple-choice questions to clarify preferences.

You MUST respond with valid JSON containing EXACTLY these top-level keys (no others):
{
  "group_summary": "<string, 1-600 chars: concise summary of the group>",
  "audience_context": "<one of: friends, coworkers, family, couples, strangers, mixed, unknown>",
  "desired_vibe": "<one of: playful, reflective, balanced, high_energy, calm, unknown>",
  "depth_preference": <integer 1-5, where 1=light/fun and 5=deep/philosophical>,
  "language": "<language code, e.g. en>",
  "followup_needed": <true or false>,
  "followup_question_specs": [
    {
      "prompt_text": "<string, 1-180 chars: the question to ask>",
      "options": ["<4-8 options, each 1-60 chars, last one should be 'Other (type your own)'>"],
      "allow_other": true,
      "answer_type": "single_select",
      "why_needed": "<string, 1-240 chars: why this question helps personalize>"
    }
  ]
}

Rules:
- No additional properties beyond the keys listed above.
- Generate 3-8 follow-up questions in followup_question_specs.
- Each question must have 4-8 options. The last option should be "Other (type your own)".
- Set followup_needed to true if you generate any questions."""

INTAKE_EXTRACTION_USER = """Group description: {free_text}
Safety policy: {policy_name} (excluded categories: {excluded_categories})

Analyze this group and respond with the JSON object described in your instructions. Remember: use ONLY the exact keys specified (group_summary, audience_context, desired_vibe, depth_preference, language, followup_needed, followup_question_specs)."""

FOLLOWUP_GENERATION_SYSTEM = """You generate follow-up multiple-choice questions for a group discussion app.
Each question helps narrow down the group's preferences, vibe, and interests.

You MUST respond with valid JSON containing EXACTLY this structure (no other keys):
{
  "prompts": [
    {
      "prompt_text": "<string, 1-180 chars: the question>",
      "options": ["<4-8 string options, each 1-60 chars, last should be 'Other (type your own)'>"],
      "allow_other": true,
      "answer_type": "single_select"
    }
  ]
}

Rules:
- Generate 3-8 questions in the "prompts" array.
- Each question must have 4-8 options.
- The last option should be "Other (type your own)".
- No additional properties beyond what is listed."""

FOLLOWUP_GENERATION_USER = """Based on the intake extraction:
{intake_data}

Generate follow-up multiple-choice questions using EXACTLY the JSON structure described in your instructions (top-level key "prompts" containing an array of question objects)."""

GROUP_PROFILE_SYNTHESIS_SYSTEM = """You synthesize a group profile from the initial description and follow-up answers.
Be thorough: extract key traits, topics of interest, constraints, vibe, depth, audience context.

You MUST respond with valid JSON containing EXACTLY these keys (no others):
{
  "summary": "<string, 1-800 chars: comprehensive group summary>",
  "key_traits": ["<3-12 strings, each 1-40 chars: defining traits of this group>"],
  "topics_of_interest": ["<3-20 strings, each 1-40 chars: topics they'd enjoy discussing>"],
  "constraints": ["<0-10 strings, each 1-80 chars: any topics or styles to avoid>"],
  "vibe": "<one of: playful, reflective, balanced, high_energy, calm, unknown>",
  "depth": <integer 1-5>,
  "audience_context": "<one of: friends, coworkers, family, couples, strangers, mixed, unknown>",
  "language": "<language code, e.g. en>",
  "safety_policy_name": "<string: the name of the safety policy applied>"
}

No additional properties beyond what is listed."""

GROUP_PROFILE_SYNTHESIS_USER = """Original group description: {free_text}

Follow-up questions and answers:
{followup_qa}

Safety policy: {policy_name}

Synthesize a comprehensive group profile. Respond with EXACTLY the JSON keys described in your instructions (summary, key_traits, topics_of_interest, constraints, vibe, depth, audience_context, language, safety_policy_name)."""

CONSTRAINED_REWORDING_SYSTEM = """You optionally reword a discussion question to better fit a group's profile.
Rules:
- Preserve the original meaning
- Keep a human, conversational tone
- Do not introduce any content from restricted categories
- Only reword if it meaningfully improves fit; otherwise set should_reword to false

You MUST respond with valid JSON containing EXACTLY these keys (no others):
{
  "should_reword": <true or false>,
  "reworded_question": "<string or null, max 220 chars: the reworded question, or null if should_reword is false>",
  "reason": "<string, 1-200 chars: why you chose to reword or not>"
}"""

CONSTRAINED_REWORDING_USER = """Group profile summary: {profile_summary}
Group traits: {key_traits}
Original question: {question_text}
Restricted categories: {restricted_categories}

Should this question be reworded to better fit this group? Respond with EXACTLY the JSON keys: should_reword, reworded_question, reason."""

# --- Distractor Generation for How Well Do You Know ---

DISTRACTOR_GENERATION_SYSTEM = """You generate plausible wrong answers for a social trivia game called "How Well Do You Know [Person]?"

Given a personal question and the correct answer about someone, generate believable but incorrect alternative answers.

You MUST respond with valid JSON containing EXACTLY this structure (no other keys):
{
  "wrong_answers": ["<string>", "<string>", "<string>"]
}

Rules:
- Generate exactly the requested number of wrong answers.
- Wrong answers must be plausible for the person and question context.
- Match the length, specificity, and tone of the correct answer.
- Do NOT include the correct answer or near-duplicates of it.
- Do NOT include offensive, sexual, cruel, or embarrassing content.
- Do NOT include obviously fake or joke answers.
- Each wrong answer should be distinct from the others.
- Keep answers concise (under 80 characters each).
- Consider the intimacy/tone level when generating answers."""

DISTRACTOR_GENERATION_USER = """Question: {question_text}
Correct answer: {correct_answer}
Number of wrong answers needed: {num_distractors}
Intimacy level: {intimacy_level}
Context about the person (if available): {person_context}

Generate plausible wrong answers. Respond with EXACTLY the JSON structure: {{"wrong_answers": [...]}}"""
