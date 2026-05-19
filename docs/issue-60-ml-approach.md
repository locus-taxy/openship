# ML Approach — Adaptive Syllabus Without Historical Data (Issue #60)

## The Problem With "No Data"

Most ML systems need thousands of data points to train. We have zero — a brand new user
has no history. But "no data" does not mean "no ML". There is a class of ML algorithms
that are specifically designed to **learn while they run**, starting from a prior belief
and updating after every single observation.

We will use three of them, each solving a different part of the problem:

| Algorithm | What it solves | Data needed to start |
|---|---|---|
| **Bayesian Knowledge Tracing (BKT)** | Does the user know this topic? | None — uses priors |
| **Contextual Multi-Armed Bandit (MAB)** | What content style works for this user? | None — explores first |
| **Ebbinghaus Forgetting Curve** | When will the user forget a topic? | None — pure math |

---

## Algorithm 1: Bayesian Knowledge Tracing (BKT)

### What is it?

BKT is the algorithm Khan Academy and Coursera use to decide if a student has "mastered"
a concept. It was invented in 1994 and is still the standard in educational ML.

It models each topic as a hidden state: **the student either knows it or doesn't**.
Every quiz answer updates the probability that the student knows the topic.

### The 4 parameters

You do not learn these from data — you set them as priors based on educational research.

| Parameter | Symbol | Default | Meaning |
|---|---|---|---|
| Initial knowledge | P(L₀) | 0.10 | 10% chance user already knows a brand-new topic |
| Learn rate | P(T) | 0.10 | 10% chance of learning per question attempt |
| Guess rate | P(G) | 0.20 | 20% chance of guessing correctly without knowing |
| Slip rate | P(S) | 0.10 | 10% chance of answering wrong even if you know it |

These are the same defaults used in published BKT research. You can tune them later
once you have data, but they work reasonably well out of the box.

### The math (simple version)

After each question answer, update `P(L)` for that topic:

```
If the user answered CORRECTLY:
  P(L | correct) = P(L) × (1 - P(S))
                   ─────────────────────────────────────────
                   P(L) × (1 - P(S))  +  (1 - P(L)) × P(G)

If the user answered WRONGLY:
  P(L | wrong)   = P(L) × P(S)
                   ─────────────────────────────────────────
                   P(L) × P(S)  +  (1 - P(L)) × (1 - P(G))

Then apply the transit (learning opportunity):
  P(L_next) = P(L | answer)  +  (1 - P(L | answer)) × P(T)
```

### Example walkthrough

