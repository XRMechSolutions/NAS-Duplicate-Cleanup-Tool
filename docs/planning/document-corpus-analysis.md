# Document Corpus Analysis

## Goal

Add document corpus analysis capabilities to DupliCleaner for extracting meaning, patterns, and relationships from large collections of scanned documents, emails, and text files. Enable users to discover repeated terms, unusual language patterns, code words, entity relationships, and communication networks across a document collection.

## Current Capabilities

- OCR text extraction (EasyOCR, Tesseract)
- FTS5 full-text search indexing
- AI-powered content summaries (LMStudio, Ollama, cloud LLMs)
- Document type detection (screenshots, documents, photos)
- SQLite storage for extracted text and metadata

## Proposed Features

### 1. Term Frequency Analysis

- Calculate TF-IDF (term frequency-inverse document frequency) across the corpus
- Surface unusually repeated words and phrases that stand out from normal language
- Highlight terms that appear frequently in the collection but are rare in general English
- Configurable stop-word lists to filter common words
- N-gram analysis (bigrams, trigrams) to catch repeated multi-word phrases

### 2. Co-occurrence and Contextual Mapping

- Identify which terms frequently appear together in the same documents or paragraphs
- Build co-occurrence matrices to visualize term relationships
- Flag terms used in unusual or unexpected contexts
- LLM-assisted contextual analysis to identify language that seems out of place

### 3. Entity Extraction (NER)

- Extract named entities: people, organizations, locations, dates, monetary amounts
- Build an entity database linked back to source documents
- Cross-reference entities across documents to find connections
- Libraries: spaCy, Hugging Face transformers, or LLM-based extraction

### 4. Communication Network Analysis

- For email collections: map sender/recipient relationships
- Build communication graphs showing who talked to whom and how often
- Identify clusters of frequent communicators
- Timeline visualization of communication patterns
- Libraries: NetworkX for graph analysis, optional visualization export

### 5. Timeline and Chronological Analysis

- Extract dates from documents (OCR, metadata, content parsing)
- Build chronological timelines of events mentioned across documents
- Correlate document dates with entity appearances
- Identify temporal clusters of activity

### 6. Pattern and Anomaly Detection

- Statistical analysis to flag documents or language that deviates from the norm
- Identify potential code words: terms with unusually high frequency or unusual context
- Cluster documents by topic using embedding similarity
- LLM-assisted analysis to flag passages that seem coded or ambiguous

## Implementation Phases

### Phase 1: Text Pipeline

- Batch OCR processing for document collections
- Text cleaning and normalization
- FTS5 indexing (already exists, extend as needed)
- Basic term frequency and TF-IDF reporting

### Phase 2: Entity and Relationship Extraction

- NER pipeline (spaCy or transformer-based)
- Entity database with source document linking
- Basic relationship mapping (entity co-occurrence)

### Phase 3: Communication Analysis

- Email header parsing (sender, recipient, date, subject)
- Communication graph construction
- Frequency and timeline analysis

### Phase 4: Advanced Pattern Detection

- LLM-assisted contextual analysis for anomalous language
- N-gram and co-occurrence visualization
- Topic clustering using document embeddings
- Exportable reports and visualizations

## UI Additions

### Corpus Analysis Tab

- Document collection selector (folder or scan subset)
- Analysis type selector (term frequency, entities, network, patterns)
- Results panel with sortable/filterable tables
- Click-through from any result to the source document and highlighted passage

### Visualizations

- Word cloud / term frequency charts
- Entity relationship graphs
- Communication network diagrams
- Timeline views
- Co-occurrence heat maps

### Export

- CSV/JSON export of all analysis results
- Graph export (GEXF, GraphML) for external tools like Gephi
- PDF report generation

## Technology Stack

### NLP / Text Analysis
- **spaCy**: Entity extraction, tokenization, linguistic analysis
- **scikit-learn**: TF-IDF, clustering, statistical analysis
- **NLTK**: N-grams, stop words, text preprocessing (alternative to spaCy)

### Graph / Network
- **NetworkX**: Graph construction and analysis
- **pyvis** or **Graphviz**: Graph visualization

### LLM Integration
- Existing LMStudio/Ollama integration for contextual analysis
- Prompt engineering for code word detection and anomaly flagging

### Visualization
- **matplotlib** / **plotly**: Charts and graphs within the UI or exported
- **DearPyGUI plot widgets**: Inline charts where possible

## Data Model Extensions

- `corpus_terms` table: term, frequency, tf_idf_score, document_count
- `entities` table: entity_text, entity_type, source_file_id, context_snippet
- `entity_relationships` table: entity_a_id, entity_b_id, co_occurrence_count, relationship_type
- `communications` table: sender, recipient, date, subject, source_file_id
- `analysis_sessions` table: track which analyses have been run on which collections
