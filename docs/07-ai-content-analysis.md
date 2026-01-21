# AI Content Analysis

## What It Does

The AI Content Analysis system understands what's in your photos - not just faces, but scenes, objects, activities, and even text. This enables powerful features:

- **Scene Classification** - Is this a beach, mountain, restaurant, or birthday party?
- **Object Detection** - What objects are in the photo? Dog, car, cake, Christmas tree?
- **Semantic Search** - Find photos by describing them: "sunset at the beach"
- **Quality Scoring** - Which photo in a set is the sharpest and best exposed?
- **OCR (Text Extraction)** - Read text from screenshots, documents, signs

## Scene Classification

### How It Works

The app uses CLIP (Contrastive Language-Image Pre-training) to classify scenes. CLIP understands both images and text, so it can match photos to descriptive categories.

**Built-in Categories:**

| Category | Detects |
|----------|---------|
| Beach | Ocean, sand, coastal scenes |
| Mountain | Peaks, hiking, alpine scenery |
| Forest | Woods, trees, nature trails |
| City | Urban environments, buildings, streets |
| Indoor | Interior rooms, houses, offices |
| Restaurant | Dining, food service establishments |
| Party | Celebrations, gatherings |
| Wedding | Ceremonies, receptions, bridal |
| Birthday | Cake, candles, celebration |
| Sports | Athletic activities, games |
| Travel | Airports, landmarks, tourism |
| Nature | Wildlife, plants, landscapes |
| Portrait | Single person focus |
| Group Photo | Multiple people posed |
| Document | Papers, forms, text documents |
| Screenshot | Screen captures |
| Food | Meals, cooking, ingredients |
| Pet | Dogs, cats, animals |
| Vehicle | Cars, bikes, transportation |
| Art | Paintings, sculptures, creative works |

### Viewing Scene Tags

Go to any photo and see its AI analysis:

```
PHOTO ANALYSIS

Scene Classification:
  Beach:       94%
  Nature:      87%
  Travel:      76%
  Outdoor:     99%

Objects Detected:
  umbrella, towel, waves, sand, person

Quality Score: 8.2/10
  Sharpness: 9.1
  Exposure: 7.8
  Composition: 7.6
```

### Custom Categories

Add your own categories in **Settings > AI > Custom Scene Categories**:

```
CUSTOM CATEGORIES

Add categories specific to your collection:

[Christmas decorations    ] [Add]
[Soccer game             ] [Add]
[Grandma's house         ] [Add]

Current custom categories:
  - Christmas decorations
  - Soccer game (remove)
  - School events (remove)
```

The AI learns to recognize your custom categories based on the description.

### Filtering by Scene

In any photo view, filter by scene:

```
PHOTOS - FILTERED VIEW

Filter: Scene = [Beach ▼]

Showing 2,341 photos tagged "Beach"

[Photo grid]

Other filters: [Date Range] [Person] [Location] [Quality]
```

## Object Detection

### How It Works

The app uses YOLOv8 (You Only Look Once) to detect objects in photos. It identifies:

- **People** - Individuals and groups
- **Animals** - Dogs, cats, birds, horses, etc.
- **Vehicles** - Cars, bikes, boats, planes
- **Furniture** - Chairs, tables, beds, sofas
- **Electronics** - TVs, phones, laptops
- **Sports equipment** - Balls, rackets, skis
- **Food items** - Specific dishes, fruits, drinks
- **Outdoor items** - Trees, flowers, buildings

### Object Tags

Each detected object is tagged with:
- Object type (e.g., "dog")
- Confidence score (e.g., 94%)
- Location in image (bounding box)

### Searching by Object

Find all photos containing specific objects:

```
SEARCH: Contains object "dog"

Results: 1,234 photos

[Photo grid showing all photos with dogs]

Refine: [Also contains: person] [Exclude: indoor]
```

### Combined Queries

Combine scene and object searches:
- "Beach photos with dogs" - Scene=beach AND object=dog
- "Birthday party with cake" - Scene=birthday AND object=cake
- "Group photos outdoors" - Scene=outdoor AND object=multiple people

## Semantic Search

### Natural Language Queries

