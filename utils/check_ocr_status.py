#!/usr/bin/env python3
import os
from pathlib import Path

input_dir = Path("input")
output_dir = Path("ocr-output")

pdf_files = list(input_dir.glob("*.pdf"))
print(f"Total PDFs: {len(pdf_files)}")

missing = []
empty = []
has_content = []

for pdf in pdf_files:
    md_path = output_dir / f"{pdf.stem}.md"
    if not md_path.exists():
        missing.append(pdf.name)
    elif md_path.stat().st_size < 100:
        empty.append(pdf.name)
    else:
        has_content.append(pdf.name)

print(f"\nMissing MD files ({len(missing)}):")
for name in sorted(missing):
    print(f"  {name}")

print(f"\nEmpty/small MD files ({len(empty)}):")
for name in sorted(empty):
    print(f"  {name}")

print(f"\nHas content ({len(has_content)}):")
for name in sorted(has_content):
    print(f"  {name}")

# Write list of PDFs that need reprocessing (missing or empty)
need_process = missing + empty
if need_process:
    print(f"\nPDFs needing OCR processing ({len(need_process)}):")
    for name in sorted(need_process):
        print(f"  {name}")