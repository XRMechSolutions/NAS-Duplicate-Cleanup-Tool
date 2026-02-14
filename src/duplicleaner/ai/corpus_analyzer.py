"""Document corpus analysis for DupliCleaner.

Provides term frequency analysis, named entity recognition, and pattern
detection across collections of scanned documents.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import log
from typing import Any

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Check for spaCy
try:
    import spacy
    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False

# Check for networkx
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

# Common English stop words (subset to avoid NLTK dependency)
STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "must", "need",
    "this", "that", "these", "those", "it", "its", "he", "she", "they",
    "we", "you", "i", "me", "my", "our", "your", "his", "her", "their",
    "not", "no", "nor", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "again", "all", "also", "am",
    "any", "as", "because", "before", "between", "both", "each",
    "few", "get", "got", "here", "him", "how", "into", "more", "most",
    "new", "now", "only", "other", "out", "own", "same", "some", "such",
    "there", "through", "up", "what", "when", "where", "which", "while",
    "who", "whom", "why", "down", "during", "over", "under",
})


@dataclass
class TermFrequency:
    """A term and its frequency/importance metrics."""
    term: str
    count: int
    doc_count: int  # Number of documents containing this term
    tf_idf: float = 0.0


@dataclass
class NGram:
    """A multi-word phrase and its frequency."""
    phrase: str
    count: int
    doc_count: int


@dataclass
class Entity:
    """A named entity extracted from text."""
    text: str
    entity_type: str  # PERSON, ORG, GPE, DATE, MONEY, etc.
    count: int
    source_file_ids: list[int] = field(default_factory=list)


@dataclass
class CoOccurrence:
    """Two entities that frequently appear together."""
    entity_a: str
    entity_b: str
    count: int


@dataclass
class CommunicationEdge:
    """A communication link between two entities."""
    sender: str
    recipient: str
    count: int
    file_ids: list[int] = field(default_factory=list)


@dataclass
class CorpusReport:
    """Complete corpus analysis results."""
    total_documents: int = 0
    total_words: int = 0
    top_terms: list[TermFrequency] = field(default_factory=list)
    top_bigrams: list[NGram] = field(default_factory=list)
    top_trigrams: list[NGram] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    co_occurrences: list[CoOccurrence] = field(default_factory=list)
    communication_edges: list[CommunicationEdge] = field(default_factory=list)


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, removing punctuation."""
    return re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())


def extract_ngrams(tokens: list[str], n: int) -> list[str]:
    """Extract n-grams from token list."""
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


