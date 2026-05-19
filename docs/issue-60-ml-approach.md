# ML Approach — Adaptive Syllabus Without Historical Data (Issue #60)

## The Problem With "No Data"

Most ML systems need thousands of data points before they start working. We have zero —
a brand new user has no history at all. But there is a class of ML algorithms that are
designed to **start from a reasonable guess and update after every single observation**.
They learn as the user uses the product.

We use three of them. Each solves a different problem:

| # | Algorithm | Problem it solves |
|---|---|---|
| 1 | **Bayesian Knowledge Tracing (BKT)** | How well does the user know each topic? |
| 2 | **Multi-Armed Bandit (MAB)** | What teaching style works best for this user? |
| 3 | **Ebbinghaus Forgetting Curve** | Which topics is the user about to forget? |

---

## First: One Change to an Existing Table

Before explaining the algorithms, there is one change to the existing `quiz_questions` table
that all three algorithms depend on.

### `quiz_questions` — add `topic` column

**Current state of the table:**

| Column | Type | Purpose |
|---|---|---|
| id | int | primary key |
| quiz_id | int | which quiz this question belongs to |
| position | int | question number (1, 2, 3 …) |
| question | text | the question text |
| option_a/b/c/d | text | the four answer choices |
| correct_option | str | "A", "B", "C", or "D" |
| explanation | text | why the correct answer is correct |

**Problem:** we know the question and the answer, but we have no idea *which topic from
the week this question is testing*. So when the user answers it wrong, we cannot update
anything — we do not know what to mark as weak.

**The fix — add one column:**

| Column | Type | Purpose |
|---|---|---|
| **topic** | text | the `DailyTask.topic` this question is testing (e.g. "Loops", "Functions") |

When we generate the per-week quiz, we tag each question with the topic it tests. This
is the link that connects a wrong answer → to a topic → to the ML algorithms below.

**Example of what a row looks like after this change:**

```
quiz_id:        5
position:       2
question:       "What does a for loop do in Python?"
option_a:       "Defines a function"
option_b:       "Repeats a block of code"   ← correct
option_c:       "Creates a variable"
option_d:       "Imports a module"
correct_option: "B"
topic:          "Loops"                      ← NEW
```

---

## Algorithm 1: Bayesian Knowledge Tracing (BKT)

### What is it and why do we use it?

After a user takes the week quiz, we need to answer one question: **how well does this
user actually know each topic?**

A simple percentage score (e.g. "70% correct") is not enough, because:
- The user might have guessed a correct answer
- The user might have slipped on a question they actually know well
- Two wrong answers in a row means something different from one wrong answer

BKT solves this by tracking a probability for each topic: **"What is the chance this user
has truly learned this topic?"** It accounts for guessing and slipping.

We use it because the output — a `p_known` score per topic — is exactly what we need to
tell the LLM: "reinforce these topics next week".

### The 4 parameters (no data needed — these are starting assumptions)

| Parameter | Value | Meaning |
|---|---|---|
| P(L₀) — initial knowledge | 0.10 | We assume the user starts not knowing the topic |
| P(T) — learn rate | 0.10 | Each question is a 10% chance to learn the topic |
| P(G) — guess rate | 0.20 | 20% chance of a correct answer even without knowing |
| P(S) — slip rate | 0.10 | 10% chance of a wrong answer even if the user knows it |

These values come from published educational research. They work without any user data.

### How it updates after each answer

```
If the user answered CORRECTLY:
  p_known = (p_known × (1 - slip)) ÷ (p_known × (1 - slip) + (1 - p_known) × guess)

If the user answered WRONGLY:
  p_known = (p_known × slip) ÷ (p_known × slip + (1 - p_known) × (1 - guess))

Then apply learning opportunity:
  p_known = p_known + (1 - p_known) × learn_rate
```

The code for this is 10 lines of Python. No external library needed.

### Mastery threshold

`p_known >= 0.95` → user has **mastered** this topic → no reinforcement needed  
`p_known < 0.95` → topic is **weak** → passed into next week's LLM prompt

### New table: `topic_knowledge`

**Purpose:** stores the BKT state (p_known) for every topic, for every user, for every skill.

| Column | Type | Purpose |
|---|---|---|
| id | int | primary key |
| skill_id | int | FK → `skills.id` (which course) |
| user_id | int | FK → `users.id` (which user) |
| topic | str | the topic name, e.g. "Loops" — matches `DailyTask.topic` |
| week | int | which week this topic was first introduced |
| p_known | float | current BKT score (starts at 0.10, updated after each quiz) |
| attempts | int | total number of questions answered on this topic |
| correct | int | how many were correct |
| p_transit | float | learn rate (default 0.10, can be tuned later) |
| p_guess | float | guess rate (default 0.20) |
| p_slip | float | slip rate (default 0.10) |

**Unique constraint:** `(skill_id, user_id, topic)` — one row per topic per user per course.

