"""Test JPEG recovery on specific corrupt FinePix files.

Tests recovery and saves to a local folder for easy viewing in File Explorer.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from duplicleaner.utils.jpeg_recovery import JPEGRecovery


def test_specific_files():
    """Test recovery on specific files."""

    # Base directory
    base_dir = r"\\LS210D11E\share\Pictures\Saved Pictures\Camera\Tacoma house Pics"

    # Specific files to test
    test_files = [
        "FinePix F4507378.JPG",
        "FinePix F4507475.JPG",
        "FinePix F4507533.JPG",
        "FinePix F4507546.JPG",
        "FinePix F4507547.JPG",
        "FinePix F4507548.JPG",
        "FinePix F4507551.JPG",
        "FinePix F4507603.JPG",
        "FinePix F4507605.JPG",
        "FinePix F4507738.JPG",
        "FinePix F4507741.JPG",
    ]

    # Output to Documents folder for easy access
    output_dir = Path.home() / "Documents" / "Recovered_JPEGs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("JPEG Recovery Test - Specific Files")
    print("=" * 70)
    print(f"\nSource: {base_dir}")
    print(f"Output: {output_dir}")
    print(f"Files to test: {len(test_files)}")
    print("\n" + "-" * 70)

    # Create recovery instance
    recovery = JPEGRecovery(
        recovery_dir=str(output_dir),
        preserve_originals=True,  # Don't touch originals
        quality=95,
    )

    recovered = []
    failed = []
    not_found = []

    for i, filename in enumerate(test_files, 1):
        file_path = os.path.join(base_dir, filename)

        print(f"\n[{i}/{len(test_files)}] {filename}")

        # Check if file exists
        if not os.path.exists(file_path):
            print(f"  ⊘ File not found")
            not_found.append(filename)
            continue

        # Check if corrupt
        is_corrupt, corruption_type = recovery.is_corrupt_jpeg(file_path)

        if not is_corrupt:
            print(f"  ℹ File is not corrupt (will copy anyway)")
            # Copy to output for comparison
            import shutil
            shutil.copy2(file_path, output_dir / filename)
            recovered.append((filename, "clean"))
            continue

        print(f"  ⚠ Detected corruption: {corruption_type}")
        print(f"  🔧 Attempting recovery...")

        # Attempt recovery
        result = recovery.recover_jpeg(file_path)

        if result.success:
            print(f"  ✓ Successfully recovered!")
            recovered.append((filename, corruption_type))
        else:
            print(f"  ✗ Recovery failed: {result.error}")
            failed.append((filename, result.error))

    # Print summary
    print("\n" + "=" * 70)
    print("Recovery Summary")
    print("=" * 70)
    print(f"\nTotal files tested: {len(test_files)}")
    print(f"  ✓ Recovered: {len(recovered)}")
    print(f"  ✗ Failed: {len(failed)}")
    print(f"  ⊘ Not found: {len(not_found)}")

    if recovered:
        print(f"\n✓ Recovered files ({len(recovered)}):")
        for filename, corruption in recovered:
            status = f"({corruption})" if corruption != "clean" else "(was clean)"
            print(f"  • {filename} {status}")

    if failed:
        print(f"\n✗ Failed files ({len(failed)}):")
        for filename, error in failed:
            print(f"  • {filename} - {error}")

    if not_found:
        print(f"\n⊘ Not found ({len(not_found)}):")
        for filename in not_found:
            print(f"  • {filename}")

    print("\n" + "=" * 70)
    print("Next Steps")
    print("=" * 70)

    if recovered:
        print(f"\n1. Open File Explorer and navigate to:")
        print(f"   {output_dir}")
        print(f"\n2. Try opening the recovered JPEG files")
        print(f"   - They should display correctly in File Explorer")
        print(f"   - You can also open them in Photos, Paint, etc.")
        print(f"\n3. If they work, you can run full recovery on the directory:")
        print(f'   python -m duplicleaner recover --directory "{base_dir}"')

    if failed:
        print(f"\nFor the {len(failed)} failed files:")
        print(f"  • They may be too severely corrupted")
        print(f"  • Try commercial tools like Stellar Photo Repair")
        print(f"  • Check if you have backups")

    return len(recovered) > 0


if __name__ == "__main__":
    try:
        success = test_specific_files()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