class CorpusAnalyzer:
    """Analyzes a collection of documents for patterns and entities."""

    def __init__(self):
        self._nlp = None  # spaCy model, loaded on demand
        self._custom_stop_words: set[str] = set()

    def add_stop_words(self, words: list[str]) -> None:
        """Add custom stop words to filter."""
        self._custom_stop_words.update(w.lower() for w in words)

    def _get_stop_words(self) -> frozenset[str]:
        """Get combined stop words."""
        if self._custom_stop_words:
            return STOP_WORDS | frozenset(self._custom_stop_words)
        return STOP_WORDS

    def _load_spacy(self) -> bool:
        """Load spaCy model for NER."""
        if self._nlp is not None:
            return True
        if not HAS_SPACY:
            return False
        try:
            self._nlp = spacy.load("en_core_web_sm")
            logger.info("Loaded spaCy model: en_core_web_sm")
            return True
        except OSError:
            logger.warning("spaCy model 'en_core_web_sm' not installed. "
                           "Run: python -m spacy download en_core_web_sm")
            return False

    def analyze_corpus(
        self,
        documents: list[tuple[int, str]],
        include_entities: bool = True,
        top_n: int = 100,
    ) -> CorpusReport:
        """Analyze a collection of documents.

        Args:
            documents: List of (file_id, text_content) tuples
            include_entities: Run NER if spaCy is available
            top_n: Number of top terms/ngrams to return

        Returns:
            CorpusReport with analysis results
        """
        report = CorpusReport(total_documents=len(documents))
        stop_words = self._get_stop_words()

        # Per-document token lists for TF-IDF
        doc_tokens: list[list[str]] = []
        all_term_counts = Counter()
        doc_term_sets: list[set[str]] = []
        bigram_counts = Counter()
        trigram_counts = Counter()
        bigram_doc_counts: dict[str, int] = defaultdict(int)
        trigram_doc_counts: dict[str, int] = defaultdict(int)

        for _file_id, text in documents:
            if not text:
                continue
            tokens = [t for t in tokenize(text) if t not in stop_words]
            doc_tokens.append(tokens)
            report.total_words += len(tokens)

            term_set = set(tokens)
            doc_term_sets.append(term_set)
            all_term_counts.update(tokens)

            # Bigrams and trigrams
            bgs = extract_ngrams(tokens, 2)
            tgs = extract_ngrams(tokens, 3)
            bigram_counts.update(bgs)
            trigram_counts.update(tgs)
            for bg in set(bgs):
                bigram_doc_counts[bg] += 1
            for tg in set(tgs):
                trigram_doc_counts[tg] += 1

        # Compute TF-IDF for top terms
        n_docs = len(doc_tokens)
        if n_docs > 0:
            # Document frequency for each term
            doc_freq: dict[str, int] = defaultdict(int)
            for term_set in doc_term_sets:
                for term in term_set:
                    doc_freq[term] += 1

            # TF-IDF = (term_count / total_words) * log(n_docs / doc_freq)
            tf_idf_scores: list[TermFrequency] = []
            for term, count in all_term_counts.most_common(top_n * 3):
                df = doc_freq.get(term, 1)
                tf = count / report.total_words if report.total_words > 0 else 0
                idf = log(n_docs / df) if df > 0 else 0
                score = tf * idf
                tf_idf_scores.append(TermFrequency(
                    term=term,
                    count=count,
                    doc_count=df,
                    tf_idf=round(score, 6),
                ))

            # Sort by TF-IDF score (interesting terms first)
            tf_idf_scores.sort(key=lambda x: x.tf_idf, reverse=True)
            report.top_terms = tf_idf_scores[:top_n]

        # Top bigrams (filter by minimum count)
        for phrase, count in bigram_counts.most_common(top_n):
            if count >= 2:
                report.top_bigrams.append(NGram(
                    phrase=phrase,
                    count=count,
                    doc_count=bigram_doc_counts.get(phrase, 1),
                ))

        # Top trigrams
        for phrase, count in trigram_counts.most_common(top_n):
            if count >= 2:
                report.top_trigrams.append(NGram(
                    phrase=phrase,
                    count=count,
                    doc_count=trigram_doc_counts.get(phrase, 1),
                ))

        # Named Entity Recognition (if spaCy available)
        if include_entities and self._load_spacy():
            entity_counts: dict[tuple[str, str], list[int]] = defaultdict(list)

            for file_id, text in documents:
                if not text:
                    continue
                # Limit text length for spaCy processing
                doc = self._nlp(text[:50000])
                for ent in doc.ents:
                    key = (ent.text.strip(), ent.label_)
                    entity_counts[key].append(file_id)

            # Build entity list
            for (text, etype), file_ids in sorted(
                entity_counts.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            )[:top_n]:
                report.entities.append(Entity(
                    text=text,
                    entity_type=etype,
                    count=len(file_ids),
                    source_file_ids=list(set(file_ids))[:20],
                ))

            # Co-occurrence (entities in the same document)
            cooc_counts: Counter = Counter()
            for file_id, text in documents:
                if not text:
                    continue
                doc = self._nlp(text[:50000])
                doc_entities = list({ent.text.strip() for ent in doc.ents if len(ent.text.strip()) > 1})
                for i in range(len(doc_entities)):
                    for j in range(i + 1, len(doc_entities)):
                        pair = tuple(sorted([doc_entities[i], doc_entities[j]]))
                        cooc_counts[pair] += 1

            for (a, b), count in cooc_counts.most_common(top_n):
                if count >= 2:
                    report.co_occurrences.append(CoOccurrence(
                        entity_a=a,
                        entity_b=b,
                        count=count,
                    ))

        logger.info(
            "Corpus analysis: %d docs, %d words, %d terms, %d entities",
            report.total_documents, report.total_words,
            len(report.top_terms), len(report.entities),
        )
        return report

    def build_communication_network(
        self,
        documents: list[tuple[int, str]],
    ) -> list[CommunicationEdge]:
        """Extract sender/recipient relationships from email-like documents.

        Looks for From:/To:/Cc: patterns in document text.

        Args:
            documents: List of (file_id, text_content) tuples

        Returns:
            List of communication edges
        """
        edge_counts: dict[tuple[str, str], list[int]] = defaultdict(list)
        from_pattern = re.compile(r"(?:From|Sent by)[:\s]+([^\n<]+?)(?:\n|<)", re.IGNORECASE)
        to_pattern = re.compile(r"(?:To|Sent to|Recipient)[:\s]+([^\n<]+?)(?:\n|<)", re.IGNORECASE)

        for file_id, text in documents:
            if not text:
                continue
            froms = from_pattern.findall(text[:5000])
            tos = to_pattern.findall(text[:5000])

            for sender in froms:
                sender = sender.strip()
                if not sender or len(sender) > 100:
                    continue
                for recipient in tos:
                    recipient = recipient.strip()
                    if not recipient or len(recipient) > 100:
                        continue
                    if sender != recipient:
                        edge_counts[(sender, recipient)].append(file_id)

        edges = []
        for (sender, recipient), file_ids in sorted(
            edge_counts.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            edges.append(CommunicationEdge(
                sender=sender,
                recipient=recipient,
                count=len(file_ids),
                file_ids=list(set(file_ids))[:20],
            ))

        logger.info("Communication network: %d edges from %d documents",
                     len(edges), len(documents))
        return edges

    def detect_patterns(
        self,
        documents: list[tuple[int, str]],
        min_tf_idf: float = 0.001,
    ) -> list[TermFrequency]:
        """Detect unusual terms that stand out from normal language.

        Returns terms with high TF-IDF scores that appear across multiple
        documents, potentially indicating repeated unusual phrases or
        code words.

        Args:
            documents: List of (file_id, text_content) tuples
            min_tf_idf: Minimum TF-IDF score to consider

        Returns:
            List of unusual terms sorted by TF-IDF
        """
        report = self.analyze_corpus(documents, include_entities=False, top_n=200)
        return [t for t in report.top_terms if t.tf_idf >= min_tf_idf and t.doc_count >= 2]


def gather_corpus_documents(db: "Database", folder_path: str | None = None) -> list[tuple[int, str]]:
    """Gather documents with OCR text or summaries from the database.

    Args:
        db: Database instance
        folder_path: Optional folder path filter

    Returns:
        List of (file_id, text_content) tuples
    """
    documents = []

    with db.connection() as conn:
        if folder_path:
            # Get files in the specified folder
            rows = conn.execute(
                """SELECT f.id, COALESCE(o.extracted_text, '') || ' ' || COALESCE(s.summary, '') || ' ' || COALESCE(s.document_summary, '') as text
                   FROM files f
                   LEFT JOIN ocr_results o ON f.id = o.file_id
                   LEFT JOIN ai_summaries s ON f.id = s.file_id
                   WHERE f.is_deleted = FALSE AND f.path LIKE ?
                     AND (o.extracted_text IS NOT NULL OR s.summary IS NOT NULL OR s.document_summary IS NOT NULL)""",
                (folder_path.rstrip("/\\") + "%",),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT f.id, COALESCE(o.extracted_text, '') || ' ' || COALESCE(s.summary, '') || ' ' || COALESCE(s.document_summary, '') as text
                   FROM files f
                   LEFT JOIN ocr_results o ON f.id = o.file_id
                   LEFT JOIN ai_summaries s ON f.id = s.file_id
                   WHERE f.is_deleted = FALSE
                     AND (o.extracted_text IS NOT NULL OR s.summary IS NOT NULL OR s.document_summary IS NOT NULL)""",
            ).fetchall()

        for row in rows:
            text = row["text"].strip() if row["text"] else ""
            if text:
                documents.append((row["id"], text))

    logger.info("Gathered %d documents for corpus analysis", len(documents))
    return documents