The most powerful feature: search using plain English descriptions.

**Examples:**

| Query | Finds |
|-------|-------|
| "sunset at the beach" | Beach photos during sunset |
| "kids playing in snow" | Children in winter/snow scenes |
| "birthday cake with candles" | Birthday celebration photos |
| "dog running in park" | Action shots of dogs outdoors |
| "family dinner at restaurant" | Group dining photos |

### How It Works

CLIP encodes both images and text into the same mathematical space. When you search:

1. Your query is encoded into a vector
2. All images are already encoded (done during analysis)
3. App finds images whose vectors are closest to your query vector
4. Results ranked by similarity

### Search Interface

```
SEMANTIC SEARCH

[sunset beach vacation                ] [Search]

Results (sorted by relevance):

[Photo] 94% match - Beach sunset, Hawaii 2023
[Photo] 91% match - Ocean view evening
[Photo] 89% match - Coastal sunset
[Photo] 85% match - Beach day afternoon
...

Showing 50 of 234 results [Load More]
```

### Search Tips

- **Be specific**: "golden retriever puppy" works better than just "dog"
- **Include context**: "wedding ceremony outdoor" narrows results
- **Describe the scene**: "crowded city street at night" vs just "city"
- **Use emotional words**: "happy birthday celebration" vs "birthday"

### Saved Searches

Save frequent searches for quick access:

```
SAVED SEARCHES

[+] Add current search

- Beach vacations (sunset beach vacation)
- Kids activities (children playing outside)
- Holiday dinners (family dinner celebration)
- Pet photos (dog or cat cute)

Click to run | Right-click to edit/delete
```

## Quality Scoring

### What It Measures

Each photo gets a quality score (0-10) based on:

| Metric | Weight | Measures |
|--------|--------|----------|
| **Sharpness** | 35% | Focus quality, blur detection |
| **Exposure** | 30% | Brightness, contrast, dynamic range |
| **Composition** | 20% | Rule of thirds, subject placement |
| **Noise** | 15% | Graininess, ISO artifacts |

### Using Quality Scores

**Finding Best Photos:**

When reviewing duplicates or burst photos, quality scores help pick the best:

```
BURST PHOTOS - 12 SIMILAR IMAGES

Quality Ranking:
1. IMG_4523.jpg - Score: 9.2 (Best) ← Recommended
2. IMG_4524.jpg - Score: 8.8
3. IMG_4521.jpg - Score: 8.4
4. IMG_4522.jpg - Score: 7.9 (Slightly blurry)
...

[Keep Best Only] [Keep Top 3] [Review All]
```

**Filtering Low Quality:**

Find and review low-quality photos:

```
LOW QUALITY PHOTOS

Filter: Quality Score < 5.0

Found: 456 photos

Common issues:
- Blurry/out of focus: 234
- Underexposed (too dark): 123
- Overexposed (too bright): 67
- High noise: 32

[Review] [Auto-select for deletion] [Export list]
```

### Quality Criteria Details

**Sharpness (Blur Detection):**
- Uses Laplacian variance algorithm
- Detects motion blur, focus issues
- Score 1-10: 1=very blurry, 10=tack sharp

**Exposure:**
- Analyzes histogram distribution
- Checks for clipped highlights/shadows
- Score 1-10: 5=perfect, 1=very dark, 10=very bright

**Composition:**
- Detects faces/subjects and their placement
- Checks rule of thirds alignment
- Score 1-10: 10=textbook composition

**Noise:**
- Estimates signal-to-noise ratio
- Higher in low-light/high-ISO photos
- Score 1-10: 10=clean, 1=very noisy

## OCR (Text Extraction)

### What It Does

OCR (Optical Character Recognition) reads text from:
- Screenshots
- Document photos
- Signs and labels
- Whiteboards
- Receipts
- Business cards

### When It Runs

OCR runs automatically on:
- Detected screenshots
- Photos classified as "document"
- Any image with significant text regions

You can also manually trigger OCR on any image.

### Searching Extracted Text

Once text is extracted, it's searchable:

```
TEXT SEARCH

Search: [tax return 2023              ] [Search]

Found in 3 images:

[Screenshot] "...Tax Return 2023 - Form 1040..."
  Path: Screenshots/2024-04/tax_screenshot.png

[Document photo] "...IRS Tax Return 2023..."
  Path: Documents/Scans/taxes_2023.jpg

[Photo] "...2023 Tax Preparation..."
  Path: Photos/2024/office_whiteboard.jpg
```

### OCR Languages

Supports multiple languages:
- English (default)
- Spanish, French, German, Italian
- Chinese, Japanese, Korean
- Arabic, Hebrew (right-to-left)

Configure in **Settings > AI > OCR Languages**.

### OCR Accuracy

Accuracy depends on:
- Image quality (resolution, focus)
- Text clarity (font, size, contrast)
- Language complexity

**Good OCR results:** Printed text, screenshots, typed documents
**Poor OCR results:** Handwriting, artistic fonts, low resolution

## AI Summaries

### What It Does

Beyond tags and categories, DupliCleaner generates rich natural language summaries of your photos and documents. Instead of just "beach, sunset, dog", you get:

> "Emma and Dad building a sandcastle on Venice Beach at sunset, with Max the golden retriever playing in the waves nearby. The sky has beautiful orange and pink colors."

### Summary Features

**For Photos:**
- Who's in the photo (people and pets by name)
- What they're doing (activities)
- Where it was taken (location context)
- Time of day and season/weather
- Mood and atmosphere

**For Documents:**
- Document type (invoice, receipt, letter, form)
- Key information summary
- Important entities (names, dates, amounts)
- Topic classification

### Viewing Summaries

Click any photo to see its AI summary:

```
PHOTO DETAILS

AI Summary:
"Family gathering for Thanksgiving dinner at Grandma's house. Mom, Dad,
Emma (age 7), and Uncle Bob are seated around the dining table. A
large turkey is the centerpiece. Everyone appears happy and festive."

People: Mom, Dad, Emma, Uncle Bob, Grandma
Activities: dining, celebrating, gathering
Mood: festive, happy
Location: indoor, home
Event type: holiday, Thanksgiving

Tags: #thanksgiving #family #dinner #holiday
```

### AI Model Options

You can choose which AI generates summaries:

**Local Models (Free, Private):**
- LLaVA 13B - Good quality, runs on your GPU
- LLaVA 7B - Faster, slightly lower quality

**Cloud APIs (Your Own Key):**
- OpenAI GPT-4 Vision - Excellent quality
- Anthropic Claude 3 - Excellent quality
- Google Gemini Pro Vision - Good quality

Cloud APIs require your own API key, stored securely on your device.

### Summary Settings

Configure in **Settings > AI > Summaries**:

```
SUMMARY SETTINGS

[x] Enable AI summaries

Provider: [Local (LLaVA) ▼]
  - Local (LLaVA) - Free, private
  - OpenAI GPT-4V - Best quality (API key required)
  - Anthropic Claude - Best quality (API key required)
  - Google Gemini - Good quality (API key required)

Detail level: [Rich ▼]
  - Brief - 1-2 sentences
  - Standard - 3-4 sentences
  - Rich - Full description with context

Include in summary:
  [x] People names (from face recognition)
  [x] Pet names (from pet tracking)
  [x] Location (from GPS/EXIF)
  [x] Activities and mood
  [x] Time of day/season
```

### Searching Summaries

Summaries are fully searchable:

```
SEARCH: "birthday cake with candles"

Results from AI summaries:

[Photo] "Emma's 7th birthday party. She's blowing out candles on a
        chocolate cake decorated with rainbow sprinkles..."

[Photo] "Jake's birthday celebration at the park. A homemade cake
        with 10 candles is on the picnic table..."
```

---

## Smart Tagging

### Automatic Tags

The app automatically generates tags from multiple sources:

| Source | Example Tags |
|--------|--------------|
| Scene Detection | #beach, #mountain, #wedding |
| Object Detection | #dog, #car, #cake |
| Face Recognition | #emma, #dad, #grandma |
| Pet Recognition | #max, #whiskers |
| EXIF Data | #2024, #january, #newyork |
| AI Summary | #birthday, #celebration, #outdoor |

