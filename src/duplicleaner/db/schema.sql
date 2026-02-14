-- DupliCleaner Database Schema
-- SQLite database for storing scan results, duplicates, and AI analysis

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Application settings (key-value store)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Registered drives/sources
CREATE TABLE IF NOT EXISTS drives (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    path TEXT NOT NULL,
    last_scan TIMESTAMP,
    total_space INTEGER,
    free_space INTEGER,
    file_count INTEGER DEFAULT 0,
    is_network BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- All scanned files
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drive_id TEXT NOT NULL REFERENCES drives(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    created TIMESTAMP,
    modified TIMESTAMP,
    file_type TEXT,
    mime_type TEXT,
    quick_hash TEXT,
    content_hash TEXT,
    perceptual_hash TEXT,
    scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    UNIQUE(drive_id, path)
);

-- File metadata (EXIF, dimensions, etc.)
CREATE TABLE IF NOT EXISTS file_metadata (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    exif_date TIMESTAMP,
    gps_lat REAL,
    gps_lon REAL,
    location_name TEXT,
    camera_make TEXT,
    camera_model TEXT,
    width INTEGER,
    height INTEGER,
    duration_seconds REAL,
    orientation INTEGER,
    raw_exif TEXT  -- JSON
);

-- Thumbnails stored as BLOBs
CREATE TABLE IF NOT EXISTS thumbnails (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    thumbnail BLOB,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Duplicate groups
CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_type TEXT NOT NULL,  -- 'exact' or 'near'
    similarity REAL DEFAULT 1.0,
    file_count INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0,
    wasted_size INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- 'pending', 'resolved', 'ignored'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- Members of duplicate groups
CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    is_keeper BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (group_id, file_id)
);

-- People (for face recognition)
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    birth_year INTEGER,         -- Approximate birth year for age progression
    notes TEXT,                 -- User notes about the person
    is_favorite BOOLEAN DEFAULT FALSE,
    is_hidden BOOLEAN DEFAULT FALSE,  -- Hidden/ignored persons (unknown faces user wants to hide)
    reference_photo_id INTEGER, -- Best photo for identification
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    photo_count INTEGER DEFAULT 0
);

-- Detected faces
CREATE TABLE IF NOT EXISTS faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    bbox_x INTEGER NOT NULL,
    bbox_y INTEGER NOT NULL,
    bbox_w INTEGER NOT NULL,
    bbox_h INTEGER NOT NULL,
    embedding BLOB,  -- 512 floats serialized
    confidence REAL,
    estimated_age INTEGER,
    estimated_gender TEXT,
    page_number INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User blacklisted files for face detection
CREATE TABLE IF NOT EXISTS face_blacklist (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Face clustering runs and membership (persist clusters across sessions)
CREATE TABLE IF NOT EXISTS face_cluster_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    method TEXT DEFAULT 'auto',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES face_cluster_runs(id) ON DELETE CASCADE,
    method TEXT DEFAULT 'auto',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_cluster_members (
    cluster_id INTEGER NOT NULL REFERENCES face_clusters(id) ON DELETE CASCADE,
    face_id INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, face_id)
);

CREATE TABLE IF NOT EXISTS face_cluster_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    from_cluster_id INTEGER,
    to_cluster_id INTEGER,
    face_ids TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- PDF page extraction tracking (links source PDF to extracted JPEG pages)