**Relationship to other tables:**

```
skills ──── topic_knowledge ──── users
              │
              │ topic column matches
              ▼
           daily_tasks.topic
              │
              │ topic column matches
              ▼
           quiz_questions.topic  (the new column above)
```

**Example rows after week 1 quiz:**

```
skill_id  user_id  topic        week  p_known  attempts  correct
1         42       Variables    1     0.92     3         3        ← nearly mastered
1         42       Loops        1     0.43     3         1        ← weak, needs review
1         42       Functions    1     0.71     2         1        ← partial
```

---

## Algorithm 2: Multi-Armed Bandit (MAB)

### What is it and why do we use it?

Different people learn in different ways. Some people understand a concept best when they
see a lot of code examples first. Others prefer to understand the theory before touching
code. Others need to go slowly and review a lot.

We want to figure out **which teaching style works best for each individual user** —
but we cannot ask them directly, and we do not know at the start.

A Multi-Armed Bandit is an ML algorithm for exactly this kind of problem:
**"I have several options. I don't know which is best. How do I find out without wasting
too many tries on bad options?"**

### Why "bandit"?

Imagine a row of slot machines (one-armed bandits). Each machine has a different payout
rate but you don't know what it is. You want to maximise your winnings. You try different
machines, learn which pays best, and gradually spend more time on the winning ones.

In our case:
- Each **slot machine = a content generation style** (an "arm")
- **Pulling the arm** = generating a week of content in that style
- **Winning** = the user's quiz score improves week over week

### The 4 arms (content styles)

| Arm | Style | What the LLM generates |
|---|---|---|
| `balanced` | Equal mix of theory and examples | Default starting style |
| `example_heavy` | Code examples first, theory after | For hands-on learners |
| `theory_first` | Full explanation before any code | For conceptual learners |
| `reinforcement` | Slower pace, more repetition | For users who are struggling |

### How Thompson Sampling works (the algorithm)

Each arm has two counters: `alpha` (wins) and `beta` (losses). Both start at 1.

Before generating each week's content:
1. Pick a random number from `Beta(alpha, beta)` for each arm
2. Pick the arm with the highest number
3. Use that style to generate the week
4. After the week's quiz: if score improved → `alpha + 1`, if not → `beta + 1`

The Beta distribution naturally balances exploration (trying new arms) and exploitation
(using the known best arm). Arms that have won more often will usually produce higher
random samples — but occasionally an untried arm gets a lucky high sample and gets
explored.

**Example over 5 weeks for one user:**

```
Week 1: all arms at Beta(1,1) → random → picks "balanced"
        quiz score: 65%

Week 2: all arms still equal → random → picks "example_heavy"
        quiz score: 72% (improved +7%) → example_heavy: alpha=2, beta=1

Week 3: example_heavy slightly favoured → picks "example_heavy" again
        quiz score: 68% (dropped -4%) → example_heavy: alpha=2, beta=2

Week 4: example_heavy and balanced now equal → "theory_first" not yet tried
        exploration kicks in → picks "theory_first"
        quiz score: 81% (improved +13%) → theory_first: alpha=2, beta=1

Week 5: theory_first now favoured → picks "theory_first"
        quiz score: 85% (improved +4%) → theory_first: alpha=3, beta=1
```

After 5 weeks the system has learned this user is a "theory first" learner.

### New table: `content_style_arms`

**Purpose:** stores the bandit state (alpha and beta counters) for every style, for every
user, for every skill.

| Column | Type | Purpose |
|---|---|---|
| id | int | primary key |
| skill_id | int | FK → `skills.id` |
| user_id | int | FK → `users.id` |
| style | str | "balanced", "example_heavy", "theory_first", "reinforcement" |
| alpha | float | number of wins + 1 (starts at 1.0) |
| beta | float | number of losses + 1 (starts at 1.0) |

**Unique constraint:** `(skill_id, user_id, style)` — one row per style per user per course.

**When rows are created:** 4 rows are inserted the moment a user generates week 1 — one
for each style, all starting at `alpha=1, beta=1`.

**Relationship to other tables:**

```
skills ──── content_style_arms ──── users
```

**Example rows after 5 weeks (same user as above):**

```
skill_id  user_id  style           alpha  beta
1         42       balanced        1.0    2.0    ← tried once, no improvement
1         42       example_heavy   2.0    2.0    ← tried twice, mixed results
1         42       theory_first    3.0    1.0    ← tried twice, both improved ← WINNER
1         42       reinforcement   1.0    1.0    ← never tried yet
```

---

## Algorithm 3: Ebbinghaus Forgetting Curve

### What is it and why do we use it?

In 1885, a psychologist named Hermann Ebbinghaus measured how fast people forget things.
He found that memory decays in a predictable mathematical pattern:

```
R(t) = e^(-t / S)

R = retention  (1.0 = perfect recall, 0.0 = completely forgotten)
t = days since the topic was last studied
S = stability  (how long the memory lasts — depends on how well you learned it)
```

