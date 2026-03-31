#!/usr/bin/env python3
"""
Update database schema file to include validation columns.
"""
import sys

def update_schema_file(schema_file="database_schema.sqlite.sql"):
    with open(schema_file, 'r') as f:
        lines = f.readlines()
    
    # Find start and end of extracted_data CREATE TABLE
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip().startswith('CREATE TABLE IF NOT EXISTS extracted_data'):
            start = i
        if start is not None and line.strip() == ');':
            # Find the closing paren that matches this table definition
            # Look ahead for next CREATE TABLE or end of file
            for j in range(i, len(lines)):
                if lines[j].strip() == ');':
                    end = j
                    break
            break
    
    if start is None or end is None:
        print("Could not find extracted_data table definition.")
        return False
    
    # Build new table definition
    new_lines = []
    for i in range(start, end + 1):
        line = lines[i]
        if line.strip() == 'extraction_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,':
            new_lines.append(line)
            new_lines.append('    validated INTEGER DEFAULT 0,\n')
            new_lines.append('    validated_at TIMESTAMP,\n')
            new_lines.append('    validated_by TEXT,\n')
            new_lines.append('    correction_notes TEXT,\n')
        else:
            new_lines.append(line)
    
    # Replace the block
    lines[start:end+1] = new_lines
    
    with open(schema_file, 'w') as f:
        f.writelines(lines)
    
    print(f"Updated {schema_file}")
    return True

if __name__ == "__main__":
    update_schema_file()