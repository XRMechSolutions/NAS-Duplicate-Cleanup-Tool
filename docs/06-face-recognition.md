# Face Recognition

## What It Does

The Face Recognition system finds faces in your photos, groups them by person, and lets you tag who's who. Once you've identified someone in a few photos, the app automatically finds all their other photos across your entire collection.

The standout feature: **Age Progression Tracking** - the app can follow a person from baby photos through childhood, teenage years, and into adulthood. This is especially valuable for organizing years of family photos where kids grow up.

## How It Works (The Big Picture)

### Phase 1: Detection

The app scans every photo and finds all faces:
- Locates faces in the image
- Extracts a "face embedding" - a 512-number fingerprint unique to that face
- Stores the face location and embedding in the database

### Phase 2: Clustering

With thousands of detected faces, the app groups similar faces:
- Faces that look alike are clustered together
- Each cluster represents a potential person
- You see clusters of "Unknown Person 1", "Unknown Person 2", etc.

### Phase 3: Identification

You tell the app who each cluster is:
- Look at a cluster, confirm it's all the same person
- Assign a name: "Dad", "Emma", "Grandma"
- The app learns from your labels

### Phase 4: Recognition

With labeled faces, the app finds more photos:
- Scans remaining unidentified faces
- Matches them to known people
- Asks you to confirm uncertain matches

## The Faces Tab

### Cluster View (Default)

When you first open the Faces tab, you see face clusters:

```
FACES - UNKNOWN CLUSTERS

[Cluster 1: 234 photos]     [Cluster 2: 189 photos]     [Cluster 3: 156 photos]
[grid of face thumbnails]   [grid of face thumbnails]   [grid of face thumbnails]
[Name This Person]          [Name This Person]          [Name This Person]

[Cluster 4: 98 photos]      [Cluster 5: 87 photos]      [Cluster 6: 76 photos]
[grid of face thumbnails]   [grid of face thumbnails]   [grid of face thumbnails]
[Name This Person]          [Name This Person]          [Name This Person]

Showing 6 of 45 clusters  [Show More]
```

Each cluster shows:
- Sample face thumbnails from that cluster
- How many photos contain this face
- Button to name the person

### Naming a Person

Click **Name This Person** on a cluster:

```
NAME THIS PERSON
================

[Sample faces from this cluster - 12 thumbnails]

These all appear to be the same person.

Name: [Emma                    ]

[ ] This person is a child (enable age tracking)
    Birth year (approximate): [2015    ]

[Not the Same Person]  [Cancel]  [Save]
```

**Options:**
- **Name** - Any name you want: "Emma", "Dad", "Uncle Bob"
- **Child tracking** - Enable special age progression for children
- **Birth year** - Approximate birth year helps with age estimation

**If faces don't match:** Click "Not the Same Person" to split the cluster.

### People View

Once you've named some people, switch to People View:

```
FACES - PEOPLE

[Emma - 456 photos]         [Dad - 234 photos]          [Mom - 198 photos]
[representative photo]      [representative photo]      [representative photo]
Age range: 0-9 years       Age range: 35-44           Age range: 32-41

[Grandma - 167 photos]      [Jake - 145 photos]        [Unknown - 23 clusters]
[representative photo]      [representative photo]
Age range: 65-74           Age range: 5-14

[View All People]
```

Click a person to see all their photos:

```
EMMA - 456 PHOTOS

Timeline View: [0-1 yr] [2-3 yr] [4-5 yr] [6-7 yr] [8-9 yr] [All Ages]

[Grid of photos organized by age]

2015 (Baby): 45 photos
2016 (1 year): 67 photos
2017 (2 years): 89 photos
...

[Find More Photos]  [Edit Person]  [Merge with Another Person]
```

## Age Progression Tracking

### The Challenge

A person's face changes dramatically from birth to adulthood. Standard face recognition can't match a baby photo to a teenager photo - they look too different.

### The Solution: Temporal Bridging

Instead of trying to match baby → teenager directly, the app chains through time:

```
Baby (0-1) → Toddler (2-4) → Child (5-9) → Preteen (10-12) → Teen (13-17) → Adult
```

Each transition is a smaller visual change that face recognition can handle.

### How It Works

1. **Initial clustering** groups faces that look similar
2. **Age estimation** determines approximate age in each photo
3. **Date ordering** arranges photos chronologically using EXIF dates
4. **Bridge building** connects faces across adjacent time periods
5. **Chain validation** ensures the chain makes sense (no gaps, consistent person)

### Example

Emma's photos span 9 years:

```
2015: Baby photos (cluster A)
2016-2017: Toddler photos (cluster B)
2018-2020: Young child photos (cluster C)
2021-2023: Older child photos (cluster D)
2024: Current photos (cluster E)

Without bridging: 5 separate clusters, looks like 5 different people
With bridging: All connected as one person "Emma" through time
```

### Enabling Age Tracking

For each person who is/was a child in your photos:

