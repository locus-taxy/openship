# ML Approach - Adaptive Syllabus Without Historical Data

## Overview

**What this doc proposes:** Instead of generating the full syllabus upfront, generate one week at a time. After each week the user takes a short quiz. Three ML algorithms assess the results and automatically adapt what gets taught next week, at what pace, and in which style. The final course quiz is also personalised to the user's weak topics - not based on enrollment settings.

**What changes:**
- 2 new DB tables (`topic_knowledge`, `content_style_arms`)
- 1 new table (`week_remediation_topics`) — stores canonical topic names for remediation weeks
- 1 new column on `quiz_questions` (topic tag per question)
- 1 new column on `daily_tasks` (`is_remediation_day`) — flags review/revision days
- Small additions to `skills` and `quizzes` tables
- Difficulty removed from enrollment - the ML figures this out automatically

**What stays the same:** auth, LLM provider setup, daily content structure, streaks, public sharing - none of this is touched.

---

## The Problem

Most ML systems need thousands of data points before they start working. We have zero - a brand new user has no history at all.

But there is a class of ML algorithms designed to **start from a reasonable guess and update after every single observation**. They learn as the user uses the product.

We use three of them:

| # | Algorithm | What it answers |
|---|---|---|
| 1 | Bayesian Knowledge Tracing (BKT) | How well does the user know each topic? |
| 2 | Multi-Armed Bandit (MAB) | What teaching style works best for this user? |
| 3 | Ebbinghaus Forgetting Curve | Which topics is the user about to forget? |

---

## Prerequisite: One Change to `quiz_questions`

All three algorithms depend on knowing **which topic each quiz question is testing**. The existing table does not store this.

### Current table

| Column | Type | Purpose |
|---|---|---|
| id | int | primary key |
| quiz_id | int | which quiz this question belongs to |
| position | int | question number (1, 2, 3 …) |
| question | text | the question text |
| option_a/b/c/d | text | the four answer choices |
| correct_option | str | `"A"`, `"B"`, `"C"`, or `"D"` |
| explanation | text | why the correct answer is correct |

**Problem:** when the user answers wrong, we have no idea what to mark as weak - we don't know which topic the question was testing.

### New column

| Column | Type | Purpose |
|---|---|---|
| **topic** | text | the `DailyTask.topic` this question tests (e.g. `"Loops"`, `"Functions"`) |

When we generate the per-week quiz, we tag each question with the topic it tests. This is the link between a wrong answer → a topic → the ML algorithms.

**Example row after the change:**

```
quiz_id:        5
position:       2
question:       "What does a for loop do in Python?"
option_a:       "Defines a function"
option_b:       "Repeats a block of code"   ← correct
option_c:       "Creates a variable"
option_d:       "Imports a module"
correct_option: "B"
topic:          "Loops"                     ← NEW
```

---

## Algorithm 1 - Bayesian Knowledge Tracing (BKT)

### What problem does it solve?

After a quiz, we need to answer: **how well does this user actually know each topic?**

A simple percentage score is not enough:
- The user might have **guessed** a correct answer
- The user might have **slipped** on a topic they actually know
- Two wrong answers in a row means something different from one wrong answer

BKT tracks a probability per topic: *"What is the chance this user has truly learned this topic?"* It accounts for both guessing and slipping.

**Output:** a `p_known` score per topic - exactly what the LLM needs to know which topics to reinforce next week.

---

### The 4 Parameters

No training data needed. These are starting assumptions from published educational research.

| Parameter | Default | Meaning |
|---|---|---|
| P(L₀) - initial knowledge | `0.10` | User starts not knowing the topic |
| P(T) - learn rate | `0.10` | Each question is a 10% chance to learn the topic |
| P(G) - guess rate | `0.20` | 20% chance of correct answer without knowing |
| P(S) - slip rate | `0.10` | 10% chance of wrong answer even if user knows it |

---

### Update Formula

