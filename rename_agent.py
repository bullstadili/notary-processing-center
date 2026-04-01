#!/usr/bin/env python3
"""
Rename Agent: Rename PDF files based on OCR-extracted information.
Renames files from input/ to renamed/ directory using ISO standard date format.
"""
import argparse
import re
import shutil
import sys
import time
from pathlib import Path

# Import parsing functions from document_parser
from document_parser import parse_markdown_file

# Database integration
try:
    from database_manager import DatabaseManager  # type: ignore
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("Warning: database_manager module not found. Database logging disabled.")

def get_extracted_info(md_path, db_manager=None, doc_id=None):
    """
    Get extracted information, preferring validated database entries.
    Returns dict with same keys as parse_markdown_file plus is_waiver, is_corporate.
    """
    # Try to get validated data from database first
    if db_manager and doc_id:
        try:
            extracted = db_manager.get_extracted_data(doc_id)
            if extracted and any(extracted.get(field) for field in ['date_of_notarization', 'document_number', 'document_type', 'lastname']):
                # Convert database fields to info dict
                info = {
                    'filename': md_path.name,
                    'date_of_notarization': extracted.get('date_of_notarization'),
                    'document_number': extracted.get('document_number'),
                    'document_type': extracted.get('document_type'),
                    'page_number': extracted.get('page_number'),
                    'book_number': extracted.get('book_number'),
                    'series_year': extracted.get('series_year'),
                    'lastname': extracted.get('lastname'),
                    'is_waiver': bool(extracted.get('is_waiver', 0)),
                    'is_corporate': bool(extracted.get('is_corporate', 0)),
                }
                # Ensure we have at least some data
                if any(v for v in info.values() if v not in (None, '')):
                    return info
        except Exception as e:
            print(f"  Warning: Failed to get validated data: {e}")
    
    # Fall back to parsing markdown file
    return parse_markdown_file(md_path)

def convert_to_iso_date(date_str):
    """
    Convert extracted date string to ISO format (YYYY-MM-DD).
    
    Handles formats like:
    - "02 FEB 2026" -> "2026-02-02"
    - "FEB 02 2026" -> "2026-02-02"
    - "Feb. 02, 2024" -> "2024-02-02"
    - "12 FEB 2026" -> "2026-02-12"
    - "FEB 12 2026" -> "2026-02-12"
    
    Returns None if conversion fails.
    """
    if not date_str or date_str == "Not found":
        return None
    
    # Clean up the date string
    date_str = date_str.strip()
    
    # Define month mappings
    month_map = {
        'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
        'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
        'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
        'JANUARY': '01', 'FEBRUARY': '02', 'MARCH': '03', 'APRIL': '04',
        'MAY': '05', 'JUNE': '06', 'JULY': '07', 'AUGUST': '08',
        'SEPTEMBER': '09', 'OCTOBER': '10', 'NOVEMBER': '11', 'DECEMBER': '12'
    }
    
    # Pattern 1: DD MON YYYY (e.g., "02 FEB 2026")
    match = re.match(r'(\d{1,2})\s+([A-Za-z]+\.?)\s+(\d{4})', date_str, re.IGNORECASE)
    if match:
        day, month, year = match.groups()
        month_clean = re.sub(r'\.$', '', month.upper())  # Remove trailing period
        if month_clean in month_map:
            day_padded = day.zfill(2)
            month_num = month_map[month_clean]
            return f"{year}-{month_num}-{day_padded}"
    
    # Pattern 2: MON DD YYYY (e.g., "FEB 02 2026")
    match = re.match(r'([A-Za-z]+\.?)\s+(\d{1,2})\s+(\d{4})', date_str, re.IGNORECASE)
    if match:
        month, day, year = match.groups()
        month_clean = re.sub(r'\.$', '', month.upper())
        if month_clean in month_map:
            day_padded = day.zfill(2)
            month_num = month_map[month_clean]
            return f"{year}-{month_num}-{day_padded}"
    
    # Pattern 3: MON. DD, YYYY (e.g., "Feb. 02, 2024")
    match = re.match(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})', date_str, re.IGNORECASE)
    if match:
        month, day, year = match.groups()
        month_clean = month.upper()
        if month_clean in month_map:
            day_padded = day.zfill(2)
            month_num = month_map[month_clean]
            return f"{year}-{month_num}-{day_padded}"
    
    return None

