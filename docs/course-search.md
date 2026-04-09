# Course Search — Implementation Plan

**Author:** Yogesh K
**Date:** April 8, 2026
**Issue:** #4
**Status:** Implemented

---

## Problem

Users had no way to search across courses and their chapters. Finding a specific topic required opening each course individually.

## Solution

Add a server-side search endpoint (`GET /syllabi/search?q=`) that performs keyword matching across the `skills` table (course name) and the `daily_tasks` table (chapter topic & generated content). The frontend calls this endpoint with a debounced search query and displays matching courses along with the specific chapters that matched.

### How It Works

1. User types in the search input on the Syllabi page
2. After a 350ms debounce, the frontend calls `GET /py/syllabi/search?q=<keyword>`
3. Backend performs a case-insensitive `ILIKE` query on:
   - `skills.skill` (course name)
   - `daily_tasks.topic` (chapter title)
   - `daily_tasks.newsletter` (generated chapter content — only searched if content exists)
4. Returns matching course cards with aggregated progress stats, plus a `matching_chapters` array for each course showing which chapters matched the keyword
5. Frontend renders matching courses; each card shows a "Matching chapters" section listing the relevant chapters (day number + topic). Cards without a syllabus show a centered empty state with the Generate button.
6. If no courses or chapters match, a "No courses found" empty state is shown
7. Clearing the input restores the full course list (no API call, uses cached data)

### Search Scope

- **Course name** — always searched
- **Chapter topic** — the visible chapter title, always searched
- **Generated content** — only searched for chapters that have content already generated; ungenerated chapters are not matched on hidden internal fields to avoid confusing results

### Why Server-Side

Chapter-level data (topics, tasks) is not loaded on the course list page — only summary stats are fetched. A server-side search allows querying `daily_tasks` without loading all chapter data upfront.

## Files Changed

| File | Change |
| --- | --- |
| `services/skill.py` | Added `search_syllabi()` — queries `skills` (course name), `daily_tasks.topic` (chapter title), and `daily_tasks.newsletter` (generated content) with `ILIKE`, returns matching courses + chapters |
| `controllers/syllabus.py` | Added `search()` controller — delegates to `search_syllabi` service |
| `routes/syllabus.py` | Added `GET /syllabi/search?q=` route |
| `ui/src/app/plugins/syllabi/index.tsx` | Added debounced search input that calls the search API; displays matching chapters on each course card; centered empty state for ungenerated courses; loading spinner during search; equal-height card grid |

## Additional UI Polish (bundled)

- Sparkles icon on all "Generate" buttons
- Gradient branding on sidebar title and auth pages
- Dark mode as default for new users
- Force light theme on login/signup pages