After every question answer, `p_known` is updated:

```
Correct answer:
  p_known = (p_known × (1 - slip)) ÷ (p_known × (1 - slip) + (1 - p_known) × guess)

Wrong answer:
  p_known = (p_known × slip) ÷ (p_known × slip + (1 - p_known) × (1 - guess))

Then apply learning opportunity (runs after both cases):
  p_known = p_known + (1 - p_known) × learn_rate
```

10 lines of Python. No external library needed.

---

### Mastery Threshold

| Score | Status | Action |
|---|---|---|
| `p_known >= 0.95` | Mastered | No reinforcement needed next week |
| `p_known < 0.95` | Weak | Topic passed into next week's LLM prompt |

With the default params, a topic reaches mastery after ~4 correct consecutive answers (p_known ≈ 0.989).

---

### Stability Mapping (used by Forgetting Curve)

After each BKT update, `stability_days` is set based on `p_known`:

| `p_known` | `stability_days` | Memory lasts |
|---|---|---|
| `≥ 0.95` (mastered) | 21 days | ~3 weeks |
| `≥ 0.70` (good) | 10 days | ~10 days |
| `≥ 0.40` (partial) | 5 days | ~5 days |
| `≥ 0.0` (including start at 0.10) | 2 days | ~2 days |

---

### New Table: `topic_knowledge`

Stores the BKT state for every topic, for every user, for every skill.

| Column | Type | Set by | Purpose |
|---|---|---|---|
| id | int | DB | primary key |
| skill_id | int | system | FK → `skills.id` |
| user_id | int | system | FK → `users.id` |
| topic | str | system | topic name - matches `DailyTask.topic` |
| week | int | system | which week this topic was first introduced |
| p_known | float | BKT | probability user knows this topic (starts at `0.10`) |
| attempts | int | BKT | total questions answered on this topic |
| correct | int | BKT | how many were correct |
| p_transit | float | config | learn rate (default `0.10`) |
| p_guess | float | config | guess rate (default `0.20`) |
| p_slip | float | config | slip rate (default `0.10`) |
| last_studied_at | datetime | Forgetting Curve | when topic was last quizzed |
| stability_days | float | Forgetting Curve | memory stability - derived from `p_known` |

> **Unique constraint:** `(skill_id, user_id, topic)` - one row per topic per user per course.

**How it connects to other tables:**

```
skills ──── topic_knowledge ──── users
              │
              │ topic column matches
              ▼
           daily_tasks.topic
              │
              │ topic column matches
              ▼
           quiz_questions.topic
```

**Example rows after a week 1 quiz:**

```
skill_id  user_id  topic        week  p_known  attempts  correct
1         42       Variables    1     0.92     3         3        ← nearly mastered
1         42       Loops        1     0.43     3         1        ← weak, needs review
1         42       Functions    1     0.71     2         1        ← partial
```

---

## Algorithm 2 - Multi-Armed Bandit (MAB)

### What problem does it solve?

Different people learn in different ways. Some learn best from code examples first. Others need theory before touching code. Others need slow repetition.

We want to find **which teaching style works best for each individual user** - but we can't ask them, and we don't know at the start.

A Multi-Armed Bandit solves exactly this: *"I have several options. I don't know which is best. How do I find out without wasting too many tries on bad options?"*

---

### Why "bandit"?

Think of a row of slot machines (one-armed bandits). Each machine has a different payout rate, but you don't know what it is. You try different machines, learn which pays best, and gradually spend more time on the winning ones.

In our case:

| Slot machine analogy | Our system |
|---|---|
| Each machine | A content generation **style** (called an "arm") |
| Pulling the arm | Generating a week of content in that style |
| Winning | The user's quiz score improves week over week |

---

### The 4 Arms (Content Styles)

Each style injects **mandatory structural rules** into the LLM system prompt - not just a description, but hard ordering constraints that force the LLM to produce genuinely different output.