CREATE TABLE IF NOT EXISTS pdf_extractions (
    source_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,          -- 0-indexed internally
    extracted_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_file_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_pdf_extractions_source ON pdf_extractions(source_file_id);
CREATE INDEX IF NOT EXISTS idx_pdf_extractions_extracted ON pdf_extractions(extracted_file_id);

-- Per-file AI analysis status (used to avoid reprocessing)
CREATE TABLE IF NOT EXISTS file_ai_status (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    faces_analyzed BOOLEAN DEFAULT FALSE,
    faces_found INTEGER DEFAULT 0,
    faces_error TEXT,
    faces_updated_at TIMESTAMP
);

-- Scene and content analysis
CREATE TABLE IF NOT EXISTS scene_analysis (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    categories TEXT,  -- JSON: {"beach": 0.9, "outdoor": 0.8}
    objects TEXT,     -- JSON: ["dog", "ball", "grass"]
    quality_score REAL,
    blur_score REAL,
    exposure_score REAL,
    clip_embedding BLOB,  -- For semantic search
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- OCR results for documents and screenshots
CREATE TABLE IF NOT EXISTS ocr_results (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    extracted_text TEXT,
    confidence REAL,
    language TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AI-generated content summaries (rich natural language descriptions)
CREATE TABLE IF NOT EXISTS ai_summaries (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    summary TEXT,               -- "Emma and Dad at beach, golden retriever playing in waves"
    summary_model TEXT,         -- "llava:13b", "gpt-4-vision", "claude-3-opus"
    people_mentioned TEXT,      -- JSON: ["Emma", "Dad"]
    pets_mentioned TEXT,        -- JSON: ["Max", "Whiskers"]
    activities TEXT,            -- JSON: ["playing", "swimming", "building sandcastle"]
    mood_atmosphere TEXT,       -- "joyful", "serene", "celebratory"
    time_of_day TEXT,           -- "sunset", "morning", "night"
    season_weather TEXT,        -- "summer", "sunny", "snowy"
    document_type TEXT,         -- For docs: "invoice", "receipt", "letter", "form"
    document_summary TEXT,      -- For docs: extracted key info summary
    key_entities TEXT,          -- JSON: extracted names, dates, amounts, etc.
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_edited BOOLEAN DEFAULT FALSE
);

-- Searchable tags (AI-generated and user-defined)
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT,              -- 'person', 'place', 'activity', 'object', 'event', 'custom'
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- File-tag associations
CREATE TABLE IF NOT EXISTS file_tags (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    confidence REAL,            -- AI confidence (0.0-1.0) or 1.0 for user tags
    source TEXT,                -- 'ai', 'user', 'exif'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, tag_id)
);

-- Pets (for pet recognition/tracking)
CREATE TABLE IF NOT EXISTS pets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    species TEXT,                -- 'dog', 'cat', 'bird', etc.
    breed TEXT,                  -- Detected or user-specified breed
    birth_year INTEGER,          -- Approximate birth year
    color_pattern TEXT,          -- Description of markings/colors
    notes TEXT,
    is_favorite BOOLEAN DEFAULT FALSE,
    reference_photo_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    photo_count INTEGER DEFAULT 0
);

-- Detected pets in images
CREATE TABLE IF NOT EXISTS pet_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    pet_id INTEGER REFERENCES pets(id) ON DELETE SET NULL,
    species TEXT NOT NULL,       -- 'dog', 'cat', etc.
    breed TEXT,                  -- Detected breed (if available)
    bbox_x INTEGER NOT NULL,
    bbox_y INTEGER NOT NULL,
    bbox_w INTEGER NOT NULL,
    bbox_h INTEGER NOT NULL,
    embedding BLOB,              -- Visual embedding for matching
    confidence REAL,             -- Detection confidence
    color_histogram BLOB,        -- Color analysis for matching
    estimated_age_stage TEXT,    -- 'puppy', 'young', 'adult', 'senior'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pets_name ON pets(name);
CREATE INDEX IF NOT EXISTS idx_pets_species ON pets(species);
CREATE INDEX IF NOT EXISTS idx_pet_detections_file ON pet_detections(file_id);
CREATE INDEX IF NOT EXISTS idx_pet_detections_pet ON pet_detections(pet_id);

-- Video frame hashes (for near-duplicate video detection)
CREATE TABLE IF NOT EXISTS video_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    frame_index INTEGER NOT NULL,
    timestamp_sec REAL NOT NULL,
    phash TEXT,
    dhash TEXT,
    UNIQUE(file_id, frame_index)
);

CREATE INDEX IF NOT EXISTS idx_video_frames_file ON video_frames(file_id);

-- Action audit log (all file operations)
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    action_type TEXT NOT NULL,  -- 'delete', 'quarantine', 'trash', 'link', 'copy', 'move', 'restore'
    source_path TEXT NOT NULL,
    dest_path TEXT,
    file_hash TEXT,
    file_size INTEGER,
    reversible BOOLEAN DEFAULT TRUE,
    reversed BOOLEAN DEFAULT FALSE,
    metadata TEXT  -- JSON for additional context
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_files_drive ON files(drive_id);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_files_quick_hash ON files(quick_hash);
CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);
CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type);
CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified);
CREATE INDEX IF NOT EXISTS idx_files_perceptual ON files(perceptual_hash);