1. Open their profile
2. Enable "Age Progression Tracking"
3. Enter approximate birth year
4. Click "Rebuild Age Timeline"

The app re-analyzes their photos with age-aware matching.

### Manual Linking

Sometimes the automatic bridging misses a connection. You can manually link:

1. Go to person's timeline view
2. Find a gap or separate cluster
3. Drag photos into the timeline, or
4. Use **Link Faces** to manually connect clusters

### Viewing the Age Timeline

For people with age tracking enabled:

```
EMMA - AGE TIMELINE

      2015    2016    2017    2018    2019    2020    2021    2022    2023    2024
      Baby    1 yr    2 yr    3 yr    4 yr    5 yr    6 yr    7 yr    8 yr    9 yr
      ----    ----    ----    ----    ----    ----    ----    ----    ----    ----
Photos: 45      67      89      78      56      92      84      76      68      45

[Scrollable timeline of photos showing growth over time]

[Export Timeline]  [Find Missing Years]
```

## Face Detection Settings

### Detection Sensitivity

Controls how aggressively the app looks for faces:

| Setting | Behavior |
|---------|----------|
| **High** | Finds more faces, including small/partial/blurry ones. May have false positives. |
| **Medium** | Balanced detection. Misses some difficult faces but few false positives. |
| **Low** | Only clear, front-facing faces. Very few false positives. |

### Minimum Face Size

Faces smaller than this (in pixels) are ignored:
- **32px** - Catch everything, including faces in crowds
- **64px** - Default, ignores very distant faces
- **128px** - Only prominent faces

### Maximum Faces Per Photo

Limit on faces detected per image:
- **Unlimited** - Find all faces (slow for crowd photos)
- **10** - Reasonable limit for family photos
- **5** - Focus on main subjects only

## Recognition Settings

### Confidence Threshold

How sure the app must be before automatically tagging a face:

| Setting | Behavior |
|---------|----------|
| **95%+** | Very conservative. Only obvious matches. Lots of "Unknown" faces. |
| **90%** | Balanced. Good matches, occasional errors. |
| **85%** | Permissive. More automatic matches, but review suggested. |
| **80%** | Aggressive. Many matches, expect some mistakes. |

### Unknown Face Handling

When a face doesn't match anyone known:
- **Add to clusters** - Group with similar unknown faces
- **Mark for review** - Flag for manual identification
- **Ignore** - Don't track unrecognized faces

## The Labeling Workflow

### Efficient Bulk Labeling

When you have many unknown clusters:

1. **Sort by size** - Start with largest clusters (most photos)
2. **Quick review** - Scroll through thumbnails to verify same person
3. **Name and save** - Assign name, move to next cluster
4. **Merge duplicates** - If same person split into multiple clusters, merge them

### Handling Errors

**Same person in multiple clusters:**
1. Name one cluster
2. Go to the other cluster
3. Click **Merge with Existing Person**
4. Select the correct person

**Different people in one cluster:**
1. Click **Split Cluster**
2. Select the faces that don't belong
3. They form a new cluster (or merge with existing person)

**Wrong identification:**
1. Go to the person's photo list
2. Find the wrong photo
3. Click **Remove from Person**
4. The face returns to unknown clusters

### Suggested Matches

The app proactively suggests matches:

```
SUGGESTED MATCHES

We found faces that might be these people:

[Face thumbnail] → Might be Emma (87% confident)
  [Yes, this is Emma]  [No]  [Skip]

[Face thumbnail] → Might be Dad (92% confident)
  [Yes, this is Dad]  [No]  [Skip]

12 more suggestions available
[Review All]  [Auto-accept 90%+]
```

## Finding All Photos of a Person

### Automatic Scanning

Click **Find More Photos** on any person:

1. App searches all unidentified faces
2. Shows potential matches with confidence scores
3. You confirm or reject each match
4. Confirmed faces are added to the person

### Manual Search

Can't find someone's photo? Use manual search:

1. Go to a photo you know contains them
2. Click on their face
3. Select **Find Similar Faces**
4. Results show faces that look similar

## Exporting Face Data

### Photo Collections by Person

Export all photos containing a specific person:

1. Go to person's profile
2. Click **Export Photos**
3. Choose: Copy to folder / Create album / Export list

### Face Report

Generate a report of all identified people:

```
FACE RECOGNITION REPORT

Total photos analyzed: 127,453
Photos with faces: 89,234
Faces detected: 156,789

People identified: 23
  Emma: 456 photos
  Dad: 234 photos
  Mom: 198 photos
  ...

Unknown faces: 12,456 (in 45 clusters)
```

## Models and Libraries

### InsightFace

Primary face recognition library:
- **Model:** buffalo_l (large model, best accuracy)
- **Face detection:** RetinaFace detector
- **Embedding:** ArcFace, 512-dimensional vectors
- **Performance:** ~50 faces/second on GPU

Why InsightFace:
- Best open-source accuracy
- Good cross-age performance
- Active development
- Works offline (no cloud required)

### Age Estimation