| Arm | Structural rule enforced |
|---|---|
| `balanced` | Strict alternation: heading → paragraph (explain) → code (demonstrate). Equal paragraph/code count. Must include at least one `note` block for caveats. After every code block, a paragraph explains what it does and why. |
| `example_heavy` | After every heading, the next block MUST be `code` - never a paragraph. Paragraph always follows code, never precedes it. At least 4 code blocks total. Code blocks must be more than 50% of all content blocks. |
| `theory_first` | After every heading, the next block MUST be a `paragraph` with a precise definition - code blocks only appear after full explanation. Pattern enforced: heading → paragraph (definition) → paragraph (elaboration) → code (illustration). Must include at least one `table` block comparing related concepts. |
| `reinforcement` | Mandatory `note` block after every major section (minimum 2 total). One `quote` block per chapter. A `bullet_list` recap mid-chapter (not just at end). The single most important concept appears twice - once in a paragraph, once in a code block - using different wording. |

The style rules are placed at the **end** of the system prompt (after all block-type definitions), so they are the last thing the LLM reads before generating - this maximises compliance. The rules are injected via `prompts/chapter.py: system_prompt(style=style)`.

`balanced` has explicit structural rules just like every other style - it is not a no-op default.

---

### How Thompson Sampling Works

Each arm has two counters: `alpha` (wins) and `beta` (losses). Both start at `1`.

**The style is sampled once per week - not once per chapter.**

This is a critical design decision: the bandit's reward signal is the weekly quiz score. If chapters within the same week used different styles, there would be no way to attribute a score improvement to any one style - the reward signal becomes noise. By locking the style for the entire week, every chapter the user reads that week has the same structural teaching approach, and the quiz result cleanly reflects whether that approach worked.

**How one week works:**
1. User generates the first chapter of week N
2. `controllers/content.py: generate_chapter()` calls `get_week_content_style(skill_id, week)` - returns `None` (no chapters generated for this week yet)
3. `sample_style()` runs Thompson Sampling across all 4 arms → picks e.g. `theory_first`
4. Chapter is generated with `theory_first` structural rules and saved with `content_style = "theory_first"`
5. User generates chapters 2, 3, 4… of week N
6. `get_week_content_style()` finds that week N already has `content_style = "theory_first"` → reuses it, no re-sampling
7. All chapters in week N are generated with `theory_first`
8. User takes the weekly quiz → score determined → `update_arm("theory_first", improved)` runs
9. Week N+1 first chapter → `get_week_content_style()` returns `None` again → fresh `sample_style()` with updated Beta distributions

**The `improved` signal — critical distinction:**

```
Week 1: no previous score exists
  → improved = attempt.passed   (True if score ≥ pass_score=60, else False)
  → reason: no prior score to compare against; pass/fail is the only signal available

Week 2+: previous weekly quiz score exists
  → improved = (this_week_score > prev_week_score)   (strict improvement)
  → reason: the user has a baseline — we reward beating it, not just passing
```

**Where this runs in code:**
- `services/daily_task.py: get_week_content_style(skill_id, week)` - queries `daily_tasks` for the style already used this week
- `services/bandit.py: sample_style()` - called only when `get_week_content_style` returns `None` (first chapter of the week)
- `services/bandit.py: update_arm()` - called in `controllers/quiz.py: submit_weekly_quiz()` with the `improved` boolean
- The used style is persisted on `daily_tasks.content_style` and shown as a badge in the UI

**Example: 5 weeks for one user**

