# ML Week Generation Flow

This document explains every file involved in the adaptive learning pipeline —
from the moment a user submits a weekly quiz to the moment next week's chapters
and quiz are ready.

---

## The Big Picture

```
User submits quiz answers
        │
        ▼
controllers/quiz.py          ← orchestrates everything
        │
        ├── services/bkt.py              ← updates p_known per topic
        ├── services/bandit.py           ← updates content style arm
        ├── services/quiz.py             ← records attempt, scores quiz
        │
        └── _generate_next_week()        ← background task
                │
                ├── services/bkt.py              ← get weak topics
                ├── services/forgetting_curve.py ← get forgotten topics
                ├── services/week_remediation.py ← store canonical topic names
                ├── services/daily_task.py        ← store week tasks
                ├── services/llm.py               ← generate week plan + quiz
                └── services/quiz.py              ← create quiz in DB
```

---

## File-by-File Breakdown

---

### [controllers/quiz.py](../controllers/quiz.py)
**Role: Main Orchestrator**

This is the entry point for everything. It contains two key functions:

**`submit_weekly_quiz()`** — called when user submits a quiz:
1. Validates every submitted answer belongs to this quiz
2. Deduplicates answers by `pool_group` (prevents double BKT updates if user somehow submits both variants of the same question)
3. Calls `quiz_service.record_attempt()` to save the attempt and score it
4. Runs BKT update on every answered question
5. Updates the bandit arm for this week's content style
6. Unlocks the next week
7. Fires `_generate_next_week()` as a background task

**`_generate_next_week()`** — the background ML task:
1. Fetches weak topics (BKT) and forgotten topics (forgetting curve)
2. Reads the previous week's quiz attempt to find which specific topics failed
3. Calculates how many remediation days are needed
4. Calls LLM to generate the week plan
5. Stores week tasks + canonical topic names
6. Pre-generates next week's quiz

**`submit_quiz()`** — same flow but for the final quiz (week=0). Also runs BKT update so final quiz answers feed back into p_known.

**Connects to:** every service file below.

---

### [services/bkt.py](../services/bkt.py)
**Role: Bayesian Knowledge Tracing Engine**

Tracks how well a user knows each topic as a probability `p_known` (0.0–1.0).

**Key functions:**

**`_bkt_update(p_known, correct, p_transit, p_guess, p_slip)`**
The core math. Called on every quiz answer:
```
If correct:
  posterior = p_known × (1 - p_slip)  ÷  [same + (1-p_known) × p_guess]

If wrong:
  posterior = p_known × p_slip  ÷  [same + (1-p_known) × (1-p_guess)]

new p_known = posterior + (1 - posterior) × p_transit
```
Default parameters per topic row:
- `p_transit = 0.10` — probability user learned even from a wrong answer
- `p_guess   = 0.20` — probability of guessing correctly without knowing
- `p_slip    = 0.10` — probability of answering wrong despite knowing

p_known progression (all correct, starting from 0.10):
| Attempt | p_known | Stability |
|---------|---------|-----------|
| Start   | 0.10    | —         |
| 1 correct | 0.40  | 5 days    |
| 2 correct | 0.775 | 10 days   |
| 3 correct | 0.945 | 10 days   |
| 4 correct | 0.989 | 21 days (mastery) |

**`update_topic_knowledge(skill_id, user_id, answers)`**
Called after every quiz submission. For each (topic, is_correct) pair, fetches or
creates the `TopicKnowledge` row, runs `_bkt_update`, and saves the new p_known
and stability_days.

**`get_weak_topics(skill_id, user_id)`**
Returns all canonical topics where `p_known < 0.95` (MASTERY_THRESHOLD), sorted
weakest first. Filters to canonical topics only — excludes any phantom alias names
like "Reinforcing: Arrays" that BKT may have created before the canonicalization fix.

**`calc_remediation_days(prev_score, days_in_week)`**
Decides how many days of the next week to dedicate to remediation:
- Score 0–39%  → 60% of week days (heavy)
- Score 40–69% → 30% of week days (moderate)
- Score 70–99% → 1 day (light touch)
- Score 100%   → 0 days
- Never consumes all days — always reserves ≥1 for new content