Uses InsightFace's age estimation:
- Estimates apparent age from face
- Helps with temporal bridging
- Not perfect - use as guidance, not gospel

### Alternative: DeepFace (Fallback)

If InsightFace has issues, DeepFace provides:
- Multiple backend options
- Similar accuracy
- Age and gender estimation
- Emotion detection (bonus)

### scikit-learn

For face clustering:
- DBSCAN clustering algorithm
- Handles variable cluster sizes
- No need to specify number of people in advance

## Performance

### Processing Speed

| Hardware | Speed |
|----------|-------|
| NVIDIA RTX 3080 | ~50 faces/sec |
| NVIDIA GTX 1660 | ~20 faces/sec |
| CPU only (modern) | ~2 faces/sec |

### Memory Usage

- Model loaded: ~2 GB GPU memory
- Per-face embedding: 2 KB
- 100,000 faces: ~200 MB database storage

### First-Time Processing

Initial face detection on 100,000 photos:
- GPU: ~30 minutes
- CPU: ~8-10 hours

Runs in background, progress shown in status bar.

## Privacy

### All Processing is Local

- No photos sent to cloud services
- No internet required after model download
- Face embeddings stored locally only

### Data Security

- Face embeddings can't be reversed to photos
- Database can be encrypted
- Delete person = delete all their face data

## Technical Details

### Face Embedding Storage

Embeddings stored as BLOBs in SQLite:
- 512 float values (32-bit each)
- 2,048 bytes per face
- Indexed for fast similarity search

### Similarity Calculation

Cosine similarity between embeddings:
- 1.0 = identical faces
- 0.9+ = very likely same person
- 0.7-0.9 = possible match, needs review
- <0.7 = probably different people

### Clustering Algorithm

DBSCAN with cosine distance:
- eps=0.5 (similarity threshold)
- min_samples=3 (minimum faces to form cluster)
- Handles noise and outliers well

### Multi-Embedding Storage

For better cross-age matching, we store multiple embeddings per person:
- Baby embedding (0-2 years)
- Toddler embedding (2-5 years)
- Child embedding (5-12 years)
- Teen embedding (13-17 years)
- Adult embedding (18+ years)

When matching a new face:
1. Compare against all embeddings for the person
2. Use the best match (highest similarity)
3. Weight by temporal proximity (recent photos match better to recent embeddings)

### Temporal Bridging Technical Details

The bridging algorithm:
1. **Sort faces by photo date** - EXIF DateTimeOriginal
2. **Calculate time gaps** - Days between consecutive photos
3. **Apply variable thresholds**:
   - Same day: Accept similarity > 0.5
   - Same month: Accept similarity > 0.6
   - Same year: Accept similarity > 0.7
   - Different years: Accept similarity > 0.8
4. **Build chains** - Connect faces through time
5. **Validate chains** - Ensure no impossible jumps (e.g., baby -> elderly)

---

## Pet Tracking

### Overview

DupliCleaner can also track your pets through time! Like children, pets change dramatically from puppy/kitten to adult. The same temporal bridging approach applies.

### How Pet Recognition Works

1. **Detection** - YOLO detects dogs, cats, and other animals
2. **Species/Breed Classification** - Identifies breed when possible
3. **Visual Embedding** - Extracts visual features for matching
4. **Color Analysis** - Coat color and markings help distinguish similar pets
5. **Age Stage Estimation** - Baby, young, adult, senior

### Pet Tracking Challenges

Pets are harder than humans because:
- No "pet face recognition" models as mature as human face recognition
- Multiple pets of same breed look very similar
- Coat can change color with age (especially puppies)

### Our Approach

We combine multiple signals:
- **Visual embedding** - Overall appearance
- **Color histogram** - Fur color distribution
- **Breed detection** - Narrows down possibilities
- **Markings** - Distinctive spots, patches, etc.
- **Size estimation** - Relative size in photos
- **Temporal proximity** - Photos close in time more likely same pet

### Life Stages for Pets

```
Dogs:
Puppy (0-1 yr) -> Adolescent (1-2 yr) -> Adult (2-7 yr) -> Senior (7+ yr)

Cats:
Kitten (0-1 yr) -> Young (1-2 yr) -> Adult (2-10 yr) -> Senior (10+ yr)
```

### Pet Timeline View

```
MAX (Golden Retriever) - 234 PHOTOS

Timeline: [Puppy] [Young] [Adult] [All]

2020 (Puppy): 45 photos
2021 (1 year): 56 photos
2022 (2 years): 48 photos
2023 (3 years): 52 photos
2024 (4 years): 33 photos

[Find More Photos]  [Edit Pet]  [Merge with Another Pet]
```

### Naming Pets

Same workflow as people:
1. View pet clusters
2. Assign name, species, breed
3. Optionally add birth year for age tracking
4. App learns and finds more photos

### Multiple Similar Pets

If you have multiple pets of the same breed:
- Add distinguishing notes (markings, size, collar color)
- Review matches more carefully
- App prioritizes temporal continuity (same pet appears across time)
