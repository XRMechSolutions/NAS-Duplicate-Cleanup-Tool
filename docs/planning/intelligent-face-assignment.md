# Intelligent Face Assignment

## Goal

Improve the face auto-assignment and matching logic to prevent impossible or implausible assignments by applying real-world constraints: a person can only appear once per photo, estimated age should be plausible given the person's birth year and photo date, and when multiple faces compete for the same identity the highest-confidence match should win.

## Current Problems

### 1. Same Person Assigned Twice in One Photo

**Status: No protection.** If two faces in the same image both exceed the match threshold for person X, both get assigned to person X. This is biologically impossible.

**Affected code paths:**
- `match_and_assign_faces()` (faces.py:775-820) - processes each face independently
- `rematch_all_faces()` (faces.py:822-922) - same independent loop
- `find_more_faces_for_person()` (faces.py:924-1003) - same pattern
- `assign_face_to_person()` in database - no constraint preventing this

### 2. No Age Plausibility Check

**Status: Age only used for +0.05 similarity boost.** No validation that the assignment makes sense given the person's birth year and the photo's date.

Example: If Emma was born in 2015, she can't be a 40-year-old face in a photo from 2020. But the current system would assign it if the embedding similarity is high enough.

**Current age handling (faces.py:748-761):**
- Estimated age is classified into stages (BABY/TODDLER/CHILD/TEEN/ADULT)
- Same-stage faces get +0.05 similarity boost
- `Person.birth_year` exists but is NOT used during matching

### 3. No Confidence Competition Between Faces

**Status: Not implemented.** When face A matches person X at 0.85 and face B (same image) matches person X at 0.92, both are assigned. Should only assign B (higher confidence) and leave A for further matching or manual review.

### 4. No "One Person Per Photo" Constraint at Database Level

**Status: No constraint.** The database allows multiple faces in the same file to be assigned to the same person_id.

## Proposed Fixes

### Fix 1: Per-Photo Conflict Resolution

Before committing any assignments for a batch of faces, group candidates by file_id and resolve conflicts:

```
For each file with multiple faces:
  1. Compute all (face, person, similarity) candidates
  2. Sort by similarity descending
  3. For each candidate (highest first):
     a. If this person is already assigned to another face in THIS file, skip
     b. If this face is already assigned to a person, skip
     c. Otherwise, mark as assignable
  4. Commit only the non-conflicting assignments
  5. Send conflicts to suggestions queue for user review
```

This is essentially a bipartite matching problem (faces <-> persons) per image. For most photos with 2-5 faces, a simple greedy approach (highest similarity first) is sufficient. For edge cases with many faces, Hungarian algorithm could be used.

### Fix 2: Age Plausibility Gate

Before auto-assigning, validate that the face's estimated age is plausible:

```python
def is_age_plausible(person, face, photo_date, tolerance_years=5):
    if not person.birth_year or not photo_date:
        return True  # Can't validate, allow it

    expected_age = photo_date.year - person.birth_year
    estimated_age = face.estimated_age or 25

    # Allow tolerance for InsightFace age estimation error
    if abs(estimated_age - expected_age) > tolerance_years:
        return False  # Implausible, don't auto-assign

    # Sanity check: person can't be negative age
    if expected_age < 0:
        return False

    return True
```

**Tolerance considerations:**
- InsightFace age estimation has ~5-8 year error margin on average
- Children's ages are estimated less accurately than adults
- Use wider tolerance for children (10 years) vs adults (8 years)
- Never hard-reject, just demote to suggestion instead of auto-assign

### Fix 3: Confidence Competition (Winner-Takes-All Per Person Per Photo)

When multiple faces in the same photo match the same person:

```
1. Keep only the highest-similarity match for each person per photo
2. Demote lower-similarity matches to "suggestion" status
3. Log the conflict for user awareness
```

### Fix 4: Database Constraint

Add a uniqueness advisory (not a hard constraint, since edge cases like mirrors/reflections exist):

- Add a validation check in `assign_face_to_person()` that warns if same person is already assigned to another face in the same file
- Log a warning but allow manual override (user might intentionally assign for mirror/composite photos)

## Implementation Plan

### Phase 1: Per-Photo Conflict Resolution (Critical)

**Where to change:** `match_and_assign_faces()`, `rematch_all_faces()`, `find_more_faces_for_person()`

1. Before committing assignments, group all candidates by file_id
2. For each file, run greedy bipartite matching (highest similarity first)
3. Only auto-assign the winning face per person per photo
4. Demote losers to suggestions
5. Add unit tests for conflict scenarios

### Phase 2: Age Plausibility Gate

**Where to change:** `match_face()` (faces.py:727-773), add validation before returning match