**Connects to:** `models/topic_knowledge.py` (reads/writes), `services/daily_task.py` (gets canonical topic names)

---

### [services/forgetting_curve.py](../services/forgetting_curve.py)
**Role: Spaced Repetition — Finds Topics You're Starting to Forget**

Uses the Ebbinghaus forgetting curve formula:
```
R(t) = e^(-t / S)
```
Where `t` = days since last studied, `S` = stability_days from BKT.

**`get_forgotten_topics(skill_id, user_id)`**
1. Fetches all canonical topic names for the skill
2. For each topic in `TopicKnowledge`, calculates current retention R
3. Returns topics where `R < 0.70` (RETENTION_THRESHOLD), sorted by retention
   **ascending** — most-forgotten topics come first
4. Caller caps the list to 5 (`_FORGOTTEN_WEEK_CAP`) — the most-forgotten 5 only

Why we need this: BKT only tracks whether you got answers right/wrong. It doesn't
account for time. A topic you mastered 3 weeks ago and haven't touched since has
decaying retention even though p_known is high. The forgetting curve catches this.

**Example:** You mastered "Arrays" (p_known=0.99, stability=21d). 25 days later:
`R = e^(-25/21) = 0.30` — only 30% retained, well below the 0.70 threshold.
Arrays comes back into your next week's forgotten list.

**Connects to:** `models/topic_knowledge.py` (reads p_known, stability_days, last_studied_at), `services/daily_task.py` (gets canonical topic names)

---

### [services/bandit.py](../services/bandit.py)
**Role: Thompson Sampling — Learns Which Content Style Works Best For You**

Four arms: `balanced`, `example_heavy`, `theory_first`, `reinforcement`

Each arm has `alpha` (successes) and `beta` (failures), stored in
`content_style_arms` table, starting at `(1, 1)`.

**`sample_style(skill_id, user_id)`**
Draws a random sample from `Beta(alpha, beta)` for each arm. The arm with the
highest draw wins and becomes next week's `content_style`. Arms with more wins
have a higher expected value but still have variance — unexplored arms can
occasionally win, ensuring continued exploration.

**`update_arm(skill_id, user_id, style, improved)`**
Called after every weekly quiz submission:
- `improved=True`  → alpha++ (this style correlated with a score improvement)
- `improved=False` → beta++ (this style did not improve the score)

How `improved` is determined:
- Week 1: `improved = attempt.passed` (no prior weekly score to compare — pass/fail is the signal)
- Week 2+: `improved = current_score > previous_week_best_score`

**Connects to:** `models/content_style_arms.py` (reads/writes alpha, beta)

---

### [services/week_remediation.py](../services/week_remediation.py)
**Role: Canonical Topic Name Storage — The Key to Correct BKT Tagging**

**Why this file exists (the problem it solves):**
When the LLM generates week 2 with remediation days, it names chapters things
like *"Reinforcing: Arrays and Loops"* or *"Deep Dive: Variables"*. Without this
file, quiz questions would be tagged with these alias names. BKT would then create
separate `TopicKnowledge` rows for "Reinforcing: Arrays" and "Arrays" — two
separate knowledge states for the same topic. The forgetting curve would never
find the alias rows. Remediation chains would break.

**`store_remediation_topics(skill_id, week, weak_topics, forgotten_topics)`**
Called right after `store_week_tasks` succeeds. Stores the canonical original
topic names (e.g. "Arrays", "Loops") used when planning this week:
- `weak_topics`    → stored with `topic_type="weak"`
- `forgotten_topics` → stored with `topic_type="forgotten"` (only those not already in weak)
- Deduplicates both lists before insertion to avoid unique constraint violations
- Called AFTER `store_week_tasks` succeeds — so if task storage fails, remediation
  topics are never persisted in an inconsistent state

**`get_canonical_topics_for_week(skill_id, week)`**
Called when building quiz questions. Returns canonical topic names for the week
(weak first, then forgotten), ordered by insertion id for determinism.
These names are used to tag quiz questions so BKT always accumulates on the
original topic.

**`clear_remediation_topics(skill_id)`**
Called on syllabus regeneration to wipe all stored canonical topics — otherwise
old topic names would persist after the course is rebuilt.