```
Week 1: all arms at Beta(1,1) → sample → "balanced" → ALL 7 chapters use balanced
        quiz score: 65% (pass_score=60) → passed=True → improved=True
        update_arm("balanced", improved=True) → balanced: alpha=2

Week 2: balanced favoured → sample → "example_heavy" → ALL chapters use example_heavy
        quiz score: 58% → improved = (58 > 65) = False
        update_arm("example_heavy", improved=False) → example_heavy: beta=2

Week 3: example_heavy penalised → sample → "theory_first"
        quiz score: 78% → improved = (78 > 58) = True
        update_arm("theory_first", improved=True) → theory_first: alpha=2

Week 4: theory_first favoured → sample → "theory_first" again
        quiz score: 81% → improved = (81 > 78) = True
        update_arm("theory_first", improved=True) → theory_first: alpha=3

Week 5: theory_first strongly favoured → sample → "theory_first"
        quiz score: 85% → improved = (85 > 81) = True → theory_first: alpha=4
```

After 5 weeks the system has learned this user is a **theory-first learner**.

---

### New Table: `content_style_arms`

Stores the bandit state for every style, for every user, for every skill.

| Column | Type | Purpose |
|---|---|---|
| id | int | primary key |
| skill_id | int | FK → `skills.id` |
| user_id | int | FK → `users.id` |
| style | str | `"balanced"`, `"example_heavy"`, `"theory_first"`, `"reinforcement"` |
| alpha | float | wins + 1 (starts at `1.0`) |
| beta | float | losses + 1 (starts at `1.0`) |

> **Unique constraint:** `(skill_id, user_id, style)` - one row per style per user per course.
>
> **When created:** 4 rows inserted when a user generates week 1 - one per style, all at `alpha=1, beta=1`.

**Example rows after 5 weeks (same user as above):**

```
skill_id  user_id  style           alpha  beta
1         42       balanced        2.0    1.0    ← tried once, improved
1         42       example_heavy   1.0    2.0    ← tried once, no improvement
1         42       theory_first    4.0    1.0    ← tried three times, all improved ← WINNER
1         42       reinforcement   1.0    1.0    ← never tried yet
```

---

## Algorithm 3 - Ebbinghaus Forgetting Curve

### What problem does it solve?

Even if a user scored well on week 1, they will start forgetting those topics over time. We need to know **which topics from previous weeks the user is about to forget**, so we can add a short review at the start of next week's content.

This gives the user automatic spaced repetition without them having to think about it.

---

### The Formula

In 1885, Hermann Ebbinghaus measured how fast people forget things and found memory decays in a predictable pattern:

```
R(t) = e^(-t / S)

R = retention  (1.0 = perfect recall,  0.0 = completely forgotten)
t = days since the topic was last studied
S = stability  (how long the memory lasts - depends on how well it was learned via BKT)
```

If `R < 0.70` (30% or more forgotten), the topic is flagged for review.

---

### Setting Stability (S)

BKT's `p_known` score tells us how well the user learned the topic. We use it to set S (see stability mapping table in Algorithm 1 above).

---

### Example

User studied "Loops" in week 1. BKT gave `p_known = 0.43` → S = 5 days.

By the start of week 2 (7 days later):

```
R(7) = e^(-7/5) = e^(-1.4) ≈ 0.25
```

Only **25% retention** - the user has mostly forgotten Loops. A review task gets added to week 2.

---

### Forgotten Topics Cap

Forgotten topics are sorted ascending by retention (most-forgotten first). To keep weeks manageable, only the **top 5 most-forgotten topics** are included in any single weekly plan (`_FORGOTTEN_WEEK_CAP = 5`). The final quiz has no such cap — it includes all forgotten topics, subject only to the overall question count limit.

---

### No New Table - Two New Columns on `topic_knowledge`

The forgetting curve state lives on the same `topic_knowledge` table as BKT. We add:

| Column | Type | Purpose |
|---|---|---|
| last_studied_at | datetime | when this topic was last in a quiz (used to compute `t`) |
| stability_days | float | S value, derived from `p_known` after each quiz |

---

## Topic Canonicalisation — Preventing Phantom BKT Rows

### The Problem

When a remediation week is generated, the LLM names the revision chapter something like *"Reinforcing: Arrays"* rather than the original topic name *"Arrays"*. If we tag quiz questions with this alias name, BKT creates a phantom row for `"Reinforcing: Arrays"` instead of updating the real `"Arrays"` row. The user's real knowledge state is never updated.

