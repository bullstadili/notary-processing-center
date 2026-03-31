#!/usr/bin/env python3
"""
Reprocess failed/missing OCR files with generous timeout settings.
"""
import subprocess
import sys
from pathlib import Path

def get_files_to_process():
    """Return list of PDFs that need OCR processing (missing or empty output)."""
    input_dir = Path("input")
    output_dir = Path("ocr-output")
    
    pdf_files = list(input_dir.glob("*.pdf"))
    need_process = []
    
    for pdf in pdf_files:
        md_path = output_dir / f"{pdf.stem}.md"
        if not md_path.exists():
            need_process.append(pdf)
        elif md_path.stat().st_size < 100:
            need_process.append(pdf)
    
    return sorted(need_process, key=lambda x: x.name)

def process_pdf(pdf_path, timeout=500, max_retries=5, dpi=150):
    """Process a single PDF using ocr_processor.py."""
    cmd = [
        sys.executable, "ocr_processor.py",
        "--single", str(pdf_path),
        "--timeout", str(timeout),
        "--max-retries", str(max_retries),
        "--dpi", str(dpi),
        "--force"
    ]
    
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * 2)
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"ERROR: Processing timed out after {timeout * 2}s")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def main():
    files = get_files_to_process()
    if not files:
        print("No files need reprocessing.")
        return
    
    print(f"Found {len(files)} files needing OCR processing.")
    
    successful = 0
    for i, pdf in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] ", end="")
        if process_pdf(pdf):
            successful += 1
    
    print(f"\n{'='*60}")
    print(f"Processing complete: {successful}/{len(files)} successful")
    print(f"{'='*60}")
    
    # Final status check
    remaining = get_files_to_process()
    if remaining:
        print(f"\nStill need processing ({len(remaining)}):")
        for pdf in remaining:
            print(f"  {pdf.name}")
    else:
        print("\nAll files processed successfully!")

if __name__ == "__main__":
    main()