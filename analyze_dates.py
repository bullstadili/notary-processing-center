#!/usr/bin/env python3
import sys
from pathlib import Path
from document_parser import parse_markdown_file

def analyze_folder(folder_path):
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Folder not found: {folder}")
        return
    
    md_files = list(folder.glob("*.md"))
    if not md_files:
        print(f"No markdown files in {folder}")
        return
    
    print(f"Analyzing {len(md_files)} files in {folder}")
    print("-" * 60)
    
    stats = {
        'date_found': 0,
        'docno_found': 0,
        'doctype_found': 0,
        'lastname_found': 0,
    }
    
    files_with_date = []
    
    for md_file in md_files:
        info = parse_markdown_file(md_file)
        if info['date_of_notarization'] and info['date_of_notarization'] != 'Not found':
            stats['date_found'] += 1
            files_with_date.append((md_file.name, info['date_of_notarization']))
        if info['document_number'] and info['document_number'] != 'Not found':
            stats['docno_found'] += 1
        if info['document_type'] and info['document_type'] != 'Not found':
            stats['doctype_found'] += 1
        if info['lastname'] and info['lastname'] != 'Not found':
            stats['lastname_found'] += 1
    
    total = len(md_files)
    print(f"Dates found: {stats['date_found']}/{total} ({stats['date_found']/total*100:.1f}%)")
    print(f"Document numbers found: {stats['docno_found']}/{total} ({stats['docno_found']/total*100:.1f}%)")
    print(f"Document types found: {stats['doctype_found']}/{total} ({stats['doctype_found']/total*100:.1f}%)")
    print(f"Lastnames found: {stats['lastname_found']}/{total} ({stats['lastname_found']/total*100:.1f}%)")
    
    if files_with_date:
        print("\nFiles with dates found:")
        for filename, date in files_with_date[:10]:  # Show first 10
            print(f"  {filename}: {date}")
        if len(files_with_date) > 10:
            print(f"  ... and {len(files_with_date) - 10} more")
    else:
        print("\nNo dates found in any files.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        folder = sys.argv[1]
    else:
        folder = "ocr-output"
    analyze_folder(folder)