### The Solution — Two New Things

**1. `is_remediation_day` column on `daily_tasks` (bool, default False)**

Set to `True` for all revision/reinforcement chapters. These days are excluded when building the canonical topic list.

**2. `week_remediation_topics` table**

When a week is planned, the original canonical topic names (from BKT/forgetting curve) are stored here before the LLM generates its alias names.

| Column | Type | Purpose |
|---|---|---|
| id | int | primary key |
| skill_id | int | FK → `skills.id` |
| week | int | which week these topics are for |
| topic | str | canonical topic name (e.g. `"Arrays"`) |
| topic_type | str | `"weak"` or `"forgotten"` |

**Unique constraint:** `(skill_id, week, topic)` — one row per topic per week.
**Check constraint:** `topic_type IN ('weak', 'forgotten')`.

**How it is used:**

`get_topics_for_week(skill_id, week)` builds the quiz topic list by:
1. Fetching canonical names from `week_remediation_topics` (remediation topics)
2. Fetching new topics from `daily_tasks WHERE is_remediation_day = False` (new content topics)

This ensures quiz questions are always tagged with the real topic name, keeping BKT accurate.

---

## How All Three Work Together

### Complete End-to-End Flow

```
USER GENERATES A CHAPTER
  └─ controllers/content.py: generate_chapter()
       ├─ get_week_content_style(skill_id, week)   ← reuse style if week already started
       │    └─ if None (first chapter of this week):
       │         └─ sample_style(skill_id, user_id) ← Bandit samples a new style
       └─ generate_chapter_content(style=style)    ← LLM writes the chapter with that style
            └─ prompts/chapter.py: system_prompt(style=style)
                 ├─ Adds mandatory structural style rules at end of prompt
                 └─ Adds "Key Takeaways" block at end

USER READS CHAPTER AND TAKES WEEKLY QUIZ
  └─ controllers/quiz.py: submit_weekly_quiz()
       ├─ records the quiz attempt in DB
       │
       ├─ update_topic_knowledge(answers)           ← BKT updates p_known per topic
       │    └─ Also sets stability_days and last_studied_at
       │
       ├─ prev_score = get_previous_best_score()
       ├─ improved = attempt.passed            (week 1: no prev score, use pass/fail)
       │            OR attempt.score > prev_score  (week 2+: strict improvement)
       ├─ stored_style = get_week_content_style() for THIS week
       ├─ update_arm(stored_style, improved)        ← Bandit learns: did that style help?
       └─ unlock_next_week() → triggers _generate_next_week() in background

BACKGROUND: NEXT WEEK IS GENERATED
  └─ controllers/quiz.py: _generate_next_week()
       ├─ remediation_topics = topics where pct < pass_score in LAST quiz attempt
       │    (only failed topics from last quiz — not all-time weak)
       │    (filters out "General" topic)
       ├─ forgotten = get_forgotten_topics()        ← Forgetting curve: topics decaying
       │    └─ capped to top 5 most-forgotten (_FORGOTTEN_WEEK_CAP = 5)
       ├─ next_style = sample_style()              ← Bandit picks next week's style
       ├─ calc_remediation_days(prev_score)         ← how many days to spend reviewing
       │    0–39% score → 60% of days
       │    40–69% score → 30% of days
       │    70–99% score → 1 day
       │    100% score → 0 days
       │    always reserves ≥ 1 day for new content
       ├─ generate_week_plan(remediation_topics, forgotten, next_style, remediation_days)
       │    └─ LLM writes a personalised day-by-day plan (remediation days flagged)
       ├─ store_week_tasks() → saves DailyTask rows with is_remediation_day flag
       └─ store_remediation_topics() → saves canonical names to week_remediation_topics

PRE-GENERATE NEXT WEEK'S QUIZ (after tasks are stored)
  └─ get_topics_for_week()
       ├─ canonical remediation topics from week_remediation_topics
       └─ new content topics from daily_tasks WHERE is_remediation_day = False
  └─ num_questions = len(topics)   ← exactly 1 question per topic
  └─ generate_weekly_quiz() → LLM generates questions in topic order
  └─ topic_map = build_topic_map(topics)   ← {pool_group → topic_name}
  └─ create_quiz() → stamps each question with its topic name

USER FINISHES ALL WEEKS AND GENERATES FINAL QUIZ
  └─ controllers/quiz.py: generate_quiz_for_skill()
       ├─ weak = get_weak_topics()           ← ALL-TIME weak topics (p_known < 0.95)
       ├─ forgotten = get_forgotten_topics() ← ALL forgotten topics (no cap here)
       ├─ all_for_map = weak + forgotten (deduped)
       ├─ cap to max_questions:
       │    ≤ 30 days course → 10 questions max
       │    ≤ 60 days course → 12 questions max
       │    90+ days course → 15 questions max
       ├─ num_questions = len(all_for_map)  ← 1 question per topic after capping
       └─ generate_final_quiz(weak, forgotten, topic_week_map)
            └─ prompts/quiz.py: final_user_prompt() with clustered topics
                 └─ LLM writes: "Week 2: Variables, Loops - Week 4: Recursion, Trees"
```

