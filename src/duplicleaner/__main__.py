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

    # Set up logging
    import logging
    from duplicleaner.utils.logging import setup_logging

    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)

    # Handle subcommands (CLI mode)
    if args.command:
        return run_cli_command(args)

    # GUI mode
    from duplicleaner.app import run_app
    run_app()
    return 0


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
        # TODO: Implement CLI organize command
        print(f"Organize command not yet implemented")
        print(f"  Source: {args.source}")
        print(f"  Destination: {args.dest}")
        print(f"  By date: {args.by_date}")
        print(f"  By location: {args.by_location}")
        print(f"  Format: {args.format}")
        print(f"  Dry run: {args.dry_run}")
        return 0

    elif args.command == "analyze":
        logger.info("Running AI analysis")
        # TODO: Implement CLI analyze command
        print("Analyze command not yet implemented")
        return 0

    elif args.command == "faces":
        if args.faces_command == "train":
            logger.info(f"Training face recognition from {args.input}")
            # TODO: Implement CLI faces train command
            print(f"Faces train command not yet implemented")
            return 0
        else:
            print("No faces subcommand specified")
            return 1

    elif args.command == "search":
        logger.info(f"Searching for: {args.query}")
        # TODO: Implement CLI search command
        print(f"Search command not yet implemented")
        print(f"  Query: {args.query}")
        print(f"  Limit: {args.limit}")
        return 0

    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
