# File Hashing

## What It Does

After scanning discovers your files, the Hasher computes a unique "fingerprint" for each file's contents. Two files with identical contents will always have identical hashes, regardless of their names or locations. This is how the app finds exact duplicates with 100% accuracy.

## How It Works

### The Fingerprinting Process

When you have 100,000 files, comparing every file to every other file would take forever. Instead, the app uses a smart approach:

1. **Group by size** - Files with different sizes can't be duplicates, so we only compare files of the same size
2. **Quick hash** - For files that might be duplicates (same size), compute a fast partial hash
3. **Full hash** - Only files with matching quick hashes get fully hashed

This means if you have 100,000 files but only 5,000 share sizes with other files, only those 5,000 get hashed at all. And of those, maybe only 500 have matching quick hashes that need full verification.

### What You'll See

During the hashing phase:

```
Hashing: Processing potential duplicates

Files to hash: 5,234 (of 127,453 total)
Completed: 2,891
Current: \\NAS\Photos\2019\IMG_4521.jpg

Speed: 145 files/sec
Elapsed: 18s

[==================>                     ] 55%

[Pause]  [Cancel]
```

The "Files to hash" number is much smaller than your total files because most files have unique sizes and don't need hashing.

## Hash Types Used

### xxHash (Quick Hash)

The app first uses xxHash, an extremely fast hashing algorithm:
- Reads only the first 64KB and last 64KB of each file
- Runs at several GB/second on modern hardware
- Used to quickly eliminate non-duplicates

Two files with different quick hashes definitely aren't duplicates. But files with matching quick hashes might just coincidentally have similar beginnings and endings - they need full verification.

### SHA-256 (Full Hash)

For files that pass the quick hash check, the app computes a full SHA-256 hash:
- Reads the entire file content
- Cryptographically secure - virtually impossible for different files to match
- Industry standard used for file verification worldwide

When two files have matching SHA-256 hashes, they are identical with certainty (the odds of a false match are 1 in 2^256, effectively zero).

## Performance

### Speed Expectations

Hashing speed depends on your storage:

| Storage Type | Typical Speed |
|--------------|---------------|
| NVMe SSD | 2,000-3,000 MB/s |
| SATA SSD | 400-550 MB/s |
| Hard Drive | 100-200 MB/s |
| NAS (Gigabit) | 100-125 MB/s |
| NAS (WiFi) | 20-50 MB/s |

For a NAS with 100GB of files to hash over Gigabit Ethernet, expect roughly 15-20 minutes.

### Why Network Drives Are Slower

When hashing files on your NAS, every byte must travel over the network. This is unavoidable - the app needs to read file contents to compute hashes. Tips:

- **Use wired Ethernet** - Gigabit wired is 10-20x faster than WiFi
- **Hash during off-hours** - Other network traffic slows things down
- **Be patient on first run** - After initial hashing, only new/changed files need processing

### Memory Usage

The app reads files in small chunks (1MB at a time) rather than loading entire files into memory. Even when hashing a 50GB video file, memory usage stays low.

## Hash Caching

### Your Hashes Are Saved

Once a file is hashed, the result is stored in the database. The app never re-hashes a file unless:
- The file's modification date changed
- You specifically run a Deep Scan
- The file was deleted and recreated

This means the second time you scan, hashing is nearly instant for unchanged files.

### Verifying Cached Hashes

If you're paranoid (or recovering from backup), use Deep Scan to re-hash everything. This verifies that cached hashes still match actual file contents.

## Handling Large Files

### Videos and Archives

Large files (videos, archives, disk images) can be several gigabytes. The app handles these efficiently:

- **Streaming reads** - Never loads entire file into memory
- **Progress within file** - For files over 100MB, shows progress within the current file
- **Interruptible** - Can pause mid-file and resume later

### Very Large Files Warning

Files over 10GB take significant time to hash. If you have many large video files, consider:
- Running the scan overnight
- Using the pause feature to take breaks
- Focusing on specific folders rather than entire drives

## Technical Details

### Hash Storage

Hashes are stored as hexadecimal strings in the database:
- Quick hash: 16 characters (64-bit xxHash)
- Full hash: 64 characters (256-bit SHA-256)

### Collision Handling

A "collision" is when two different files produce the same hash.

For quick hashes (xxHash), collisions are expected and handled - that's why we verify with SHA-256.

For SHA-256, collisions are theoretically possible but practically impossible. No SHA-256 collision has ever been found in real-world use. The app trusts matching SHA-256 hashes as proof of identical content.

### Partial Hash Strategy

The quick hash reads:
- First 64KB of file
- Last 64KB of file
- File size is also considered

This catches most differences while being extremely fast. Files that differ only in the middle (rare) will have matching quick hashes but different full hashes, so they're still correctly identified as different.

### Library: xxhash

The app uses the `xxhash` Python library for quick hashing:
- Written in C for maximum speed
- Consistent results across platforms
- Widely used and well-tested

### Library: hashlib (SHA-256)

Full hashing uses Python's built-in `hashlib`:
- Part of the Python standard library
- Hardware-accelerated on modern CPUs
- Matches SHA-256 implementations everywhere

## Troubleshooting

### "Hashing is taking forever"

If hashing seems stuck:
1. Check if it's processing a very large file (shown in current file)
2. Verify network connection if using NAS
3. Check disk health - failing drives are very slow
4. Consider pausing and resuming later

### "Hash mismatch after no changes"

If a file's hash changed but you didn't modify it:
- Another program may have touched it
- Disk corruption is possible - check drive health
- Some apps update files silently (metadata, thumbnails)

### "Not all files were hashed"

The app only hashes files that share sizes with other files. A file with a unique size can't have duplicates, so it's skipped. This is by design and saves significant time.

To see which files were hashed, go to **Duplicates > View All > Filter: Hashed Files**.
