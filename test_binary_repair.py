"""Test custom binary JPEG repair on corrupt files."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from duplicleaner.utils.jpeg_binary_repair import JPEGBinaryRepairer


def test_binary_repair():
    """Test binary repair on corrupt FinePix files."""

    # Base directory
    base_dir = r"\\LS210D11E\share\Pictures\Saved Pictures\Camera\Tacoma house Pics"

    # Test files
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

    # Output directory
    output_dir = Path.home() / "Documents" / "Recovered_JPEGs_Binary"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Custom Binary JPEG Repair Test")
    print("=" * 70)
    print(f"\nSource: {base_dir}")
    print(f"Output: {output_dir}")
    print(f"Files: {len(test_files)}")
    print("\n" + "-" * 70)

    repairer = JPEGBinaryRepairer()

    recovered = []
    failed = []
    not_found = []

    for i, filename in enumerate(test_files, 1):
        input_path = os.path.join(base_dir, filename)
        output_path = output_dir / filename

        print(f"\n[{i}/{len(test_files)}] {filename}")

        # Check exists
        if not os.path.exists(input_path):
            print(f"  ⊘ File not found")
            not_found.append(filename)
            continue

        # Get file size
        file_size = os.path.getsize(input_path)
        print(f"  📁 Size: {file_size:,} bytes")

        # Try standard repair first
        print(f"  🔧 Attempting binary repair...")
        success = repairer.repair_jpeg(input_path, str(output_path))

        if not success:
            # Try aggressive repair
            print(f"  ⚡ Trying aggressive repair...")
            clean_data = repairer.attempt_aggressive_repair(input_path)

            if clean_data:
                try:
                    with open(output_path, 'wb') as f:
                        f.write(clean_data)
                    print(f"  ✓ Aggressive repair succeeded ({len(clean_data):,} bytes)")
                    recovered.append((filename, "aggressive", len(clean_data)))
                except Exception as e:
                    print(f"  ✗ Failed to save: {e}")
                    failed.append((filename, str(e)))
            else:
                print(f"  ✗ All repair attempts failed")
                failed.append((filename, "no_jpeg_structure"))
        else:
            output_size = os.path.getsize(output_path)
            print(f"  ✓ Repaired ({output_size:,} bytes)")
            recovered.append((filename, "standard", output_size))

    # Summary
    print("\n" + "=" * 70)
    print("Repair Summary")
    print("=" * 70)
    print(f"\nTotal: {len(test_files)}")
    print(f"  ✓ Recovered: {len(recovered)}")
    print(f"  ✗ Failed: {len(failed)}")
    print(f"  ⊘ Not found: {len(not_found)}")

    if recovered:
        print(f"\n✓ Recovered files ({len(recovered)}):")
        for filename, method, size in recovered:
            print(f"  • {filename}")
            print(f"    Method: {method}, Size: {size:,} bytes")

    if failed:
        print(f"\n✗ Failed files ({len(failed)}):")
        for filename, error in failed:
            print(f"  • {filename}: {error}")

    print("\n" + "=" * 70)
    print("Next Steps")
    print("=" * 70)

    if recovered:
        print(f"\n1. Open File Explorer:")
        print(f"   {output_dir}")
        print(f"\n2. Try opening the recovered JPEGs")
        print(f"   - Open with Photos, Paint, web browser, etc.")
        print(f"   - Even partial recovery is useful!")
        print(f"\n3. If they work, run on all corrupt files:")
        print(f"   python -m duplicleaner recover --directory \"{base_dir}\"")
    else:
        print(f"\nNo files could be recovered with binary repair.")
        print(f"These files may have:")
        print(f"  • Complete header corruption")
        print(f"  • Random/encrypted data")
        print(f"  • Physical media damage beyond recovery")

    return len(recovered) > 0


if __name__ == "__main__":
    try:
        success = test_binary_repair()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