Topic: "Loops". User starts with P(L) = 0.10 (doesn't know it).

```
Question 1 (Loops) → wrong answer
  P(L | wrong) = 0.10 × 0.10 / (0.10 × 0.10 + 0.90 × 0.80) = 0.014
  P(L_next)    = 0.014 + (1 - 0.014) × 0.10 = 0.112

Question 2 (Loops) → wrong again
  P(L | wrong) = 0.112 × 0.10 / (0.112 × 0.10 + 0.888 × 0.80) = 0.016
  P(L_next)    = 0.016 + (1 - 0.016) × 0.10 = 0.114

Question 3 (Loops) → correct!
  P(L | correct) = 0.114 × 0.90 / (0.114 × 0.90 + 0.886 × 0.20) = 0.366
  P(L_next)      = 0.366 + (1 - 0.366) × 0.10 = 0.429
```

After 3 questions the model estimates there is a 43% chance the user knows "Loops".
Still below the mastery threshold (0.95), so "Loops" stays in the weak-topics list.

### Mastery threshold

`P(L) >= 0.95` → topic is considered **mastered** → no reinforcement needed next week.
`P(L) < 0.95` → topic needs reinforcement → passed to next week's LLM prompt.

### What we store

A new `TopicKnowledge` table (replaces the simpler `TopicMastery` from the other doc):

```python
class TopicKnowledge(SQLModel, table=True):
    __tablename__ = "topic_knowledge"

    id:          Optional[int]
    skill_id:    int      # FK → skills.id CASCADE
    user_id:     int      # FK → users.id CASCADE
    topic:       str
    p_known:     float = 0.10   # current P(L) — updated after every answer
    attempts:    int = 0
    correct:     int = 0

    # BKT constants (can be tuned later per topic or per user)
    p_transit:   float = 0.10
    p_guess:     float = 0.20
    p_slip:      float = 0.10
```

Unique constraint: `(skill_id, user_id, topic)`

---

## Algorithm 2: Contextual Multi-Armed Bandit (MAB)

### What is it?

A bandit problem: you have multiple options (arms) and you want to figure out which one
works best for this user — but you only learn by trying them. The challenge is balancing:
- **Exploration** — try all options to learn which works
- **Exploitation** — use the best known option to maximise results

We use **Thompson Sampling**, the simplest and most effective bandit algorithm.

### What are the arms?

Four content generation styles for the LLM prompt:

| Arm | Style | When it works |
|---|---|---|
| `balanced` | Mix of theory, examples, practice | Default, works for most |
| `example_heavy` | More code examples, less theory | Users who learn by doing |
| `theory_first` | Concepts before examples | Users who want to understand why |
| `reinforcement` | More review of past topics, slower pace | Users who struggle |

### How Thompson Sampling works

Each arm has a Beta distribution `Beta(α, β)`:
- `α` = number of "successes" (quiz score improved week over week)
- `β` = number of "failures" (score stayed same or dropped)
- Initial state: `Beta(1, 1)` — total uncertainty, all arms equally likely

Each week before generating content:
1. Sample a random value from each arm's Beta distribution
2. Pick the arm with the highest sample
3. Generate content using that arm's style
4. After the week's quiz: if score improved → `α++`, else → `β++`

### Example walkthrough

Initial state: all arms at `Beta(1, 1)`.

```
Week 1: sample from Beta(1,1) for all → pick "balanced" (random)
  → Week 1 quiz score: 65%

Week 2: sample from Beta(1,1) for all → pick "example_heavy" (random)
  → Week 2 quiz score: 72% (improved +7%) → success → example_heavy: Beta(2,1)

Week 3: sample → example_heavy now has higher α, likely picked again
  → Week 3 quiz score: 68% (dropped -4%) → failure → example_heavy: Beta(2,2)

Week 4: balanced and example_heavy are similar, but "theory_first" not tried yet
  → system tries theory_first (exploration)
  → Week 4 quiz score: 80% (improved +12%) → success → theory_first: Beta(2,1)

... over time, theory_first wins for this user
```

After 6-8 weeks the bandit converges on the best style for each user.

### What we store

```python
class ContentStyleArm(SQLModel, table=True):
    __tablename__ = "content_style_arms"

    id:       Optional[int]
    skill_id: int      # FK → skills.id CASCADE
    user_id:  int      # FK → users.id CASCADE
    style:    str      # "balanced" | "example_heavy" | "theory_first" | "reinforcement"
    alpha:    float = 1.0   # successes + 1 (Beta prior)
    beta:     float = 1.0   # failures + 1 (Beta prior)
```

---

## Algorithm 3: Ebbinghaus Forgetting Curve

### What is it?

In 1885, Hermann Ebbinghaus mathematically modelled how memory decays over time.
The formula is:

```
R(t) = e^(-t / S)

R = retention (0 to 1, where 1 = perfect recall)
t = days since the topic was last studied
S = stability (how long the memory lasts)
```

No data, no training — just math. This is what Anki and Duolingo use for spaced repetition.

### How we use it

When a topic is covered in week N, we record when it was learned and estimate its
stability based on the BKT `P(L)` score:

| P(L) at end of week | Stability S |
|---|---|
| ≥ 0.95 (mastered) | 21 days |
| 0.70 – 0.94 | 10 days |
| 0.40 – 0.69 | 5 days |
| < 0.40 | 2 days |

When generating the next week, we compute `R(t)` for every previously covered topic.
Topics where `R(t) < 0.70` (user has likely forgotten 30% or more) get a brief review
task injected into the new week's content.

### Example

Topic "Loops" was covered in week 1. `P(L)` at end of week 1 = 0.43 → S = 5 days.

```
Day 7 (start of week 2):  R = e^(-7/5)  = 0.25  → forgotten, needs review
Day 3 (start of week 1):  R = e^(-3/5)  = 0.55  → partially forgotten
Day 1:                    R = e^(-1/5)  = 0.82  → mostly remembered
```

At the start of week 2, R = 0.25 for "Loops" → add a 15-minute review task for Loops
at the beginning of week 2.

### What we store

Add two columns to `TopicKnowledge`:

```python
last_studied_at:  Optional[datetime]   # when the topic was last in a weekly quiz
stability_days:   float = 5.0          # S value, set from P(L) after each quiz
```

---

## How All Three Combine

```
WEEK 1 QUIZ SUBMITTED
        │
        ▼
┌─────────────────────────────┐
│  BKT UPDATE                 │
│  For each question:         │
│  update P(L) for its topic  │
│  → identifies weak topics   │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  FORGETTING CURVE           │
│  For each topic covered:    │
│  compute R(7) — retention   │
│  after 7 days               │
│  → identifies forgotten     │
│    topics needing review    │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│  MAB — PICK CONTENT STYLE   │
│  Thompson sample all arms   │
│  → picks style for week 2   │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  GENERATE WEEK 2 PROMPT                                 │
│                                                         │
│  Style:        {MAB winner}                             │
│  Weak topics:  {BKT topics where P(L) < 0.95}          │
│  Review tasks: {Forgetting Curve topics where R < 0.70} │
│  New topics:   {next week's planned topics}             │
└─────────────────────────────────────────────────────────┘
        │
        ▼
  LLM generates week 2 content
```

---

## The LLM Prompt (with ML data injected)

```python
def week_user_prompt(
    skill: str,
    week_number: int,
    hours: int,
    style: str,             # from MAB
    weak_topics: list[str], # from BKT: P(L) < 0.95
    review_topics: list[str], # from forgetting curve: R(7) < 0.70
    new_topics: list[str],  # planned topics for this week
) -> str:

    style_instructions = {
        "balanced":       "Mix theory with practical examples equally.",
        "example_heavy":  "Lead with code examples. Explain theory after.",
        "theory_first":   "Explain the concept fully before showing examples.",
        "reinforcement":  "Go slower. Use more repetition and simpler examples.",
    }

    return f"""
Generate week {week_number} content for learning {skill}.
Daily commitment: {hours} hour(s).

Teaching style: {style_instructions[style]}

{"Reinforce these weak topics from last week: " + ", ".join(weak_topics) + "." if weak_topics else ""}
{"Add short review tasks for topics the user is likely forgetting: " + ", ".join(review_topics) + "." if review_topics else ""}
New topics to introduce this week: {", ".join(new_topics)}.

Structure each day as: [optional review] → [new content] → [practice].
"""
```

---

## Implementation Plan

### New files

| File | Purpose |
|---|---|
| `models/topic_knowledge.py` | `TopicKnowledge` table (BKT state per topic) |
| `models/content_style_arm.py` | `ContentStyleArm` table (MAB state per user) |
| `services/bkt.py` | BKT update function, mastery check |
| `services/bandit.py` | Thompson sampling, arm update |
| `services/forgetting.py` | Forgetting curve, stability assignment, review scheduling |

### `services/bkt.py` — the full implementation

```python
def update_p_known(
    p_known: float,
    correct: bool,
    p_transit: float = 0.10,
    p_guess: float = 0.20,
    p_slip: float = 0.10,
) -> float:
    if correct:
        numerator = p_known * (1 - p_slip)
        denominator = numerator + (1 - p_known) * p_guess
    else:
        numerator = p_known * p_slip
        denominator = numerator + (1 - p_known) * (1 - p_guess)

    p_known_given_obs = numerator / denominator if denominator > 0 else p_known
    return p_known_given_obs + (1 - p_known_given_obs) * p_transit
```

That is the entire BKT algorithm — 10 lines of Python, no library needed.

### `services/bandit.py` — Thompson Sampling

```python
import random

def sample_arm(alpha: float, beta: float) -> float:
    """Sample from Beta(alpha, beta) using the standard library."""
    return random.betavariate(alpha, beta)

def pick_best_arm(arms: list[dict]) -> str:
    """arms = [{"style": "balanced", "alpha": 1, "beta": 1}, ...]"""
    return max(arms, key=lambda a: sample_arm(a["alpha"], a["beta"]))["style"]

def update_arm(alpha: float, beta: float, success: bool) -> tuple[float, float]:
    if success:
        return alpha + 1, beta
    return alpha, beta + 1
```

### `services/forgetting.py`

```python
import math
from datetime import datetime

STABILITY_FROM_P_KNOWN = [
    (0.95, 21.0),
    (0.70, 10.0),
    (0.40, 5.0),
    (0.00, 2.0),
]

def get_stability(p_known: float) -> float:
    for threshold, stability in STABILITY_FROM_P_KNOWN:
        if p_known >= threshold:
            return stability
    return 2.0

def retention(days_since: float, stability: float) -> float:
    return math.exp(-days_since / stability)

def needs_review(last_studied_at: datetime, stability: float, threshold: float = 0.70) -> bool:
    days = (datetime.utcnow() - last_studied_at).days
    return retention(days, stability) < threshold
```

---

## What the user sees

The ML runs entirely in the background. From the user's perspective:

1. Take a 5-question quiz at the end of each week
2. Next week's content appears automatically — it just feels more relevant
3. Topics they struggled with come back in a lighter review format
4. Over 4–6 weeks the content style gradually matches how they learn best

The user never needs to know there is a BKT model or a bandit running. They just
experience a course that gets smarter about them over time.

---

## What you learn by building this

| Concept | Where it appears |
|---|---|
| Bayesian inference | BKT update rule — posterior from prior + evidence |
| Hidden Markov Model | BKT is a 2-state HMM (knows / doesn't know) |
| Exploration vs exploitation | MAB — why you can't just always pick the best known option |
| Beta distribution | Thompson Sampling — natural way to model uncertainty over probabilities |
| Exponential decay | Forgetting curve — why memories fade non-linearly |
| Online learning | All three update after every single data point, not in batches |
