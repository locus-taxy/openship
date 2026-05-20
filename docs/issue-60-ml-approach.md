# ML Approach — Adaptive Syllabus Without Historical Data

## Overview

**What this doc proposes:** Instead of generating the full syllabus upfront, generate one week at a time. After each week the user takes a short quiz. Three ML algorithms assess the results and automatically adapt what gets taught next week, at what pace, and in which style. The final course quiz is also personalised to the user's weak topics — not based on enrollment settings.

**What changes:**
- 2 new DB tables (`topic_knowledge`, `content_style_arms`)
- 1 new column on `quiz_questions` (topic tag per question)
- Small additions to `skills` and `quizzes` tables
- Difficulty removed from enrollment — the ML figures this out automatically

**What stays the same:** auth, LLM provider setup, daily content structure, streaks, public sharing — none of this is touched.

---

## The Problem

Most ML systems need thousands of data points before they start working. We have zero — a brand new user has no history at all.

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

**Problem:** when the user answers wrong, we have no idea what to mark as weak — we don't know which topic the question was testing.

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

## Algorithm 1 — Bayesian Knowledge Tracing (BKT)

### What problem does it solve?

After a quiz, we need to answer: **how well does this user actually know each topic?**

A simple percentage score is not enough:
- The user might have **guessed** a correct answer
- The user might have **slipped** on a topic they actually know
- Two wrong answers in a row means something different from one wrong answer

BKT tracks a probability per topic: *"What is the chance this user has truly learned this topic?"* It accounts for both guessing and slipping.

**Output:** a `p_known` score per topic — exactly what the LLM needs to know which topics to reinforce next week.

---

### The 4 Parameters

No training data needed. These are starting assumptions from published educational research.

| Parameter | Default | Meaning |
|---|---|---|
| P(L₀) — initial knowledge | `0.10` | User starts not knowing the topic |
| P(T) — learn rate | `0.10` | Each question is a 10% chance to learn the topic |
| P(G) — guess rate | `0.20` | 20% chance of correct answer without knowing |
| P(S) — slip rate | `0.10` | 10% chance of wrong answer even if user knows it |

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

---

### New Table: `topic_knowledge`

Stores the BKT state for every topic, for every user, for every skill.

| Column | Type | Set by | Purpose |
|---|---|---|---|
| id | int | DB | primary key |
| skill_id | int | system | FK → `skills.id` |
| user_id | int | system | FK → `users.id` |
| topic | str | system | topic name — matches `DailyTask.topic` |
| week | int | system | which week this topic was first introduced |
| p_known | float | BKT | probability user knows this topic (starts at `0.10`) |
| attempts | int | BKT | total questions answered on this topic |
| correct | int | BKT | how many were correct |
| p_transit | float | config | learn rate (default `0.10`) |
| p_guess | float | config | guess rate (default `0.20`) |
| p_slip | float | config | slip rate (default `0.10`) |
| last_studied_at | datetime | Forgetting Curve | when topic was last quizzed |
| stability_days | float | Forgetting Curve | memory stability — derived from `p_known` |

> **Unique constraint:** `(skill_id, user_id, topic)` — one row per topic per user per course.

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

## Algorithm 2 — Multi-Armed Bandit (MAB)

### What problem does it solve?

Different people learn in different ways. Some learn best from code examples first. Others need theory before touching code. Others need slow repetition.

We want to find **which teaching style works best for each individual user** — but we can't ask them, and we don't know at the start.

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

| Arm | Style | What the LLM generates |
|---|---|---|
| `balanced` | Equal mix of theory and examples | Default starting style |
| `example_heavy` | Code examples first, theory after | For hands-on learners |
| `theory_first` | Full explanation before any code | For conceptual learners |
| `reinforcement` | Slower pace, more repetition | For struggling users |

---

### How Thompson Sampling Works

Each arm has two counters: `alpha` (wins) and `beta` (losses). Both start at `1`.

**Before generating each week's content:**
1. For each arm, draw a random number from `Beta(alpha, beta)`
2. Pick the arm with the highest draw
3. Generate the week's content in that style
4. After the quiz: if score improved → `alpha + 1`, if not → `beta + 1`