CREATE INDEX IF NOT EXISTS idx_metadata_date ON file_metadata(exif_date);
CREATE INDEX IF NOT EXISTS idx_metadata_location ON file_metadata(location_name);

CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_faces_file ON faces(file_id);

CREATE INDEX IF NOT EXISTS idx_duplicate_members_file ON duplicate_members(file_id);
CREATE INDEX IF NOT EXISTS idx_duplicate_groups_status ON duplicate_groups(status);

CREATE INDEX IF NOT EXISTS idx_action_log_type ON action_log(action_type);
CREATE INDEX IF NOT EXISTS idx_action_log_timestamp ON action_log(timestamp);

CREATE INDEX IF NOT EXISTS idx_ai_summaries_model ON ai_summaries(summary_model);
CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_file_tags_source ON file_tags(source);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);

-- Full-text search for summaries and tags
CREATE VIRTUAL TABLE IF NOT EXISTS ai_summaries_fts USING fts5(
    summary,
    people_mentioned,
    pets_mentioned,
    activities,
    document_summary,
    key_entities,
    content='ai_summaries',
    content_rowid='file_id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(
    extracted_text,
    content='ocr_results',
    content_rowid='file_id'
);

-- Triggers to keep FTS tables in sync
CREATE TRIGGER IF NOT EXISTS ai_summaries_ai AFTER INSERT ON ai_summaries BEGIN
    INSERT INTO ai_summaries_fts(rowid, summary, people_mentioned, pets_mentioned, activities, document_summary, key_entities)
    VALUES (new.file_id, new.summary, new.people_mentioned, new.pets_mentioned, new.activities, new.document_summary, new.key_entities);
END;

CREATE TRIGGER IF NOT EXISTS ai_summaries_ad AFTER DELETE ON ai_summaries BEGIN
    INSERT INTO ai_summaries_fts(ai_summaries_fts, rowid, summary, people_mentioned, pets_mentioned, activities, document_summary, key_entities)
    VALUES ('delete', old.file_id, old.summary, old.people_mentioned, old.pets_mentioned, old.activities, old.document_summary, old.key_entities);
END;

CREATE TRIGGER IF NOT EXISTS ai_summaries_au AFTER UPDATE ON ai_summaries BEGIN
    INSERT INTO ai_summaries_fts(ai_summaries_fts, rowid, summary, people_mentioned, pets_mentioned, activities, document_summary, key_entities)
    VALUES ('delete', old.file_id, old.summary, old.people_mentioned, old.pets_mentioned, old.activities, old.document_summary, old.key_entities);
    INSERT INTO ai_summaries_fts(rowid, summary, people_mentioned, pets_mentioned, activities, document_summary, key_entities)
    VALUES (new.file_id, new.summary, new.people_mentioned, new.pets_mentioned, new.activities, new.document_summary, new.key_entities);
END;

CREATE TRIGGER IF NOT EXISTS ocr_ai AFTER INSERT ON ocr_results BEGIN
    INSERT INTO ocr_fts(rowid, extracted_text) VALUES (new.file_id, new.extracted_text);
END;

CREATE TRIGGER IF NOT EXISTS ocr_ad AFTER DELETE ON ocr_results BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, extracted_text) VALUES ('delete', old.file_id, old.extracted_text);
END;

CREATE TRIGGER IF NOT EXISTS ocr_au AFTER UPDATE ON ocr_results BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, extracted_text) VALUES ('delete', old.file_id, old.extracted_text);
    INSERT INTO ocr_fts(rowid, extracted_text) VALUES (new.file_id, new.extracted_text);
END;

-- Celebrity identification matches (links faces to celebrity identification results)
CREATE TABLE IF NOT EXISTS celebrity_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,             -- 'rekognition', 'local_db'
    celebrity_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    external_id TEXT,                   -- Provider-specific ID
    external_urls TEXT,                 -- JSON: [{"label":"IMDB","url":"..."}]
    known_for TEXT,                     -- Short description from API
    status TEXT DEFAULT 'pending',      -- 'pending', 'confirmed', 'rejected'
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(face_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_celebrity_matches_face ON celebrity_matches(face_id);
CREATE INDEX IF NOT EXISTS idx_celebrity_matches_status ON celebrity_matches(status);
CREATE INDEX IF NOT EXISTS idx_celebrity_matches_name ON celebrity_matches(celebrity_name);

-- Insert initial schema version
INSERT OR IGNORE INTO schema_version (version) VALUES (2);
