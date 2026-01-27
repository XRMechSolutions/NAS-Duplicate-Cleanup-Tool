"""DupliCleaner entry point.

Run with: python -m duplicleaner
"""

import sys
import argparse

from duplicleaner import __version__


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="duplicleaner",
        description="NAS duplicate file cleanup and photo organization tool"
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"DupliCleaner {__version__}"
    )

    parser.add_argument(
        "--scan",
        metavar="PATH",
        help="Path to scan on startup"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable startup profiling and timing logs"
    )
    parser.add_argument(
        "--profile-output",
        metavar="PATH",
        help="Write cProfile output to PATH (dir or file)"
    )
    parser.add_argument(
        "--profile-min-ms",
        type=float,
        default=0.0,
        help="Minimum milliseconds for timing logs (default: 0)"
    )

    # Subcommands for CLI operations
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Organize subcommand
    organize_parser = subparsers.add_parser("organize", help="Organize photos")
    organize_parser.add_argument("source", help="Source folder to organize")
    organize_parser.add_argument("--dest", help="Destination folder")
    organize_parser.add_argument("--by-date", action="store_true", help="Organize by date")
    organize_parser.add_argument("--by-location", action="store_true", help="Organize by location")
    organize_parser.add_argument("--detect-events", action="store_true", help="Detect events")
    organize_parser.add_argument("--format", default="YYYY/MM", help="Date format")
    organize_parser.add_argument("--dry-run", action="store_true", help="Preview only")

    # Analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", help="Run AI analysis")
    analyze_parser.add_argument("--faces", action="store_true", help="Detect faces")
    analyze_parser.add_argument("--scenes", action="store_true", help="Classify scenes")
    analyze_parser.add_argument("--all", action="store_true", help="Run all analysis")
    analyze_parser.add_argument("--drive-id", help="Limit to a specific drive ID")
    analyze_parser.add_argument("--metadata", action="store_true", help="Extract file metadata (EXIF)")
    analyze_parser.add_argument("--objects", action="store_true", help="Detect objects (YOLO)")
    analyze_parser.add_argument("--ocr", action="store_true", help="Extract text (OCR/docs)")
    analyze_parser.add_argument("--summaries", action="store_true", help="Generate AI summaries")
    analyze_parser.add_argument("--no-images", action="store_true", help="Skip image analysis")
    analyze_parser.add_argument("--no-docs", action="store_true", help="Skip document analysis")
    analyze_parser.add_argument("--include-data", action="store_true", help="Include data files (csv/json/xml)")
    analyze_parser.add_argument("--reanalyze", action="store_true", help="Re-analyze even if results exist")
    analyze_parser.add_argument("--limit", type=int, default=200, help="Batch size per analysis step")

    # Hash subcommand
    hash_parser = subparsers.add_parser("hash", help="Compute file hashes")
    hash_parser.add_argument("--drive-id", help="Limit to a specific drive ID")
    hash_parser.add_argument("--force", action="store_true", help="Rehash all files")

    # Faces subcommand
    faces_parser = subparsers.add_parser("faces", help="Face recognition commands")
    faces_sub = faces_parser.add_subparsers(dest="faces_command")
    train_parser = faces_sub.add_parser("train", help="Train on labeled faces")
    train_parser.add_argument("--input", required=True, help="Input folder with labeled faces")

    # Search subcommand
    search_parser = subparsers.add_parser("search", help="Search photos by content")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=20, help="Max results")

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Enable profiling before startup work
    profiler_session = None
    if args.profile:
        from duplicleaner.utils.profiling import enable_profiling, start_cpu_profiler
        enable_profiling(min_ms=max(0.0, float(args.profile_min_ms)))
        profiler_session = start_cpu_profiler(args.profile_output)

    # Set up logging
    import logging
    from duplicleaner.utils.logging import setup_logging

    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)

    # Handle subcommands (CLI mode)
    try:
        if args.command:
            return run_cli_command(args)

        # GUI mode
        from duplicleaner.app import run_app
        run_app()
        return 0
    finally:
        if profiler_session:
            from duplicleaner.utils.profiling import stop_cpu_profiler
            stop_cpu_profiler(profiler_session)