The Beta distribution naturally balances **exploration** (trying new styles) and **exploitation** (using the style that's working). Arms with more wins produce higher draws more often — but occasionally an untried arm gets lucky and gets explored.

**Example: 5 weeks for one user**

```
Week 1: all arms at Beta(1,1) → random pick → "balanced"
        quiz score: 65%

Week 2: all arms still equal → random pick → "example_heavy"
        quiz score: 72% (+7%, improved) → example_heavy: alpha=2, beta=1

Week 3: example_heavy slightly favoured → "example_heavy" again
        quiz score: 68% (-4%, dropped) → example_heavy: alpha=2, beta=2

Week 4: example_heavy and balanced now equal → "theory_first" not yet tried
        exploration kicks in → picks "theory_first"
        quiz score: 81% (+13%, improved) → theory_first: alpha=2, beta=1

Week 5: theory_first now favoured → "theory_first"
        quiz score: 85% (+4%, improved) → theory_first: alpha=3, beta=1
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

> **Unique constraint:** `(skill_id, user_id, style)` — one row per style per user per course.
>
> **When created:** 4 rows inserted when a user generates week 1 — one per style, all at `alpha=1, beta=1`.

**Example rows after 5 weeks (same user as above):**

```
skill_id  user_id  style           alpha  beta
1         42       balanced        1.0    2.0    ← tried once, no improvement
1         42       example_heavy   2.0    2.0    ← tried twice, mixed results
1         42       theory_first    3.0    1.0    ← tried twice, both improved ← WINNER
1         42       reinforcement   1.0    1.0    ← never tried yet
```

---

## Algorithm 3 — Ebbinghaus Forgetting Curve

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
S = stability  (how long the memory lasts — depends on how well it was learned)
```

If `R < 0.70` (30% or more forgotten), a review task is injected into next week's content.

---

### Setting Stability (S)

BKT's `p_known` score tells us how well the user learned the topic. We use it to set S:

| BKT `p_known` | Stability S | Memory lasts |
|---|---|---|
| `≥ 0.95` (mastered) | 21 days | ~3 weeks |
| `0.70 – 0.94` (good) | 10 days | ~10 days |
| `0.40 – 0.69` (weak) | 5 days | ~5 days |
| `< 0.40` (very weak) | 2 days | ~2 days |

---

### Example

User studied "Loops" in week 1. BKT gave `p_known = 0.43` → S = 5 days.

By the start of week 2 (7 days later):

```
R(7) = e^(-7/5) = e^(-1.4) ≈ 0.25
```

Only **25% retention** — the user has mostly forgotten Loops. A review task gets added to week 2.

---

### No New Table — Two New Columns on `topic_knowledge`

The forgetting curve state lives on the same `topic_knowledge` table as BKT. We add:

| Column | Type | Purpose |
|---|---|---|
| last_studied_at | datetime | when this topic was last in a quiz (used to compute `t`) |
| stability_days | float | S value, derived from `p_known` after each quiz |

---

## How All Three Work Together

This is the full flow every time a user submits a weekly quiz:

**Step 1 — BKT (run immediately after quiz submission)**

For every question the user answered:
- Look up `question.topic`
- Find the `topic_knowledge` row for that topic
- Run the BKT formula → update `p_known`
- Update `last_studied_at` and `stability_days`

Result: we know exactly which topics are weak (`p_known < 0.95`)

---

**Step 2 — Forgetting Curve (run for all previous weeks)**

For every topic the user has ever studied (not just this week):
- Compute `R = e^(-days_since_last_studied / stability_days)`
- If `R < 0.70` → add to "needs review" list

Result: we know which old topics the user is about to forget

---

**Step 3 — Bandit (run after score is known)**

- Compare this week's quiz score with last week's score
- If score improved → `alpha + 1` for the style used this week
- If score dropped → `beta + 1` for the style used this week
- Thompson-sample all 4 arms → pick the style for next week

Result: we know which teaching style to use next week

---

**Step 4 — Generate next week's content**

All three results are combined into one LLM prompt:

| Input | Instruction to LLM |
|---|---|
| Weak topics (BKT) | "Reinforce these topics next week" |
| Forgotten topics (Curve) | "Add a short review task for each of these at the start" |
| Chosen style (Bandit) | "Teach in this style: theory-first / example-heavy / etc." |
| New topics for next week | "Also introduce these new topics" |

---

**Final Quiz — generated after the last weekly quiz, based entirely on ML**

Once the user completes all weeks and submits the final weekly quiz:
- Collect every topic where `p_known < 0.95` across all weeks (BKT)
- Also include topics where forgetting curve `R < 0.70`
- Send those weak/forgotten topics to the LLM
- LLM generates final quiz questions targeting exactly what this user struggled with

> The final quiz is **not** generated from enrollment topics. It is completely personalised by what BKT and the Forgetting Curve found across the entire course.

---

## Enrollment Change — Difficulty Removed

Currently during enrollment the user selects a **difficulty level** (beginner / intermediate / advanced). This was used to set the quiz pass score and influence content generation.

With the ML approach, difficulty becomes unnecessary:
- The **Bandit** automatically discovers the right teaching style for the user — there is no need to ask them upfront
- The **BKT** tracks per-topic mastery and adapts content accordingly — a "beginner" label adds no information the ML doesn't already capture
- The **final quiz** is personalised by ML, not by a difficulty setting

**Decision:** remove the `difficulty` field from the enrollment flow. The `quiz_difficulty` column on the `skills` table and the `difficulty` column on the `quizzes` table will be removed as part of this implementation.

---

## Summary of All DB Changes

### `quiz_questions` — one new column

| Column | Type | Purpose |
|---|---|---|
| topic | text | which `DailyTask.topic` this question tests |

### `topic_knowledge` — new table

One row per topic per user per skill. Owned by BKT + Forgetting Curve.

### `content_style_arms` — new table

Four rows per user per skill (one per style). Owned by the Bandit.

### `skills` — changes

| Change | Detail |
|---|---|
| Add `generated_weeks` (int) | how many weeks have been generated so far |
| Add `total_weeks` (int) | total weeks in this plan (set on first generation) |
| Remove `quiz_difficulty` | no longer needed — Bandit replaces this |

### `quizzes` — changes

| Change | Detail |
|---|---|
| Add `week` (int) | `0` = final quiz, `1–N` = per-week quiz |
| Remove `difficulty` | no longer needed |
| Constraint | `UNIQUE(skill_id)` → `UNIQUE(skill_id, week)` |

---

## Complete Picture — End to End Flow

```
USER ENROLLS
  → picks skill, days, hours/day
  → difficulty NO LONGER ASKED (removed)
  │
  ▼
WEEK 1 CONTENT GENERATED
  → LLM generates daily tasks for week 1
  → style defaults to "balanced" (first week, bandit has no data yet)
  │
  ▼
USER STUDIES WEEK 1
  → reads daily content, marks tasks complete, builds streak
  │
  ▼
WEEK 1 QUIZ
  → quiz generated from week 1 topics (each question tagged with topic)
  → user submits answers
  │
  ├──► BKT runs per question
  │      → updates p_known for each topic
  │      → topics with p_known < 0.95 = WEAK
  │
  ├──► FORGETTING CURVE runs for all studied topics
  │      → topics with R < 0.70 = FORGOTTEN
  │
  ├──► BANDIT updates
  │      → score improved? alpha+1 for "balanced"
  │      → score dropped? beta+1 for "balanced"
  │      → samples all 4 arms → picks style for week 2
  │
  ▼
WEEK 2 CONTENT GENERATED
  → weak topics   → reinforced in week 2
  → forgotten topics → short review tasks added at start
  → new topics    → introduced as normal
  → style         → picked by bandit (e.g. "theory_first")
  │
  ▼
  ... (repeats every week) ...
  │
  ▼
FINAL QUIZ (after last weekly quiz is submitted)
  → collect ALL topics with p_known < 0.95 (BKT, across all weeks)
  → collect ALL topics with R < 0.70 (Forgetting Curve)
  → LLM generates questions targeting only those weak/forgotten topics
  → user gets a quiz that is 100% personalised to their gaps
```
