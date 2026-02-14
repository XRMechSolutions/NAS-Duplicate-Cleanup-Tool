# Family Groups and Relationships

## Goal

Add a relationship model between persons so the system understands family structure. This enables sibling detection (pre-birth exclusion suggests family members), "show me all photos of the Campbells" queries, family timeline views, and smarter face assignment when people look alike due to genetics.

## Current Capabilities

### Person Model (Existing)

- `persons` table: id, name, birth_year, notes, is_favorite, is_hidden, reference_photo_id, photo_count
- No relationship fields or tables
- No family grouping concept
- `notes` field is the only place to store unstructured relationship info

### Face Assignment (Existing, Relevant)

- Intelligent face assignment planning doc describes sibling detection via pre-birth exclusion
- `suggest_siblings()` function proposed but needs a relationship model to work properly
- Currently no way to say "Person A and Person B are siblings"

## What Needs to Be Built

### 1. Relationship Data Model

**New table: `person_relationships`**

```sql
CREATE TABLE person_relationships (
    id INTEGER PRIMARY KEY,
    person_a_id INTEGER NOT NULL REFERENCES persons(id),
    person_b_id INTEGER NOT NULL REFERENCES persons(id),
    relationship_type TEXT NOT NULL,  -- parent, child, sibling, spouse, other
    confidence TEXT DEFAULT 'confirmed',  -- confirmed, suggested, inferred
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    UNIQUE(person_a_id, person_b_id, relationship_type)
);
```

**Relationship types:**
- `parent` - person_a is parent of person_b
- `child` - person_a is child of person_b (inverse of parent)
- `sibling` - person_a and person_b share parents
- `spouse` - married/partnered
- `other` - user-defined (cousin, grandparent, friend, etc.)

**New table: `family_groups`**

```sql
CREATE TABLE family_groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,  -- "The Campbells", "Mom's side"
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE TABLE family_group_members (
    family_group_id INTEGER REFERENCES family_groups(id),
    person_id INTEGER REFERENCES persons(id),
    role TEXT,  -- optional: "father", "mother", "child"
    PRIMARY KEY (family_group_id, person_id)
);
```

### 2. Relationship Inference

The system can suggest relationships automatically based on:

- **Co-occurrence frequency** - People who appear in many photos together are likely related
- **Last name matching** - If persons share a last name (when available), suggest family link
- **Age gaps** - A 25-year age difference suggests parent-child, a 2-year gap suggests siblings
- **Pre-birth sibling detection** - When a face matches person X but predates their birth, and person Y (existing sibling) is plausible, strengthen the sibling relationship
- **Photo context** - People at the same events, same locations, over many years

### 3. Family-Aware Face Assignment

Integration with the intelligent face assignment system:

- When a match is rejected (pre-birth, age implausible), search family members first
- Siblings get a similarity bonus when matching ambiguous faces
- Parent-child pairs: if a child's face is detected, boost the likelihood of detecting their parents in the same photo
- Family group photos: if 3 of 5 family members are identified, boost scores for the remaining 2

### 4. Family Search and Filtering

- "Show all photos containing any Campbell family member"
- "Show photos where Emma and Dad appear together"
- Filter faces panel by family group
- Family timeline: photos of the whole family over the years

## Implementation Phases

### Phase 1: Data Model and Basic UI

- Create person_relationships and family_groups tables
- Add relationship management to Faces panel:
  - Right-click person -> "Add Relationship" -> select another person + type
  - "Create Family Group" dialog
  - Display relationships on person detail view
- Store and query relationships in database.py

### Phase 2: Integration with Face Assignment

- Wire sibling relationships into pre-birth exclusion logic
- When a match is impossible, query family_group_members for alternatives
- Add relationship-based similarity adjustments:
  - Known siblings: +0.03 boost (they may look alike)
  - Known parent-child: +0.02 boost at appropriate ages
- Log relationship-based suggestions with reasoning

### Phase 3: Relationship Inference

- Analyze co-occurrence patterns across all photos
- Suggest relationships based on:
  - Top co-occurring person pairs (appear together in 50%+ of each other's photos)
  - Age gap analysis (compute from birth_year or estimated_age)
  - Name analysis (shared last names)
- Present suggestions to user for confirmation
- "These two people appear together in 847 photos. Are they related?"

### Phase 4: Family Search and Views

- Family group filter in search panel
- "Photos of [family group]" quick filter
- Family timeline view: photos containing any family member, sorted chronologically
- Family co-occurrence matrix: heatmap showing which family members appear together most
- Family group photo detection: photos where all or most family members appear

## UI Design

### Person Detail Panel (Faces Tab)

```
[Person Photo] Emma Campbell
Born: 2015 | Photos: 342

Relationships:
  Father: John Campbell (847 photos together)
  Mother: Sarah Campbell (792 photos together)
  Brother: James Campbell (523 photos together)

Family Groups:
  The Campbells (5 members)

[Add Relationship] [Create Family Group]
```

### Family Group View

```
The Campbells
  John (Dad) - 1,245 photos
  Sarah (Mom) - 1,102 photos
  James - 892 photos
  Emma - 342 photos
  Max (pet) - 267 photos  <-- pets can be family members too

[View All Photos] [View Timeline] [Add Member]
```

## Edge Cases

| Scenario | Handling |
|---|---|
| Blended families (step-siblings) | relationship_type "sibling" with notes field for detail |
| Person in multiple family groups | Supported via many-to-many family_group_members |
| Pets as family members | Allow pets in family groups (separate from person_relationships) |
| Relationship changes over time (divorce) | Keep relationship records, add end_date field if needed |
| Unknown relationships | confidence="suggested" until user confirms |
| Large extended family | Family groups can overlap; person can be in "Immediate Family" and "Extended Family" |

## Integration Points

- **Intelligent Face Assignment** (intelligent-face-assignment.md) - Sibling suggestions on pre-birth rejection
- **Age-Progression Face Recognition** (age-progression-face-recognition.md) - Family context helps temporal bridging
- **AI Summaries** - Include relationship context: "Emma with her father John at the beach"
- **Metadata Embedding** - Write family group as hierarchical tag: "Family|Campbells|Emma"
- **Search** - Filter by family group, search "photos of Emma and Dad"
- **Pet Tracking** - Pets can belong to family groups