def sanitize_filename_part(text, max_length=50):
    """
    Convert text to filesystem-safe string.
    
    Rules:
    - Convert to uppercase
    - Replace spaces with underscores
    - Remove special characters
    - Limit length
    """
    if not text or text == "Not found":
        return ""
    
    # Convert to uppercase for consistency
    text = text.upper()
    
    # Replace multiple spaces with single underscore
    text = re.sub(r'\s+', '_', text)
    
    # Remove characters that aren't alphanumeric, underscore, or hyphen
    text = re.sub(r'[^\w\-]', '', text)
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
    
    return text

def generate_new_filename(info, template=None):
    """
    Generate new filename based on extracted information.
    
    Uses template if provided, otherwise uses format based on document type:
    
    For "WAIVER OF ELECTRONIC TRANSMITTAL" documents:
      {Date}-{Lastname}-{DocumentType}
    
    For other notarized documents:
      {Date}-D{DocumentNumber}-{DocumentType}-{Lastname}
    
    Returns sanitized filename with .pdf extension.
    """
    original_name = Path(info['filename']).stem
    lastname = info['lastname']
    doc_type = info['document_type']
    doc_no = info['document_number']
    
    # Convert date to ISO format
    iso_date = None
    if info['date_of_notarization'] and info['date_of_notarization'] != "Not found":
        iso_date = convert_to_iso_date(info['date_of_notarization'])
    
    # Sanitize parts
    sanitized_lastname = sanitize_filename_part(lastname) if lastname and lastname != "Not found" else ""
    sanitized_doctype = sanitize_filename_part(doc_type) if doc_type and doc_type != "Not found" else ""
    sanitized_docno = sanitize_filename_part(doc_no) if doc_no and doc_no != "Not found" else ""
    
    # Generate filename based on available fields
    if template:
        # Simple template substitution
        filename = template
        filename = filename.replace('{Lastname}', sanitized_lastname)
        filename = filename.replace('{DocumentType}', sanitized_doctype)
        filename = filename.replace('{DocNo}', sanitized_docno)
        filename = filename.replace('{Date}', iso_date if iso_date else "")
        filename = filename.replace('{OriginalName}', original_name)
    else:
        # Determine format based on document type
        is_waiver = doc_type and "WAIVER OF ELECTRONIC TRANSMITTAL" in doc_type.upper()
        
        if is_waiver:
            # Waiver format: {Date}-{Lastname}-{DocumentType}
            if iso_date and sanitized_lastname and sanitized_doctype:
                filename = f"{iso_date}-{sanitized_lastname}-{sanitized_doctype}"
            elif iso_date and sanitized_lastname:
                filename = f"{iso_date}-{sanitized_lastname}-WAIVER"
            elif iso_date and sanitized_doctype:
                filename = f"{iso_date}-{sanitized_doctype}"
            elif sanitized_lastname and sanitized_doctype:
                filename = f"{sanitized_lastname}-{sanitized_doctype}"
            elif sanitized_doctype:
                filename = f"{original_name}_{sanitized_doctype}_renamed"
            else:
                filename = f"{original_name}_renamed"
        else:
            # Notarized document format: {Date}-D{DocumentNumber}-{DocumentType}-{Lastname}
            if iso_date and sanitized_docno and sanitized_doctype and sanitized_lastname:
                filename = f"{iso_date}-D{sanitized_docno}-{sanitized_doctype}-{sanitized_lastname}"
            elif iso_date and sanitized_doctype and sanitized_lastname:
                filename = f"{iso_date}-{sanitized_doctype}-{sanitized_lastname}"
            elif iso_date and sanitized_lastname:
                filename = f"{iso_date}-{sanitized_lastname}"
            elif sanitized_lastname and sanitized_doctype:
                filename = f"{sanitized_lastname}-{sanitized_doctype}"
            elif sanitized_doctype:
                filename = f"{original_name}_{sanitized_doctype}_renamed"
            else:
                filename = f"{original_name}_renamed"
    
    # Ensure filename isn't empty
    if not filename:
        filename = f"{original_name}_renamed"
    
    return f"{filename}.pdf"

def handle_duplicate_filename(target_path):
    """
    If target file exists, add numerical suffix.
    Returns new Path object.
    """
    if not target_path.exists():
        return target_path
    
    base = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix
    
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = base / new_name
        if not new_path.exists():
            return new_path
        counter += 1

