# Pet Detection and Tracking

## Goal

Extend DupliCleaner's pet detection from basic YOLO-based detection and color histogram matching into a full pet tracking system that can follow individual animals across years of photos, identify breeds, and integrate pet information into search and organization workflows.

## Current Capabilities (Working)

- **YOLO-based detection** - YOLOv8n detects dogs, cats, and birds in images (pets.py)
- **Color histogram matching** - HSV histogram comparison to distinguish pets by coat color/markings
- **DBSCAN clustering** - Groups unassigned pet detections into clusters by color similarity
- **Pet management** - Create named pets, assign detections, basic timeline by year
- **Batch analysis** - Process multiple files with progress tracking and cancellation
- **Age stage estimation** - Rough heuristic based on bounding box size (baby/young/adult/senior)
- **Database model** - Pet, PetDetection tables with all needed fields

## What's Incomplete

### 1. Visual Embedding-Based Matching (Partially Stubbed)

**Current state:** `DetectedPet.visual_embedding` field exists but is never populated. Only color histograms are used for matching.

**Needed:**
- Extract visual feature embeddings using a CNN (ResNet50, EfficientNet, or CLIP)
- Store embeddings alongside color histograms
- Use embedding similarity as primary matching signal, color as secondary
- Combine both signals for more robust matching

### 2. Breed Classification (Not Implemented)

**Current state:** `PetDetection.breed` field exists in DB schema but is never populated.

**Needed:**
- Post-detection breed classifier (YOLO only detects "dog"/"cat", not breed)
- Options: fine-tuned ResNet/EfficientNet on Stanford Dogs dataset, or CLIP zero-shot classification
- Use breed as a matching signal (two Golden Retrievers more likely to be the same pet)
- Display breed in UI alongside pet name

### 3. Temporal Tracking Across Years (Not Implemented)

**Current state:** `get_pet_timeline()` returns photos grouped by year, but no temporal bridging logic connects a puppy to the same adult dog.

**Needed:**
- Same temporal bridging approach as face recognition: lower similarity thresholds for temporally adjacent photos
- Multi-embedding storage per pet at different life stages
- Chain building: Puppy photos (Year 1) -> Young dog (Year 2) -> Adult (Year 3+)
- Handle appearance changes: coat color shifts, size changes, markings developing

### 4. Integration with AI Summaries and Tags (Not Implemented)

**Current state:** Pet detections are stored but not surfaced in summaries or search tags.

**Needed:**
- Auto-tag photos with pet names when detected
- Include pet info in AI summaries ("Max the Golden Retriever playing in the yard")
- Enable search by pet name
- Cross-reference with face detection (photos with both people and their pets)

## Implementation Phases

### Phase 1: Visual Embeddings

- Add CNN-based feature extraction after YOLO detection
- Store embeddings in database
- Update matching to use embedding cosine similarity as primary signal
- Retrain/re-cluster existing detections with improved matching

### Phase 2: Breed Classification

- Integrate breed classifier (CLIP zero-shot is simplest, fine-tuned model is most accurate)
- Populate breed field for all detections
- Use breed as a clustering signal
- Display breed in Faces/Pets UI panel

### Phase 3: Temporal Tracking

- Implement temporal bridging (same pattern as face age-progression)
- Multi-embedding storage per pet per life stage
- Lower thresholds for temporally close photos
- Gap detection: alert user to missing years in pet timeline
- Handle multi-pet households (distinguish between two dogs of same breed)

### Phase 4: Integration

- Auto-generate tags from pet detections
- Include pet names in AI summaries
- Enable pet-based search
- Pet timeline view in UI (photos of a pet organized chronologically)
- People-with-pets grouping (show which people appear with which pets)

## Technical Considerations

### Model Selection for Embeddings

| Option | Pros | Cons |
|--------|------|------|
| ResNet50 (ImageNet) | Fast, widely available | Not specialized for pets |
| CLIP ViT | Already loaded for other features, good general features | May not capture fine pet details |
| Fine-tuned on pet datasets | Best accuracy | Requires training or finding pre-trained model |

### Multi-Pet Households

- Color histograms alone can't distinguish two black cats
- Embeddings + breed + size + facial markings needed
- User confirmation essential for ambiguous cases
- Allow manual split/merge of pet clusters

### Performance

- YOLO detection is fast (~50ms per image on GPU)
- Embedding extraction adds ~20ms per detection
- Breed classification adds ~10ms per detection
- Total overhead per image: minimal when batched with GPU

## Database Schema (Existing, Needs Extension)

- `pets` table: id, name, breed, species, color_description, birth_year, notes
- `pet_detections` table: id, file_id, pet_id, bbox, confidence, color_histogram, breed, visual_embedding
- **New:** `pet_embeddings` table: pet_id, age_stage, embedding, created_date (multi-embedding storage)