---

This is the step-by-step breakdown of what runs at each stage:

**Step 1 - BKT (run immediately after quiz submission)**

For every question the user answered:
- Look up `question.topic`
- Find the `topic_knowledge` row for that topic
- Run the BKT formula → update `p_known`
- Update `last_studied_at` and `stability_days`

Result: we know exactly which topics are weak (`p_known < 0.95`)

---

**Step 2 - Forgetting Curve (run for all previous weeks)**

For every topic the user has ever studied (not just this week):
- Compute `R = e^(-days_since_last_studied / stability_days)`
- If `R < 0.70` → add to "needs review" list
- Sort by retention ascending (most-forgotten first)

Result: we know which old topics the user is about to forget

---

**Step 3 - Bandit (run after score is known)**

- Week 1: `improved = attempt.passed` (no prior score to compare)
- Week 2+: `improved = (this_week_score > prev_week_score)`
- If improved → `alpha + 1` for the style used this week
- If not improved → `beta + 1` for the style used this week
- Thompson-sample all 4 arms → pick the style for next week

Result: we know which teaching style to use next week

---

**Step 4 - Generate next week's content**

All three results are combined into one LLM prompt:

| Input | Source | Instruction to LLM |
|---|---|---|
| Remediation topics | Last quiz failed topics only | "Reinforce these topics — they failed last quiz" |
| Forgotten topics | Forgetting Curve (capped at 5) | "Add a short review task for each of these" |
| Remediation days | `calc_remediation_days(score)` | "Spend N days revisiting before new material" |
| New topics for next week | Syllabus progression | "Also introduce these new topics" |

---

**Step 5 - Chapter content style (Bandit, locked per week)**

Every time the user requests a chapter to be generated:
- `get_week_content_style(skill_id, week)` checks if any chapter this week already has a style set
- If yes → reuse it (all chapters in the same week share one style)
- If no (first chapter of the week) → `sample_style(skill_id, user_id)` samples all 4 Beta distributions and picks a winner
- The winning style is injected into the chapter LLM prompt as **mandatory structural rules** (placed at the end of the prompt for recency bias)
- The LLM writes the chapter body following those structural constraints
- `content_style` is saved on `daily_tasks` and shown as a badge in the UI

This is separate from week plan generation - the bandit influences both **what topics** are covered (via week plan) and **how each chapter is written** (via per-week style locking). Locking the style per week ensures the weekly quiz score can be cleanly attributed to a single teaching approach when updating the bandit's Beta distributions.

---