def run_cli_command(args: argparse.Namespace) -> int:
    """Run a CLI subcommand.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code
    """
    from duplicleaner.utils.logging import get_logger
    logger = get_logger(__name__)

    if args.command == "organize":
        logger.info(f"Organizing photos from {args.source}")
        from duplicleaner.core.organizer import Organizer, OrganizeSettings, DateFormat

        settings = OrganizeSettings()
        settings.include_location = bool(args.by_location)
        settings.event_clustering = bool(args.detect_events)
        settings.dry_run = bool(args.dry_run)

        format_map = {
            "YYYY/MM": DateFormat.YYYY_MM,
            "YYYY/MM/DD": DateFormat.YYYY_MM_DD,
            "YYYY/YYYY-MM-DD": DateFormat.YYYY_FULL_DATE,
            "YYYY/MM-Month": DateFormat.YYYY_MM_MONTH,
        }
        settings.date_format = format_map.get(args.format, DateFormat.YYYY_MM_MONTH)

        organizer = Organizer(settings=settings)
        dest = args.dest or args.source
        preview = organizer.preview(args.source, dest)

        print(f"Preview: {preview.total_files} files, {preview.files_to_move} moves, {preview.folders_to_create} folders")
        if args.dry_run:
            print("Dry run complete. No changes applied.")
            return 0

        results = organizer.execute(args.source, dest, preview=preview)
        success = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        print(f"Organize complete. Success: {success}, Failed: {failed}")
        return 0

    elif args.command == "analyze":
        logger.info("Running AI analysis")
        from duplicleaner.db.database import get_database
        from duplicleaner.utils.config import get_config
        from duplicleaner.core.analysis_runner import AnalysisRunner, AnalysisOptions

        config = get_config()
        db = get_database()

        include_metadata = args.metadata or args.all or config.ai.analysis_include_metadata
        include_scenes = args.scenes or args.all or config.ai.analysis_include_scenes
        include_objects = args.objects or args.all or config.ai.analysis_include_objects
        include_ocr = args.ocr or args.all or config.ai.analysis_include_ocr
        include_summaries = args.summaries or args.all or config.ai.analysis_include_summaries

        options = AnalysisOptions(
            include_metadata=include_metadata,
            include_scenes=include_scenes,
            include_objects=include_objects,
            include_ocr=include_ocr,
            include_summaries=include_summaries,
            include_images=not args.no_images and config.ai.analysis_include_images,
            include_documents=not args.no_docs and config.ai.analysis_include_documents,
            include_data_files=args.include_data or config.ai.analysis_include_data_files,
            document_extensions=config.ai.analysis_doc_extensions,
            data_extensions=config.ai.analysis_data_extensions,
            reanalyze_existing=args.reanalyze or config.ai.analysis_reanalyze_existing,
            drive_id=args.drive_id,
            batch_limit=args.limit or config.ai.analysis_batch_limit,
        )

        runner = AnalysisRunner(db)
        stats = runner.run(options)

        face_count = 0
        if args.faces or args.all:
            from duplicleaner.ai.faces import FaceAnalyzer
            analyzer = FaceAnalyzer(db)
            if analyzer.is_available():
                files = db.get_image_files_missing_face_analysis(
                    limit=options.batch_limit,
                    drive_id=options.drive_id,
                )
                for file_record in files:
                    analyzer.analyze_file(file_record)
                    face_count += 1
            else:
                print("Face analysis unavailable (missing dependencies).")

        print(
            f"Analysis complete: metadata {stats.metadata}, scenes {stats.scenes}, "
            f"objects {stats.objects}, OCR {stats.ocr}, summaries {stats.summaries}, "
            f"faces {face_count}"
        )
        return 0

    elif args.command == "faces":
        if args.faces_command == "train":
            logger.info(f"Training face recognition from {args.input}")
            from duplicleaner.db.database import get_database
            from duplicleaner.db.models import Person
            from duplicleaner.ai.faces import FaceAnalyzer
            from pathlib import Path

            db = get_database()
            analyzer = FaceAnalyzer(db)
            if not analyzer.is_available():
                print("Face analysis dependencies not available.")
                return 1

            base = Path(args.input)
            if not base.exists():
                print("Input folder not found.")
                return 1

            persons = {p.name: p for p in db.get_all_persons(named_only=True) if p.name}
            images_processed = 0
            for person_dir in base.iterdir():
                if not person_dir.is_dir():
                    continue
                name = person_dir.name.strip()
                if not name:
                    continue
                person = persons.get(name)
                if not person:
                    person_id = db.add_person(Person(name=name))
                    person = db.get_person(person_id)
                    persons[name] = person
                if not person:
                    continue

                for image_path in person_dir.rglob("*"):
                    if not image_path.is_file():
                        continue
                    file_record = db.get_file_by_path_any(str(image_path))
                    if not file_record:
                        continue
                    faces = analyzer.analyze_file(file_record)
                    for face in faces:
                        db.assign_face_to_person(face.id, person.id)
                    images_processed += 1

            print(f"Faces train complete. Images processed: {images_processed}")
            return 0
        else:
            print("No faces subcommand specified")
            return 1

    elif args.command == "search":
        logger.info(f"Searching for: {args.query}")
        from duplicleaner.db.database import get_database
        from duplicleaner.ai.scenes import SceneClassifier

        db = get_database()
        results = []
        semantic = SceneClassifier(db)
        if semantic.is_available():
            results.extend(semantic.search(args.query, limit=args.limit))

        text_results = db.search_files(args.query, limit=args.limit)
        for file_record, source in text_results:
            results.append((file_record, source))

        print(f"Results: {len(results)}")
        for item in results[:args.limit]:
            if hasattr(item, "file_path"):
                print(f"[semantic] {item.file_path} ({item.similarity:.2f})")
            else:
                file_record, source = item
                print(f"[{source}] {file_record.path}")
        return 0

    elif args.command == "hash":
        logger.info("Hashing files")
        from duplicleaner.db.database import get_database
        from duplicleaner.core.hasher import Hasher

        db = get_database()
        hasher = Hasher(db)
        result = hasher.hash_files(drive_id=args.drive_id, force_rehash=args.force)
        print(
            f"Hashing complete: hashed {result.files_hashed}, skipped {result.files_skipped}, "
            f"quick dupes {result.duplicate_candidates}, exact dupes {result.exact_duplicates}, errors {result.errors}"
        )
        return 0

    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
