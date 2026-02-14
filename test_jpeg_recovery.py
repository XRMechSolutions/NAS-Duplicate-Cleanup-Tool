"""Test JPEG recovery on actual corrupt files from NAS.

This script tests the JPEG recovery feature on the corrupt FinePix images
found in the Tacoma house Pics folder.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from duplicleaner.utils.jpeg_recovery import JPEGRecovery


def test_recovery():
    """Test recovery on the corrupt FinePix files."""

    # Path to corrupt files
    source_dir = r"\\LS210D11E\share\Pictures\Saved Pictures\Camera\Tacoma house Pics"

    print("=" * 70)
    print("JPEG Recovery Test")
    print("=" * 70)
    print(f"\nTesting recovery on: {source_dir}")

    if not os.path.exists(source_dir):
        print(f"\nError: Directory not found!")
        print(f"  {source_dir}")
        print("\nPlease update the path in test_jpeg_recovery.py to match your setup.")
        return

    # Create recovery instance
    output_dir = os.path.join(source_dir, "recovered")
    recovery = JPEGRecovery(
        recovery_dir=output_dir,
        preserve_originals=True,  # Keep originals
        quality=95,
    )

    print(f"Output directory: {output_dir}")
    print("\n" + "-" * 70)

    # Test on specific corrupt files mentioned in the logs
    test_files = [
        "FinePix F4509121.JPG",
        "FinePix F4509124.JPG",
        "FinePix F4509234.JPG",
        "FinePix F4509264.JPG",
        "FinePix F4509282.JPG",
        "FinePix F4509298.JPG",
        "FinePix F4509299.JPG",
        "FinePix F4509311.JPG",
        "FinePix F4509312.JPG",
        "FinePix F4509318.JPG",
    ]

    print("\nTesting recovery on 10 known corrupt files...")
    print("-" * 70)

    recovered_count = 0
    failed_count = 0

    for filename in test_files:
        file_path = os.path.join(source_dir, filename)

        if not os.path.exists(file_path):
            print(f"⊘ File not found: {filename}")
            continue

        result = recovery.recover_jpeg(file_path)

        if result.success:
            print(f"✓ Recovered: {filename} (type: {result.corruption_type})")
            recovered_count += 1
        else:
            print(f"✗ Failed: {filename} - {result.error}")
            failed_count += 1

    print("\n" + "=" * 70)
    print("Test Results")
    print("=" * 70)
    print(f"Recovered: {recovered_count}/{len(test_files)}")
    print(f"Failed: {failed_count}/{len(test_files)}")

    if recovered_count > 0:
        print(f"\n✓ Success! Recovered files are in:")
        print(f"  {output_dir}")
        print("\nNext steps:")
        print("  1. Check recovered images in the output folder")
        print("  2. Run full directory recovery with:")
        print(f"     python -m duplicleaner recover --directory \"{source_dir}\"")
        print("  3. Run face analysis on recovered files")
    else:
        print("\n⚠ No files could be recovered.")
        print("These files may be too severely corrupted.")

    return recovered_count > 0


if __name__ == "__main__":
    try:
        success = test_recovery()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