We use this to answer: **"Which topics from previous weeks is the user about to forget?"**
If the answer is R < 0.70 (30% or more forgotten), we inject a short review task into
next week's content before introducing anything new.

This means the user naturally gets spaced repetition without having to think about it.

### How stability is set

After each week's quiz, BKT gives us `p_known` for each topic. We use that to set S:

| p_known (BKT score) | Stability S | Meaning |
|---|---|---|
| ≥ 0.95 | 21 days | Mastered — memory lasts 3 weeks |
| 0.70 – 0.94 | 10 days | Good — memory lasts ~10 days |
| 0.40 – 0.69 | 5 days | Weak — memory lasts ~5 days |
| < 0.40 | 2 days | Very weak — will forget in 2 days |

### Example

User studied "Loops" in week 1. BKT gave `p_known = 0.43` → S = 5 days.

By the start of week 2 (7 days later):
```
R(7) = e^(-7/5) = e^(-1.4) = 0.25
```

Only 25% retention. The user has mostly forgotten Loops. A review task gets added at
the start of week 2.

### No new table — two new columns on `topic_knowledge`

The forgetting curve state lives on the same `topic_knowledge` table as BKT.
We just add two columns:

| Column | Type | Purpose |
|---|---|---|
| last_studied_at | datetime | when this topic was last in a quiz (to compute `t`) |
| stability_days | float | S value, set from `p_known` after each quiz |

**Updated `topic_knowledge` table (all columns together):**

| Column | Type | Set by | Purpose |
|---|---|---|---|
| id | int | DB | primary key |
| skill_id | int | system | FK → skills.id |
| user_id | int | system | FK → users.id |
| topic | str | system | matches DailyTask.topic |
| week | int | system | which week introduced this topic |
| p_known | float | **BKT** | probability user knows this topic |
| attempts | int | **BKT** | total questions answered on this topic |
| correct | int | **BKT** | correct answers on this topic |
| p_transit | float | config | BKT learn rate (default 0.10) |
| p_guess | float | config | BKT guess rate (default 0.20) |
| p_slip | float | config | BKT slip rate (default 0.10) |
| last_studied_at | datetime | **Forgetting Curve** | when topic was last quizzed |
| stability_days | float | **Forgetting Curve** | S value derived from p_known |

---

## How All Three Work Together

After the user submits the week 1 quiz:

```
STEP 1 — BKT
  For every question in the quiz:
    → look up question.topic
    → look up TopicKnowledge row for that topic
    → update p_known using the BKT formula
    → update last_studied_at and stability_days
  Result: we know which topics are weak (p_known < 0.95)

STEP 2 — FORGETTING CURVE
  For every topic from previous weeks (not just this week):
    → compute R(days_since_last_studied)
    → if R < 0.70, add topic to "needs review" list
  Result: we know which old topics the user is forgetting

STEP 3 — BANDIT
  → look up current quiz score
  → compare to previous week score
  → update alpha or beta for the style used this week
  → Thompson sample all arms → pick style for next week
  Result: we know which teaching style to use

STEP 4 — BUILD LLM PROMPT
  → weak topics from BKT    → "reinforce these"
  → forgotten topics from curve → "add review tasks for these"
  → style from bandit        → "teach in this way"
  → new topics for week 2    → "introduce these"
  → send to LLM → generate week 2 content
```

---

## All New and Changed Tables Summary

### Changed: `quiz_questions`

Add one column:

| New column | Type | Purpose |
|---|---|---|
| topic | text | which DailyTask.topic this question tests |

### New: `topic_knowledge`

One row per topic per user per skill. Updated by BKT and Forgetting Curve after every quiz.

### New: `content_style_arms`

Four rows per user per skill (one per style). Updated by the Bandit after every quiz.

### Changed: `skills`

| New column | Type | Purpose |
|---|---|---|
| generated_weeks | int | how many weeks have been generated so far |
| total_weeks | int | total number of weeks in this plan (set on first generation) |

### Changed: `quizzes`

| New column | Type | Purpose |
|---|---|---|
| week | int | 0 = full course quiz, 1–N = per-week quiz |

The unique constraint on `quizzes` changes from `UNIQUE(skill_id)` to
`UNIQUE(skill_id, week)` so each week can have its own quiz.

---

## The Complete Picture

```
skills
  │
  ├── daily_tasks (week, topic, task …)
  │       │
  │       └── topic name feeds into ──────────────────────────┐
  │                                                            │
  ├── quizzes (week=0 full course, week=1,2,3 per-week)        │
  │       │                                                    │
  │       └── quiz_questions (+ topic column) ────────────────┘
  │               │                                            │
  │               └── wrong/correct answer ──► topic_knowledge
  │                                               (BKT + forgetting curve state)
  │
  └── content_style_arms
          (bandit state — which style works for this user)
```