**Connects to:** `models/week_remediation_topic.py`, called by `controllers/quiz.py` and `services/quiz.py`

---

### [services/daily_task.py](../services/daily_task.py)
**Role: All DailyTask DB Operations**

Handles reading and writing the `daily_tasks` table — the chapters of the course.

**Key functions relevant to week generation:**

**`store_week_tasks(user_id, skill, skill_id, week, month, daily_plan, hours, remediation_days)`**
Saves the LLM-generated daily plan to the DB. Sorts the plan by day number first,
then flags the first `remediation_days` entries with `is_remediation_day=True`.
This flag is how the system knows which days are LLM-alias days vs original topic days.

**`get_max_day_for_week(skill_id, week)`**
Returns the highest day number stored for a given week. Used to compute the
correct `start_day` for the next week — prevents day number overlap when the
initial LLM syllabus returned a non-standard number of days (e.g. week 1 had 7
days instead of the expected 6, so week 2's arithmetic start_day would collide).

**`get_canonical_topic_names(skill_id)`**
Returns all topic names from non-remediation days only (`is_remediation_day=False`),
order-preserving deduplicated. Used by BKT and forgetting curve to filter their
results to real curriculum topics only — excludes LLM aliases.

**`delete_week_tasks(skill_id, week)`**
Wipes all tasks for a week before storing new ML-generated ones. Called only
after the LLM returns a valid plan, so failure before this point leaves existing
data intact.

**Connects to:** `models/daily_task.py`, called by `controllers/quiz.py`, `services/bkt.py`, `services/forgetting_curve.py`

---

### [services/quiz.py](../services/quiz.py)
**Role: Quiz DB Operations and Topic Mapping**

All database read/write operations for quizzes, questions, and attempts.

**Key functions:**

**`record_attempt(quiz, user_id, answers, questions)`**
Saves the quiz attempt. Calculates score as percentage of correct answers.
If passed, marks quiz status as "passed". None-checks the quiz row before
writing status to handle rare race conditions.

**`get_latest_attempt_results(quiz_id, user_id)`**
Builds the full result breakdown including per-topic scores (`topic_scores`).
Crucially, only includes questions that are in `served_ids` (the user's
submitted answers) — unserved pool variants and unanswered questions are
excluded. This is the function that feeds `remediation_topics` in week generation.

**`build_topic_map(topics, num_questions)`**
Maps pool group numbers to canonical topic names. Guarantees every topic gets
at least one question slot. Extra slots distributed round-robin. Raises
`ValueError` if `num_questions < len(topics)` — prevents the final quiz from
crashing when there are more topics than questions.

**`get_topics_for_week(skill_id, week)`**
Returns canonical topic names for a week's quiz. For remediation weeks, reads
from `WeekRemediationTopic` (canonical names) first, then appends new topic
names from non-remediation `DailyTask` rows. This is what ensures quiz
questions are tagged with original names, not LLM aliases.

**`get_previous_best_score(skill_id, user_id, before_week)`**
Returns the best score from the quiz immediately before the given week.
Used by the bandit to decide if this week's style "improved" the score.

**Connects to:** `models/quiz.py`, `models/quiz_attempt.py`, `models/quiz_question.py`, `models/daily_task.py`, `services/week_remediation.py`

---

### [services/llm.py](../services/llm.py)
**Role: LLM API Calls — Week Plan and Quiz Generation**

**`generate_week_plan(...)`**
Calls the LLM to produce a JSON daily plan for the next week. Receives:
- `weak_topics` — topics to remediate (from last quiz failures)
- `forgotten_topics` — topics to reinforce (from forgetting curve)
- `remediation_days` — how many days to dedicate to review
- `start_day` — correct day number to continue from (computed from DB, not arithmetic)
- `provider`, `api_key`, `model` — user's LLM config

Returns a list of day objects `[{day, topic, task}, ...]` or None on failure.

**`generate_weekly_quiz(...)`**
Generates 5 quiz questions for the upcoming week's topics. Questions are
tagged by topic so BKT can update correctly on submission.

**`generate_final_quiz(...)`**
Generates the full final quiz (10/12/15 questions depending on course length).
Uses the complete weak + forgotten topic list. Supports `pool_size=2` for
non-Mistral providers (generates 2 variants per question for randomized delivery).

**Connects to:** called by `controllers/quiz.py` and `controllers/syllabus.py`

---

## Models (DB Schema)

---

### [models/topic_knowledge.py](../models/topic_knowledge.py)
**Role: BKT State Per User Per Topic**

One row per (skill, user, topic). Stores the full BKT state:
- `p_known` — current mastery probability (starts at 0.10)
- `p_transit`, `p_guess`, `p_slip` — BKT parameters (per-row, can be tuned per topic)
- `stability_days` — from the stability map, drives forgetting curve
- `last_studied_at` — timestamp of last answer, drives forgetting curve decay
- `attempts`, `correct` — raw counts for reference

Why per-row params: future tuning could give harder topics lower `p_transit`
(slower learning rate) without changing global constants.

---

### [models/week_remediation_topic.py](../models/week_remediation_topic.py)
**Role: Canonical Topic Names Per Week — NEW**

One row per (skill, week, topic). Stores the canonical name used when planning
a week, so quiz questions can look it up regardless of what the LLM named the day.

- `topic_type` — `"weak"` or `"forgotten"` (enforced by `CheckConstraint` at DB level)
- `UniqueConstraint` on (skill_id, week, topic) — prevents duplicates

Why we need it: without this, the LLM's alias chapter names would be used to tag
quiz questions, causing BKT rows to split by alias instead of accumulating on
the original topic. Remediation chains would silently break after week 2.

---

### [models/daily_task.py](../models/daily_task.py)
**Role: One Row Per Course Chapter**

Each chapter of the course is a `DailyTask` row.

Key field added: **`is_remediation_day`** (bool, default False)
Set to True for the first N days of an ML-generated week where N = `remediation_days`.
This flag is what `get_canonical_topic_names` uses to exclude alias days from
canonical topic lists. Without it, "Reinforcing: Arrays" would appear in the
canonical list and pollute BKT and forgetting curve queries.

---

### [models/quiz.py](../models/quiz.py)
**Role: One Row Per Quiz**

- `week=0` → final quiz
- `week≥1` → weekly quiz
- `pass_score` → 60 for weekly, 70 for final
- `status` → "available" or "passed"

---

### [models/quiz_question.py](../models/quiz_question.py)
**Role: One Row Per Quiz Question**

- `topic` — the canonical topic name this question tests (populated from `topic_map`)
- `pool_group` — for non-Mistral providers, 2 variants share the same pool_group;
  only one is served per attempt (randomised delivery)
- `position` — ordering within the quiz

---

### [models/quiz_attempt.py](../models/quiz_attempt.py)
**Role: Records Each Quiz Submission**

- `answers` — JSON map of `{question_id: selected_option}`
- `score` — percentage correct
- `passed` — bool

---

## Migration

### [alembic/versions/y3z4a5b6c7d8_fix_topic_canonicalization.py](../alembic/versions/y3z4a5b6c7d8_fix_topic_canonicalization.py)
**Role: DB Schema Changes for ML Pipeline**

Two changes:
1. Adds `is_remediation_day` boolean column to `daily_tasks` (default `false`)
2. Creates `week_remediation_topics` table with UniqueConstraint and CheckConstraint

---

## Complete Week Generation Flow (Step by Step)

```
① User submits Week N quiz
   └── controllers/quiz.py → submit_weekly_quiz()

② Validate answers
   └── Dedup by pool_group (one BKT update per topic slot, not per variant)

③ Record attempt + score
   └── services/quiz.py → record_attempt()
       Builds topic_scores: {topic: {correct, total, pct}}
       Only counts questions in served_ids (unanswered excluded — bug fix)

④ BKT update
   └── services/bkt.py → update_topic_knowledge()
       For each (topic, is_correct): run _bkt_update()
       → new p_known, stability_days, last_studied_at saved to topic_knowledge

⑤ Bandit update
   └── services/bandit.py → update_arm()
       improved = attempt.passed          [week 1: no prior score]
       improved = score > prev_week_score [week 2+]
       → alpha++ or beta++ on the arm used this week

⑥ Sample next week's style
   └── services/bandit.py → sample_style()
       Draw Beta(α,β) for all 4 arms → pick highest → next week's content_style

⑦ Unlock Week N+1
   └── services/skill.py → unlock_next_week()

⑧ Background: _generate_next_week()
   └── controllers/quiz.py

   a) Get all-time weak topics
      └── services/bkt.py → get_weak_topics()
          canonical only, p_known < 0.95, sorted weakest first

   b) Get forgotten topics
      └── services/forgetting_curve.py → get_forgotten_topics()
          R = e^(-t/S), R < 0.70, sorted most-forgotten first
          → CAPPED TO TOP 5

   c) Read Week N quiz attempt (latest)
      └── services/quiz.py → get_latest_attempt_results()
          Returns topic_scores per canonical topic name

   d) Build remediation_topics
      = topics from topic_scores where pct < pass_score AND topic != "General"
      (only failed topics from LAST quiz — not all-time weak)

   e) Fallback if no remediation topics and no prior attempt
      = top 3 BKT weak topics

   f) Calculate remediation days
      └── services/bkt.py → calc_remediation_days(score, days_in_week)
          0-39%  → 60% of days
          40-69% → 30% of days
          70-99% → 1 day
          100%   → 0 days

   g) Generate week plan
      └── services/llm.py → generate_week_plan()
          Inputs: weak_topics, forgotten_topics, remediation_days, start_day
          start_day = get_max_day_for_week(skill_id, week_N) + 1
          (from DB — not arithmetic — prevents day overlap)
          Returns: [{day, topic, task}, ...]

   h) If plan is None → log warning, return (existing week data untouched)

   i) Delete old week data
      └── services/daily_task.py → delete_week_tasks()

   j) Store new week tasks
      └── services/daily_task.py → store_week_tasks()
          Sorts by day number
          Flags first remediation_days entries as is_remediation_day=True
          If returns False → log error, return (don't persist orphaned topics)

   k) Store canonical topic names  ← only after tasks confirmed stored
      └── services/week_remediation.py → store_remediation_topics()
          Deduplicates weak_topics internally
          Stores weak with type="weak", forgotten with type="forgotten"
          These become the lookup table for quiz question topic tagging

   l) Get topics for next week's quiz
      └── services/quiz.py → get_topics_for_week()
          Reads WeekRemediationTopic for canonical names
          Appends new (non-remediation) topic names from DailyTask
          Returns: ["Arrays", "Loops", "New Topic"]

   m) Pre-generate next week's quiz
      └── services/llm.py → generate_weekly_quiz()
          5 questions across the week's topics

   n) Save quiz to DB
      └── services/quiz.py → create_quiz()
          Questions tagged with canonical topic names via topic_map
          pool_size=2 for non-Mistral (2 variants per group for randomisation)
```

---

## Why Each New File Was Needed

| File | Problem It Solves |
|---|---|
| `services/bkt.py` | Nothing was tracking per-topic knowledge state. Every user got the same content regardless of what they knew. |
| `services/forgetting_curve.py` | BKT only updates on quiz answers. Topics you haven't touched in weeks decay in retention — forgetting curve catches this without needing another quiz. |
| `services/bandit.py` | All users were getting the same content style. No learning about which style (theory-first, examples, etc.) works for a specific user. |
| `services/week_remediation.py` | LLM renames remediation chapters with aliases. Without storing canonical names, BKT splits state across the real topic and the alias — breaking the entire remediation feedback loop. |
| `models/week_remediation_topic.py` | DB storage for canonical names. The `CheckConstraint` ensures only valid types reach the DB. `UniqueConstraint` prevents duplicate topic entries per week. |
| `is_remediation_day` on `DailyTask` | Without this flag, `get_canonical_topic_names` would include alias day names in its list. BKT and forgetting curve would then operate on alias names, not real topics. |
| `get_max_day_for_week` in `daily_task.py` | The initial LLM syllabus can return a non-standard number of days per week. Arithmetic `start_day` calculation would overlap with existing day numbers. This reads the actual last day from DB. |
