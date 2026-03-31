#!/usr/bin/env python3
"""
Migration script to add validation columns to extracted_data table.
Run this before using the validation dashboard.
"""
import sqlite3
import sys
from pathlib import Path

def add_validation_columns(db_path="notary_processing.db"):
    """Add validation columns to extracted_data table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(extracted_data)")
    columns = [col[1] for col in cursor.fetchall()]
    
    added = []
    
    if 'validated' not in columns:
        cursor.execute("ALTER TABLE extracted_data ADD COLUMN validated INTEGER DEFAULT 0")
        added.append('validated')
    
    if 'validated_at' not in columns:
        cursor.execute("ALTER TABLE extracted_data ADD COLUMN validated_at TIMESTAMP")
        added.append('validated_at')
    
    if 'validated_by' not in columns:
        cursor.execute("ALTER TABLE extracted_data ADD COLUMN validated_by TEXT")
        added.append('validated_by')
    
    if 'correction_notes' not in columns:
        cursor.execute("ALTER TABLE extracted_data ADD COLUMN correction_notes TEXT")
        added.append('correction_notes')
    
    conn.commit()
    conn.close()
    
    if added:
        print(f"Added columns: {', '.join(added)}")
    else:
        print("All validation columns already exist.")
    
    return added

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "notary_processing.db"
    add_validation_columns(db_path)