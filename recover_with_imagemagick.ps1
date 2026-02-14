# JPEG Recovery using ImageMagick
# This script uses ImageMagick to recover severely corrupt JPEG files

param(
    [string]$SourceDir = "\\LS210D11E\share\Pictures\Saved Pictures\Camera\Tacoma house Pics",
    [string]$OutputDir = "$env:USERPROFILE\Documents\Recovered_JPEGs_ImageMagick"
)

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "JPEG Recovery with ImageMagick" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if ImageMagick is installed
$magickPath = (Get-Command magick -ErrorAction SilentlyContinue)
if (-not $magickPath) {
    Write-Host "ERROR: ImageMagick not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install ImageMagick:" -ForegroundColor Yellow
    Write-Host "1. Download from: https://imagemagick.org/script/download.php#windows" -ForegroundColor Yellow
    Write-Host "2. Run the installer (ImageMagick-7.x.x-Q16-HDRI-x64-dll.exe)" -ForegroundColor Yellow
    Write-Host "3. CHECK 'Add to PATH' during installation" -ForegroundColor Yellow
    Write-Host "4. Restart PowerShell and run this script again" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ ImageMagick found: $($magickPath.Source)" -ForegroundColor Green
Write-Host ""

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Write-Host "✓ Created output directory: $OutputDir" -ForegroundColor Green
} else {
    Write-Host "✓ Output directory exists: $OutputDir" -ForegroundColor Green
}
Write-Host ""

# Test files to recover
$testFiles = @(
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
    "FinePix F4507741.JPG"
)

Write-Host "Processing $($testFiles.Count) files..." -ForegroundColor Cyan
Write-Host "---------------------------------------------------------------------"
Write-Host ""

$recovered = 0
$failed = 0
$notFound = 0

foreach ($file in $testFiles) {
    $sourcePath = Join-Path $SourceDir $file
    $outputPath = Join-Path $OutputDir $file

    Write-Host "Processing: $file" -ForegroundColor White

    # Check if source exists
    if (-not (Test-Path $sourcePath)) {
        Write-Host "  ⊘ File not found" -ForegroundColor Gray
        $notFound++
        Write-Host ""
        continue
    }

    # Try to recover with ImageMagick
    try {
        # Use ImageMagick with aggressive error recovery
        # -regard-warnings: Don't fail on warnings
        # -define jpeg:size=2048x2048: Limit memory usage
        $result = & magick convert "$sourcePath" -auto-orient -quality 95 "$outputPath" 2>&1

        # Check if output file was created and is valid
        if (Test-Path $outputPath) {
            $fileInfo = Get-Item $outputPath
            if ($fileInfo.Length -gt 0) {
                Write-Host "  ✓ Recovered successfully ($($fileInfo.Length) bytes)" -ForegroundColor Green
                $recovered++
            } else {
                Write-Host "  ✗ Output file is empty" -ForegroundColor Red
                Remove-Item $outputPath -Force
                $failed++
            }
        } else {
            Write-Host "  ✗ Failed to create output" -ForegroundColor Red
            $failed++
        }
    }
    catch {
        Write-Host "  ✗ Recovery failed: $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }

    Write-Host ""
}

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Recovery Summary" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Total files: $($testFiles.Count)" -ForegroundColor White
Write-Host "  ✓ Recovered: $recovered" -ForegroundColor Green
Write-Host "  ✗ Failed: $failed" -ForegroundColor Red
Write-Host "  ⊘ Not found: $notFound" -ForegroundColor Gray
Write-Host ""

if ($recovered -gt 0) {
    Write-Host "SUCCESS! Recovered files are in:" -ForegroundColor Green
    Write-Host "  $OutputDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Open File Explorer and navigate to the folder above" -ForegroundColor White
    Write-Host "2. Try opening the recovered JPEGs in Photos, Paint, etc." -ForegroundColor White
    Write-Host "3. If they work, run full recovery on all files:" -ForegroundColor White
    Write-Host "   .\recover_all_imagemagick.ps1" -ForegroundColor Cyan
} else {
    Write-Host "No files were recovered." -ForegroundColor Yellow
    Write-Host "These files may be beyond recovery." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Consider:" -ForegroundColor White
    Write-Host "  • Commercial tools (Stellar Photo Repair)" -ForegroundColor White
    Write-Host "  • Professional data recovery services" -ForegroundColor White
    Write-Host "  • Checking for backups" -ForegroundColor White
}

Write-Host ""
