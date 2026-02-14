# Age-Progression Face Recognition

## Goal

Complete the temporal bridging system for face recognition so DupliCleaner can track the same person from infancy through adulthood. A baby photo from 2005 should eventually link to a teenager photo from 2018 through a chain of intermediate photos, even though the direct embedding similarity between baby and teen is too low to match.

## Current Capabilities (Working)

- **Age stage classification** - Five stages: BABY (0-2), TODDLER (2-5), CHILD (5-12), TEEN (13-17), ADULT (18+)
- **Multi-embedding storage** - Each person stores multiple embeddings grouped by age stage
- **Age estimation** - InsightFace provides estimated age per detected face
- **Age stage boost** - +0.05 similarity bonus when comparing faces at the same life stage
- **Cross-age cluster linking** - `find_intermediate_clusters()` finds clusters that may be the same person at different ages, auto-assigns at 0.95 confidence, suggests at 0.35
- **Rematch with suggestions** - Re-matches unassigned faces against known people with age-aware boosting
- **Chain gap detection** - `find_chain_gaps()` identifies years with no photos for a person
- **Person timeline** - `get_person_timeline()` groups faces by year

## What's Incomplete

### 1. Temporal Chain Building (Stubbed)

**Current state:** `build_temporal_chain()` method exists (faces.py:1270-1343) but is non-functional. It sorts faces by date and iterates pairs, logging breaks, but does not persist any chain data or use the temporal thresholds for matching.

**Temporal thresholds defined but unused:**
- Same day: 0.5 (most relaxed)
- Same month: 0.6
- Same year: 0.7
- Different years: 0.8 (strictest)

**Needed:**
- Persist temporal edges in database (which faces are temporal neighbors)
- Use temporal proximity to relax similarity thresholds during matching
- Graph traversal: if Face A matches Face B (age 3) and Face B matches Face C (age 5), suggest A and C are the same person even if A-C direct similarity is below threshold

### 2. Temporal Link Database Storage (Not Implemented)

**Current state:** No database table for temporal chain links.

**Needed:**
- `temporal_links` table: face_id_a, face_id_b, similarity_score, temporal_distance_days, link_type (auto/suggested/confirmed)
- Query: given a person, retrieve their temporal chain in chronological order
- Support user confirmation/rejection of suggested links

### 3. Intermediate Age Estimation (Partially Broken)

**Current state:** Cross-age matching tries to estimate expected age at photo time using `_estimate_age_stage()`, but this method references `stage.mid_age()` which doesn't exist on the enum.

**Needed:**
- Fix `_estimate_age_stage()` to properly calculate expected age from person's birth year + photo date
- Use expected vs actual age stage to weight similarity scores
- Handle unknown birth years gracefully (estimate from earliest photo with age)

### 4. Full Timeline Analysis (Not Implemented)

**Current state:** Timeline groups faces by year but doesn't analyze the progression.

**Needed:**
- Consistency checking: flag if a person's face changes too drastically between adjacent years
- Missing year alerts with suggestions to search specific date ranges
- Visual timeline display in UI showing face thumbnails along a chronological axis
- Embedding drift visualization: how much the person's face has changed over time

## Implementation Phases

### Phase 1: Fix and Complete Temporal Chain Building

- Create `temporal_links` database table
- Implement actual chain building logic:
  1. Sort all faces for a person chronologically
  2. For each adjacent pair, compute similarity and temporal distance
  3. Store as edges in temporal_links table
  4. Flag weak links (low similarity between adjacent photos) for user review
- Fix `_estimate_age_stage()` method

### Phase 2: Temporal-Aware Matching

- During face matching, use temporal proximity to adjust thresholds:
  - Photos taken on the same day: accept 0.5 similarity
  - Same month: accept 0.6
  - Same year: accept 0.7
  - Different years: require 0.8+
- Graph-based transitive matching:
  - If A->B (0.7 similarity, 6 months apart) and B->C (0.65 similarity, 8 months apart), suggest A=C
  - Confidence degrades with chain length (prevent long-chain false positives)
- Present chain-based suggestions to user with the full chain shown for context

### Phase 3: Cross-Age Cluster Merging

- Improve `find_intermediate_clusters()` to use temporal chains as evidence
- When two unassigned clusters have a plausible temporal bridge, suggest merge
- Show user: "These faces might be the same person at different ages" with timeline view
- One-click merge with automatic multi-embedding update

### Phase 4: Timeline UI and Diagnostics

- Visual timeline component in Faces tab showing face progression
- Embedding drift chart (how similar each year's face is to the previous year)
- Gap alerts: "No photos of Emma between ages 7-10, check folders from 2015-2018"
- Age estimation accuracy display (compare estimated age to actual age from birth year)
- Export person timeline as a collage or report

## Technical Approach

### Chain Building Algorithm

```
1. Get all faces for person P, sorted by photo date
2. For each consecutive pair (F_i, F_j):
   a. Compute cosine similarity of embeddings
   b. Compute temporal distance in days
   c. Look up threshold for that temporal distance
   d. If similarity >= threshold: strong link
   e. If similarity >= threshold * 0.7: weak link (suggest to user)
   f. If similarity < threshold * 0.7: break (possible misassignment)
3. Store all links in temporal_links table
4. Return chain with any breaks flagged
```

### Transitive Matching

```
For unassigned face F:
  For each known person P:
    direct_sim = max similarity to any of P's embeddings
    if direct_sim >= hard_threshold: auto-assign

    # Try temporal bridge
    chain_sim = find_best_chain(F, P's faces, max_hops=3)
    if chain_sim >= soft_threshold: suggest to user
```

### Confidence Decay Over Chain Length

- Direct match (1 hop): full confidence
- 2 hops: confidence * 0.85
- 3 hops: confidence * 0.70
- 4+ hops: too unreliable, don't suggest

## Edge Cases

- **Twins**: Nearly identical embeddings at same age, different people. Require user to manually separate.
- **Dramatic appearance changes**: Glasses, facial hair, weight changes. Multi-embedding storage helps here.
- **Adoption/unknown birth year**: Estimate birth year from earliest photo with age estimation, allow manual override.
- **Gaps of many years**: If no photos exist between age 5 and 15, direct comparison is unreliable. Flag for user rather than auto-matching.
- **Multiple children of similar ages**: Use temporal ordering and other context (who else is in the photo) to disambiguate.