### Tag Categories

Tags are organized by category:

- **People**: Names of identified people
- **Pets**: Names of identified pets
- **Places**: Locations and venues
- **Activities**: What's happening
- **Objects**: Things in the photo
- **Events**: Occasions and celebrations
- **Custom**: Your own tags

### Managing Tags

```
PHOTO TAGS

AI-generated tags (confidence):
  #beach (94%)  #sunset (89%)  #vacation (76%)

Face/Pet tags:
  #emma  #max

User tags:
  #favorites  #print-worthy

[+ Add Tag]

All tags: beach, sunset, vacation, emma, max, favorites, print-worthy
```

### Tag Confidence

AI-generated tags include confidence scores:
- 90%+ : Very confident, shown by default
- 70-90% : Confident, shown by default
- 50-70% : Uncertain, shown with (?) marker
- <50% : Low confidence, hidden by default

Adjust the threshold in **Settings > AI > Tag Confidence Threshold**.

### Editing Tags

You can always edit tags:
- Remove incorrect AI tags
- Add your own tags
- Correct misspellings
- Merge similar tags

User edits are preserved and override AI suggestions.

---

## Models and Libraries

### CLIP (OpenAI)

**What it does:** Scene classification, semantic search
**Model:** open-clip ViT-L/14 (via open-clip-torch)
**Size:** ~1.5 GB
**Speed:** ~100 images/second on GPU

Why CLIP:
- Understands images AND text together
- Zero-shot classification (no training needed)
- Excellent for semantic search
- Active open-source community

### YOLOv8 (Ultralytics)

**What it does:** Object detection
**Model:** yolov8l (large model)
**Size:** ~200 MB
**Speed:** ~50 images/second on GPU

Why YOLOv8:
- State-of-the-art object detection
- Very fast inference
- Detects 80+ object categories
- Easy to use Python API

### EasyOCR

**What it does:** Text extraction
**Model:** Multiple language models
**Size:** ~100-500 MB depending on languages
**Speed:** ~5-20 images/second on GPU

Why EasyOCR:
- Multi-language support
- Good accuracy on various text types
- Handles skewed/rotated text
- Pure Python, easy to integrate

### Quality Scoring

**What it does:** Image quality assessment
**Implementation:** Custom algorithms using OpenCV
**No separate model needed**

Algorithms:
- Laplacian variance (sharpness)
- Histogram analysis (exposure)
- Edge detection (composition)
- Noise estimation (signal analysis)

## Processing Pipeline

### Analysis Phases

When you run AI analysis on your photos:

1. **Phase 1: Scene/Search Embeddings** (CLIP)
   - Encode all images for semantic search
   - Classify into scene categories
   - ~100 images/second

2. **Phase 2: Object Detection** (YOLO)
   - Detect objects in each image
   - Store object tags and locations
   - ~50 images/second

3. **Phase 3: Quality Scoring**
   - Calculate quality metrics
   - Very fast, CPU-based
   - ~500 images/second

4. **Phase 4: OCR** (selective)
   - Only on screenshots/documents
   - Extract and index text
   - ~10 images/second

### Progress Display

```
AI ANALYSIS

Processing: 45,234 images

Phase 1: Scene Analysis [=========>          ] 45%
  23,456 / 45,234 images
  Speed: 98 images/sec
  ETA: 4 minutes

Phase 2: Object Detection - Waiting
Phase 3: Quality Scoring - Waiting
Phase 4: OCR (2,341 documents) - Waiting

[Pause] [Cancel] [Run in Background]
```

### Background Processing

Click **Run in Background** to:
- Continue analysis while using other features
- See progress in status bar
- Get notified when complete

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| Scene Categories | Built-in | Which scene types to detect |
| Custom Categories | None | User-defined categories |
| Object Detection | On | Enable/disable YOLO |
| Min Object Confidence | 70% | Threshold for object tags |
| Quality Scoring | On | Calculate quality metrics |
| Auto-OCR | On | OCR on detected documents |
| OCR Languages | English | Languages for text extraction |
| Batch Size | 32 | Images per GPU batch |
| GPU Memory Limit | 6 GB | Max VRAM usage |