1. Look up person's birth_year and photo's EXIF date
2. Compute expected age vs estimated age
3. If implausible: reduce similarity score or demote to suggestion
4. Don't hard-reject (age estimation is imprecise), just lower confidence
5. Add configuration for tolerance (default 8 years for adults, 10 for children)

**Critical rule: Pre-birth exclusion.** If a person's birth_year is known and the photo date is before they were born, that face CANNOT be that person. This is an absolute constraint, not a soft penalty. Most digital photos have reliable EXIF dates, making this check very reliable.

**Sibling detection hint:** When a baby face in a pre-birth photo has high similarity to a known child, the system should suggest siblings as alternative matches rather than just demoting. Baby faces of siblings (especially at similar ages) often look very similar. The suggestion should note: "This photo predates [person]'s birth -- could this be a sibling?"

Implementation:
```python
def check_birth_constraint(person, photo_date):
    if not person.birth_year or not photo_date:
        return "unknown"  # Can't validate
    if photo_date.year < person.birth_year:
        return "impossible"  # Photo taken before person was born
    expected_age = photo_date.year - person.birth_year
    return expected_age

def suggest_siblings(person, all_persons):
    """When a match is impossible due to pre-birth, suggest family members."""
    siblings = [p for p in all_persons
                if p.id != person.id
                and p.last_name == person.last_name  # if available
                and p.birth_year and p.birth_year < photo_date.year]
    return siblings
```

### Phase 3: Enhanced Suggestion Quality

**Where to change:** suggestion generation in `rematch_all_faces()`

1. When a match is demoted (conflict or age), include the reason in the suggestion
2. UI shows: "Demoted: another face in this photo matched with higher confidence"
3. UI shows: "Demoted: estimated age (5) doesn't match expected age (35)"
4. User can still manually assign if they disagree

### Phase 4: Batch Assignment Intelligence

**Where to change:** new method or enhance `match_and_assign_faces()`

1. Process ALL faces across ALL photos before committing any assignments
2. Build a global assignment graph: faces -> candidate persons with scores
3. Resolve conflicts globally (not just per-photo)
4. Example: Face A in Photo 1 matches Person X at 0.82, Face B in Photo 2 matches Person X at 0.95. If we're less sure about Face A, maybe it's actually Person Y.
5. This is a more sophisticated optimization but can wait for later

## Edge Cases

| Scenario | Current Behavior | Proposed Behavior |
|---|---|---|
| Two faces in photo both match Person X | Both assigned | Higher similarity wins, other becomes suggestion |
| Face matches Person X but age is implausible | Auto-assigned if above threshold | Demoted to suggestion with reason |
| Person has no birth_year set | Age boost only | Skip age validation (can't compute) |
| Photo has no EXIF date | Age boost only | Skip age validation (can't compute) |
| Mirror/reflection shows same person twice | N/A (would be two different face detections) | Allow manual override of one-per-photo rule |
| Twins in same photo | Would both match if similar embeddings | Greedy assignment gives first to higher similarity, second to next-best person or suggestion |
| Group photo with 10+ faces | Each processed independently | Greedy matching still efficient (10 faces is trivial) |
| Baby face with very low age estimation accuracy | Age boost/penalty applied | Use wider tolerance (10 years) for estimated ages under 5 |
| Baby face matches child X but photo predates X's birth | Auto-assigned (no birth check) | Hard reject, suggest siblings with same last name or family group |
| Two siblings who look similar as babies | May be confused if embeddings are close | Pre-birth check catches impossible assignments; for same-era photos, present both as suggestions |
| Photo date is wrong/missing EXIF | Age check could give wrong result | Skip age validation entirely if no EXIF date; never trust file system dates for this |

## Testing

- Photo with 2 faces, both matching same person -> only higher-confidence assigned
- Photo with 3 faces, person A matches face 1 (0.9) and face 2 (0.7) -> face 1 wins
- Person born 2015, photo from 2018, face estimated age 40 -> demoted to suggestion
- Person born 2015, photo from 2018, face estimated age 4 -> allowed (within tolerance)
- Person with no birth_year -> age validation skipped, normal assignment
- Photo with no EXIF date -> age validation skipped, normal assignment
- Batch of 100 photos -> no two faces in same photo assigned to same person
- Person born 2015, photo from 2012, baby face matches person -> hard rejected (pre-birth)
- Person born 2015, photo from 2012, sibling born 2010 exists -> sibling suggested as alternative
- Photo with no EXIF date, person has birth_year -> age validation skipped (don't use file system dates)
- Two siblings as babies, similar embeddings -> both presented as suggestions, not auto-assigned