def rename_file(pdf_path, md_path, output_dir, template=None, dry_run=False, interactive=False, db_manager=None, doc_id=None):
    """
    Rename a single PDF file based on OCR information.
    
    Returns (success, original_path, new_path, message)
    """
    pdf_path = Path(pdf_path)
    md_path = Path(md_path)
    output_dir = Path(output_dir)
    
    # Get extracted information (prefer validated database entries)
    try:
        info = get_extracted_info(md_path, db_manager, doc_id)
    except Exception as e:
        # Log error to database if available
        if db_manager and doc_id:
            try:
                db_manager.add_error_log(
                    document_id=doc_id,
                    agent_name='rename',
                    error_type='parse_error',
                    error_message=f"Failed to get extracted info: {e}"
                )
            except:
                pass
        return (False, pdf_path, None, f"Failed to get extracted info: {e}")
    
    # Generate new filename
    try:
        new_filename = generate_new_filename(info, template)
    except Exception as e:
        if db_manager and doc_id:
            try:
                db_manager.add_error_log(
                    document_id=doc_id,
                    agent_name='rename',
                    error_type='filename_generation_error',
                    error_message=f"Failed to generate filename: {e}"
                )
            except:
                pass
        return (False, pdf_path, None, f"Failed to generate filename: {e}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Construct target path
    target_path = output_dir / new_filename
    target_path = handle_duplicate_filename(target_path)
    
    # Prepare message
    msg = f"Would rename: {pdf_path.name} → {target_path.name}"
    
    if interactive:
        print(f"\n{msg}")
        print(f"  Lastname: {info['lastname'] or 'Not found'}")
        print(f"  Document Type: {info['document_type'] or 'Not found'}")
        print(f"  Date (ISO): {convert_to_iso_date(info['date_of_notarization']) or 'Not found'}")
        print(f"  Doc No.: {info['document_number'] or 'Not found'}")
        response = input("Proceed? (y/N): ").strip().lower()
        if response != 'y':
            if db_manager and doc_id:
                try:
                    db_manager.add_processing_log(
                        document_id=doc_id,
                        agent_name='rename',
                        operation='skip',
                        log_message=f"Rename skipped by user interaction"
                    )
                except:
                    pass
            return (False, pdf_path, None, f"Skipped by user: {pdf_path.name}")
    
    if dry_run:
        # Log dry run to database
        if db_manager and doc_id:
            try:
                db_manager.add_processing_log(
                    document_id=doc_id,
                    agent_name='rename',
                    operation='dry_run',
                    log_message=f"Dry run: would rename {pdf_path.name} to {target_path.name}",
                    parameters={"template": template, "dry_run": True}
                )
            except:
                pass
        return (True, pdf_path, target_path, msg)
    
    # Actually copy the file
    try:
        shutil.copy2(pdf_path, target_path)
        
        # Log successful rename to database
        if db_manager and doc_id:
            try:
                db_manager.add_rename_operation(
                    document_id=doc_id,
                    original_filename=pdf_path.name,
                    new_filename=target_path.name,
                    rename_template=template,
                    destination_path=str(target_path.relative_to(Path.cwd())),
                    success=True
                )
                db_manager.add_processing_log(
                    document_id=doc_id,
                    agent_name='rename',
                    operation='complete',
                    log_message=f"Successfully renamed {pdf_path.name} to {target_path.name}"
                )
            except Exception as db_error:
                print(f"Warning: Failed to log rename to database: {db_error}")
        
        return (True, pdf_path, target_path, f"Renamed: {pdf_path.name} → {target_path.name}")
    except Exception as e:
        # Log error to database
        if db_manager and doc_id:
            try:
                db_manager.add_rename_operation(
                    document_id=doc_id,
                    original_filename=pdf_path.name,
                    new_filename=target_path.name,
                    rename_template=template,
                    destination_path=str(target_path.relative_to(Path.cwd())),
                    success=False,
                    error_message=str(e)
                )
                db_manager.add_error_log(
                    document_id=doc_id,
                    agent_name='rename',
                    error_type='copy_error',
                    error_message=f"Failed to copy file: {e}"
                )
            except:
                pass
        return (False, pdf_path, None, f"Failed to copy file: {e}")

def main():
    parser = argparse.ArgumentParser(description="Rename PDF files based on OCR-extracted information")
    parser.add_argument("--input", default="input", help="Directory containing original PDF files")
    parser.add_argument("--ocr-output", default="ocr-output", help="Directory containing OCR markdown files")
    parser.add_argument("--output", default="renamed", help="Output directory for renamed files")
    parser.add_argument("--single", help="Process a single PDF file (without extension)")
    parser.add_argument("--template", help="Custom filename template (use {Lastname}, {DocumentType}, {Date}, {DocNo}, {OriginalName})")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without renaming files")
    parser.add_argument("--interactive", action="store_true", help="Prompt for confirmation before each rename")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files (use with caution)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already exist in output directory")
    parser.add_argument("--no-db", action="store_true", help="Disable database logging")
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    ocr_dir = Path(args.ocr_output)
    output_dir = Path(args.output)
    
    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}")
        sys.exit(1)
    
    if not ocr_dir.exists():
        print(f"Error: OCR output directory not found: {ocr_dir}")
        sys.exit(1)
    
    # Database initialization
    db_manager = None
    if DATABASE_AVAILABLE and not args.no_db:
        try:
            db_manager = DatabaseManager()  # type: ignore
            print("Database logging enabled")
        except Exception as e:
            print(f"Warning: Database initialization failed: {e}")
            db_manager = None
    else:
        if args.no_db:
            print("Database logging disabled by user request")
        else:
            print("Database logging unavailable (module not found)")
    
    # Collect PDF files to process
    if args.single:
        pdf_stem = Path(args.single).stem
        pdf_files = list(input_dir.glob(f"{pdf_stem}.pdf"))
        if not pdf_files:
            print(f"Error: PDF file not found: {args.single}")
            sys.exit(1)
    else:
        pdf_files = list(input_dir.glob("*.pdf"))
        if not pdf_files:
            print(f"No PDF files found in {input_dir}")
            return
    
    print(f"Found {len(pdf_files)} PDF file(s) to process.")
    if args.dry_run:
        print("DRY RUN MODE: No files will be renamed.")
    print()
    
    # Process each file
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for pdf_path in sorted(pdf_files):
        start_time = time.time()
        print(f"Processing: {pdf_path.name}")
        
        # Check if corresponding markdown file exists
        md_path = ocr_dir / f"{pdf_path.stem}.md"
        if not md_path.exists():
            print(f"  Warning: No OCR file found for {pdf_path.name}, skipping")
            skip_count += 1
            continue
        
        # Try to find document in database
        doc_id = None
        if db_manager:
            try:
                document = db_manager.get_document(original_filename=pdf_path.name)
                if document:
                    doc_id = document['id']
                    print(f"  Document ID: {doc_id}")
                    
                    # Log rename start
                    db_manager.add_processing_log(
                        document_id=doc_id,
                        agent_name='rename',
                        operation='start',
                        log_message=f"Starting rename operation for {pdf_path.name}"
                    )
                else:
                    print(f"  Warning: No database record found for {pdf_path.name}")
            except Exception as e:
                print(f"  Warning: Database lookup failed: {e}")
        
        # Rename the file
        success, original, new_path, message = rename_file(
            pdf_path, md_path, output_dir,
            template=args.template,
            dry_run=args.dry_run,
            interactive=args.interactive,
            db_manager=db_manager,
            doc_id=doc_id
        )
        
        print(f"  {message}")
        
        # Update processing time
        if db_manager and doc_id:
            try:
                processing_time = int((time.time() - start_time) * 1000)
                db_manager.add_processing_log(
                    document_id=doc_id,
                    agent_name='rename',
                    operation='complete' if success else 'error',
                    log_message=f"Rename operation completed" if success else f"Rename failed",
                    processing_time_ms=processing_time
                )
            except:
                pass
        
        if success:
            success_count += 1
        else:
            if "Skipped by user" in message:
                skip_count += 1
            else:
                error_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY:")
    print(f"  Successfully processed: {success_count}")
    print(f"  Skipped: {skip_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total: {len(pdf_files)}")
    
    # Database statistics
    if db_manager:
        try:
            stats = db_manager.get_statistics()
            print(f"\nDatabase Statistics:")
            print(f"  Total documents: {stats.get('total_documents', 0)}")
            print(f"  With OCR: {stats.get('documents_with_ocr', 0)}")
            print(f"  Extracted: {stats.get('documents_extracted', 0)}")
            print(f"  Renamed: {stats.get('documents_renamed', 0)}")
        except:
            pass
        finally:
            db_manager.close()
    
    if args.dry_run:
        print(f"\nOutput would be written to: {output_dir}")
    else:
        print(f"\nRenamed files saved to: {output_dir}")
        if output_dir.exists():
            renamed_files = list(output_dir.glob("*.pdf"))
            print(f"  Contains {len(renamed_files)} PDF file(s)")

if __name__ == "__main__":
    main()