**Final Quiz - personalised by ML, grouped by course week**

Once the user completes all weeks:
- Collect every topic where `p_known < 0.95` across all weeks (BKT) — all-time weak
- Also include topics where forgetting curve `R < 0.70` — all forgotten (no weekly cap)
- Cap total: 10 (≤30d course), 12 (≤60d), 15 (≤90d)
- Exactly 1 question per topic → pct per topic is always 0 or 100
- Map each topic to the week it was taught → `get_topic_week_map()`
- Send grouped data to LLM: *"Week 1: Variables, Loops - Week 3: Recursion - Week 4: Trees"*
- LLM generates questions knowing the course structure and which areas need the most work

> The final quiz is **not** generated from enrollment topics. It is completely personalised by what BKT and the Forgetting Curve found across the entire course. The week grouping gives the LLM context about topic relationships and course progression.

---

## Weekly Quiz — 1 Question Per Topic

All weekly quizzes (pre-generated at syllabus creation, manually triggered, or auto-generated after quiz submission) use exactly **1 question per topic**. This means:

- pct per topic is always 0 (wrong) or 100 (correct) — never ambiguous 50%
- `remediation_topics` = simply every topic the user got wrong in the last quiz
- No minimum question floor — a week with 4 topics gets 4 questions

For non-Mistral providers, `pool_size=2` means 2 variant phrasings are generated per topic but only 1 is served. The 2 variants exist for anti-memorisation retakes, not to increase the question count.

---

## Enrollment Change - Difficulty Removed

Currently during enrollment the user selects a **difficulty level** (beginner / intermediate / advanced). This was used to set the quiz pass score and influence content generation.

With the ML approach, difficulty becomes unnecessary:
- The **Bandit** automatically discovers the right teaching style for the user - there is no need to ask them upfront
- The **BKT** tracks per-topic mastery and adapts content accordingly - a "beginner" label adds no information the ML doesn't already capture
- The **final quiz** is personalised by ML, not by a difficulty setting

**Decision:** remove the `difficulty` field from the enrollment flow. The `quiz_difficulty` column on the `skills` table and the `difficulty` column on the `quizzes` table will be removed as part of this implementation.

---

## Summary of All DB Changes

### `quiz_questions` - two new columns

| Column | Type | Purpose |
|---|---|---|
| `topic` | text | which `DailyTask.topic` this question tests - links wrong answers to BKT/forgetting curve |
| `pool_group` | int (nullable) | variant group number - see Quiz Variant Pool below |

### `daily_tasks` - one new column

| Column | Type | Purpose |
|---|---|---|
| `is_remediation_day` | bool (default False) | flags revision/reinforcement days so their LLM-generated names are excluded from canonical topic lists |

### `topic_knowledge` - new table

One row per topic per user per skill. Owned by BKT + Forgetting Curve.

### `content_style_arms` - new table

Four rows per user per skill (one per style). Owned by the Bandit.

### `week_remediation_topics` - new table

Stores canonical weak/forgotten topic names used when planning each ML-generated week. Used by `get_topics_for_week()` to ensure quiz questions are tagged with real topic names, not LLM-generated aliases.

| Column | Type | Purpose |
|---|---|---|
| `id` | int | primary key |
| `skill_id` | int | FK → `skills.id` (CASCADE) |
| `week` | int | which week these topics are remediation for |
| `topic` | str (max 255) | canonical topic name |
| `topic_type` | str (`"weak"` or `"forgotten"`) | type of remediation |

### `skills` - changes

| Change | Detail |
|---|---|
| Add `generated_weeks` (int) | how many weeks have been generated so far |
| Add `total_weeks` (int) | total weeks in this plan (set on first generation) |
| Remove `quiz_difficulty` | no longer needed - Bandit replaces this |

### `quizzes` - changes

| Change | Detail |
|---|---|
| Add `week` (int) | `0` = final quiz, `1–N` = per-week quiz |
| Remove `difficulty` | no longer needed |
| Constraint | `UNIQUE(skill_id)` → `UNIQUE(skill_id, week)` |


