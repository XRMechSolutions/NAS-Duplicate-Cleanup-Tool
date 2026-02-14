# Celebrity Face Identification

## Goal

Extend DupliCleaner's existing face detection and clustering pipeline to identify public figures and celebrities in photos and scanned documents. Unknown faces that match known public figures should be automatically labeled with names and metadata.

## Current Capabilities

- Face detection and embedding extraction (InsightFace/ArcFace)
- Face clustering by similarity
- User-assisted labeling of face clusters
- Face embedding storage in SQLite
- Face thumbnail cropping and display

## Proposed Approaches

### Option A: Cloud API - Amazon Rekognition

- **API**: `RecognizeCelebrities` endpoint
- **Pros**: Purpose-built, high accuracy, returns structured data (name, confidence, URLs, known-for info)
- **Cons**: Pay-per-use (~$1/1,000 images), requires internet, sends face crops to AWS
- **Integration point**: After face detection, send unknown face crops to Rekognition before clustering

### Option B: Cloud API - Google Cloud Vision

- **API**: Celebrity detection via label/entity detection
- **Pros**: Broad coverage, same infrastructure as Google Lens
- **Cons**: Pay-per-use, requires internet, privacy considerations

### Option C: Local Celebrity Embedding Database

- **Approach**: Download or build a reference database of celebrity face embeddings, match unknown faces using cosine similarity (same technique as existing clustering)
- **Pros**: Free, fully offline, private
- **Cons**: Limited to celebrities in the reference database, lower accuracy than cloud APIs, requires maintaining the database
- **Sources for embeddings**: VGGFace2 dataset, MS-Celeb-1M, or scrape and embed from public sources

### Option D: Reverse Image Search API

- **APIs**: SerpAPI (Google Lens), Bing Visual Search
- **Pros**: Broadest coverage, finds non-celebrities too
- **Cons**: Pay-per-use, slower, less structured results

## Recommended Implementation

1. **Phase 1**: Integrate Amazon Rekognition as the primary cloud option (best accuracy-to-effort ratio)
2. **Phase 2**: Build a local celebrity embedding database as a free/offline fallback
3. **Phase 3**: Optional reverse image search integration for edge cases

## Integration Design

### Workflow

1. User scans a collection containing unknown faces
2. Face detection runs as normal, faces are clustered
3. For unclustered/unknown faces, user can trigger "Identify Celebrities" action
4. System sends face crops to selected provider (cloud API or local DB)
5. Matches above confidence threshold are auto-labeled
6. Uncertain matches are presented to user for confirmation
7. Confirmed identities are stored as named persons in the existing face database

### UI Additions

- "Identify Unknown Faces" button in Faces tab
- Provider selection in settings (Rekognition, local DB, etc.)
- Confidence threshold slider
- Review queue for uncertain matches

### Data Model

- Extend person records with `source` field (manual, rekognition, local_db, etc.)
- Store match confidence alongside identification
- Store external metadata (links, known-for info) when available from APIs

## API Key Management

- Use existing keystore infrastructure (Windows DPAPI/keyring)
- AWS credentials stored securely alongside existing API keys
- Configuration in settings panel
