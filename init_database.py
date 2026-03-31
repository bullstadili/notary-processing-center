#!/usr/bin/env python3
"""
Database Initialization Script for Notary Processing Center.
Creates and initializes the SQLite database, optionally importing existing data.
"""
import argparse
import sys
from pathlib import Path
from database_manager import DatabaseManager, init_database
import json

def import_existing_documents(db_manager: DatabaseManager, input_dir: str = "input", 
                             ocr_output_dir: str = "ocr-output", renamed_dir: str = "renamed"):
    """
    Import existing processed documents into the database.
    Scans input, ocr-output, and renamed directories to reconstruct processing history.
    """
    print("Importing existing documents...")
    
    input_path = Path(input_dir)
    ocr_output_path = Path(ocr_output_dir)
    renamed_path = Path(renamed_dir)
    
    # Get all PDF files in input directory
    pdf_files = list(input_path.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {input_dir}/")
    
    imported_count = 0
    for pdf_file in pdf_files:
        original_filename = pdf_file.name
        print(f"  Processing: {original_filename}")
        
        try:
            # Add document to database
            file_size = pdf_file.stat().st_size
            file_hash = db_manager.calculate_file_hash(str(pdf_file))
            
            # TODO: Get page count from PDF (would need PyPDF2 or similar)
            # For now, we'll estimate or leave as None
            page_count = 0
            
            # Get absolute path
            abs_path = str(pdf_file.resolve())
            
            doc_id = db_manager.add_document(
                original_filename=original_filename,
                file_path=abs_path,
                file_size_bytes=file_size,
                file_hash=file_hash,
                page_count=page_count,
                status='processed'  # Assume already processed
            )
            
            # Check for OCR output
            ocr_md_file = ocr_output_path / f"{pdf_file.stem}.md"
            if ocr_md_file.exists():
                try:
                    with open(ocr_md_file, 'r', encoding='utf-8') as f:
                        ocr_text = f.read()
                    
                    # For now, add as single page OCR result
                    # In reality, we should parse page breaks
                    db_manager.add_ocr_result(
                        document_id=doc_id,
                        page_number=1,
                        ocr_text=ocr_text,
                        ocr_parameters={"source": "import", "method": "existing_file"}
                    )
                    db_manager.add_processing_log(
                        document_id=doc_id,
                        agent_name='ocr',
                        operation='import',
                        log_message=f"OCR imported from existing file: {ocr_md_file.name}"
                    )
                except Exception as e:
                    print(f"    Warning: Failed to import OCR for {original_filename}: {e}")
            
            # Check for extracted data (parse results)
            # We would need to re-parse or read from parse results
            # For now, we'll skip and let parse agent handle it
            
            # Check for renamed file
            renamed_files = list(renamed_path.glob(f"*{pdf_file.stem}*.pdf"))
            if renamed_files:
                renamed_file = renamed_files[0]  # Take first match
                db_manager.add_rename_operation(
                    document_id=doc_id,
                    original_filename=original_filename,
                    new_filename=renamed_file.name,
                    destination_path=str(renamed_file),
                    success=True
                )
                db_manager.add_processing_log(
                    document_id=doc_id,
                    agent_name='rename',
                    operation='import',
                    log_message=f"Rename imported from existing file: {renamed_file.name}"
                )
            
            imported_count += 1
            print(f"    Imported as document ID: {doc_id}")
            
        except Exception as e:
            print(f"    Error importing {original_filename}: {e}")
            db_manager.add_error_log(
                document_id=None,
                agent_name='database',
                error_type='import_error',
                error_message=f"Failed to import {original_filename}: {str(e)}"
            )
    
    print(f"\nSuccessfully imported {imported_count} documents")
    return imported_count

def main():
    parser = argparse.ArgumentParser(description="Initialize Notary Processing Center Database")
    parser.add_argument("--schema", default="database_schema.sqlite.sql",
                       help="Path to SQL schema file")
    parser.add_argument("--database", default="notary_processing.db",
                       help="Path to SQLite database file")
    parser.add_argument("--import-existing", action="store_true",
                       help="Import existing processed documents")
    parser.add_argument("--input-dir", default="input",
                       help="Input directory with PDF files")
    parser.add_argument("--ocr-output-dir", default="ocr-output",
                       help="OCR output directory")
    parser.add_argument("--renamed-dir", default="renamed",
                       help="Renamed files directory")
    parser.add_argument("--backup", action="store_true",
                       help="Create backup before initialization")
    parser.add_argument("--stats", action="store_true",
                       help="Show database statistics after initialization")
    
    args = parser.parse_args()
    
    # Check if database already exists
    db_path = Path(args.database)
    if db_path.exists():
        print(f"Database already exists at {args.database}")
        response = input("Do you want to recreate it? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Aborting.")
            return 1
    
    # Create database manager
    db_manager = DatabaseManager(args.database)
    
    # Backup existing database if requested
    if args.backup and db_path.exists():
        backup_path = f"{args.database}.backup"
        print(f"Creating backup at {backup_path}...")
        if db_manager.backup_database(backup_path):
            print("Backup created successfully")
        else:
            print("Warning: Backup failed")
    
    # Initialize database
    print(f"Initializing database from schema: {args.schema}")
    if not Path(args.schema).exists():
        print(f"Error: Schema file not found: {args.schema}")
        return 1
    
    if db_manager.initialize_database(args.schema):
        print("Database initialized successfully")
    else:
        print("Database initialization failed")
        return 1
    
    # Import existing data if requested
    if args.import_existing:
        import_existing_documents(db_manager, args.input_dir, args.ocr_output_dir, args.renamed_dir)
    
    # Show statistics if requested
    if args.stats:
        stats = db_manager.get_statistics()
        print("\nDatabase Statistics:")
        print(json.dumps(stats, indent=2))
    
    db_manager.close()
    print(f"\nDatabase ready at: {args.database}")
    return 0

if __name__ == "__main__":
    sys.exit(main())