---

## Additional Features

### Key Takeaways Block

Every chapter now ends with two mandatory blocks (enforced in `prompts/chapter.py`):

1. A `heading` block (level 2) with content `"Key Takeaways"`
2. A `bullet_list` block with 4–6 points summarising what the reader just learned

This is hardcoded into the LLM system prompt - the LLM must include it or the Pydantic validator rejects the response. It gives students a consistent review section at the end of every chapter and reinforces learning through summarisation.

---

### Weak Topic Clustering for Final Quiz

**Problem:** the old prompt passed weak topics as a flat numbered list. The LLM had no idea which week a topic came from or how topics related to each other.

**Solution:** `services/quiz.py: get_topic_week_map(skill_id, topics)` queries the `daily_tasks` table to find which week each topic was taught. The final quiz prompt groups them:

```
# Before
"The student struggled with: Variables, Loops, Recursion, Trees"

# After
"The student struggled with (grouped by week):
 Week 1: Variables, Loops
 Week 3: Recursion
 Week 4: Trees, Binary Search"
```

This tells the LLM three things it couldn't infer before:
- Which topics are conceptually related (same week = same theme)
- Which are foundational vs advanced (week 1 vs week 4)
- How to weight difficulty - week 1 topics still not mastered are a bigger gap than week 4 topics

**Files:** `services/quiz.py` (new `get_topic_week_map`), `prompts/quiz.py` (updated `final_user_prompt`), `services/llm.py` (new `topic_week_map` param), `controllers/quiz.py` (builds and passes the map)

---

### Quiz Question Variant Pool (Anti-Memorisation)

**Problem:** when a user retakes a quiz, they see the exact same questions in the same order. After 2–3 attempts they can memorise answers without understanding the topic - which breaks BKT's accuracy (the model thinks they're improving when they're just memorising).

**Solution:** for each unique question slot, the LLM now generates multiple variant phrasings of the same question. On every quiz attempt, `get_quiz_with_questions()` randomly picks one variant per slot. The student sees a fresh version each time.

**How it works:**

| Provider | `pool_size` | Variants generated per topic | Questions shown per attempt |
|---|---|---|---|
| Gemini | `2` | 2 | 1 per topic (one variant randomly served) |
| OpenAI | `2` | 2 | 1 per topic |
| Anthropic | `2` | 2 | 1 per topic |
| Mistral | `1` | 1 | 1 per topic (no variants - hard token cap) |

In the database, variants share the same `pool_group` integer on `quiz_questions`:

```
pool_group=1, question="What does a for loop do?"          ← variant A  (topic: Loops)
pool_group=1, question="Which statement repeats a block?"  ← variant B  (topic: Loops)
pool_group=2, question="What is a function?"               ← variant A  (topic: Functions)
pool_group=2, question="Which keyword defines a function?" ← variant B  (topic: Functions)
```

`get_quiz_with_questions()` runs `random.choice(variants)` for each group → the student sees a different question every retake.

**Why Mistral stays at pool_size=1:** Mistral Small has an 8 192 output token hard cap that it enforces strictly - exceeding it truncates the JSON mid-stream and triggers `IncompleteOutputException`. Quiz question JSON is short enough that Gemini, OpenAI, and Anthropic handle `N × 2` questions comfortably within their output limits (32 768 / 16 384 / 8 192 tokens respectively - quiz output is far smaller than chapter content).

**Files:** `models/quiz_question.py` (new `pool_group` column), `alembic/versions/o3p4q5r6s7t8_add_pool_group_to_quiz_questions.py` (migration), `services/quiz.py` (`create_quiz` assigns pool groups, `get_quiz_with_questions` samples), `services/llm.py` (new `pool_size` param on both quiz generators), `controllers/quiz.py` (sets `pool_size` per provider, passes through)
