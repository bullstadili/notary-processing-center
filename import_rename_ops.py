#!/usr/bin/env python3
"""
Import missing rename operations from rename_execution.log into database.
"""
import re
import sys
from pathlib import Path
from database_manager import DatabaseManager

def parse_rename_log(log_path):
    """Parse rename_execution.log and return list of (original, new) tuples."""
    mappings = []
    with open(log_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Match lines like "Renamed: original.pdf → new.pdf"
            if line.startswith('Renamed:'):
                # Extract original and new filenames
                match = re.search(r'Renamed:\s+([^→]+)→\s*(.+)', line)
                if match:
                    original = match.group(1).strip()
                    new = match.group(2).strip()
                    mappings.append((original, new))
    return mappings

def main():
    db_manager = DatabaseManager()
    
    # Parse log file
    log_path = Path('rename_execution.log')
    if not log_path.exists():
        print(f"Error: {log_path} not found")
        sys.exit(1)
    
    mappings = parse_rename_log(log_path)
    print(f"Found {len(mappings)} rename mappings in log")
    
    imported = 0
    skipped = 0
    
    for original, new in mappings:
        # Get document ID
        document = db_manager.get_document(original_filename=original)
        if not document:
            print(f"Warning: No database record for {original}")
            continue
        
        doc_id = document['id']
        
        # Check if rename operation already exists for this document
        existing = db_manager.get_rename_history(document_id=doc_id)
        if existing:
            print(f"  Skipping {original} → {new} (already in database)")
            skipped += 1
            continue
        
        # Determine destination path
        dest_path = str(Path('renamed') / new)
        
        # Add rename operation
        rename_id = db_manager.add_rename_operation(
            document_id=doc_id,
            original_filename=original,
            new_filename=new,
            rename_template='',  # Unknown
            destination_path=dest_path,
            success=True,
            error_message=''
        )
        
        if rename_id:
            print(f"  Imported: {original} → {new} (ID: {rename_id})")
            imported += 1
        else:
            print(f"  Failed to import: {original} → {new}")
    
    print(f"\nSummary: Imported {imported}, Skipped {skipped}")
    db_manager.close()

if __name__ == '__main__':
    main()