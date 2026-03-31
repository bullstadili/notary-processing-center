#!/usr/bin/env python3
"""
Parse OCR-extracted markdown files to extract key document information:
- Date of notarization
- Document number
- Type of legal document
- Page number (Page No.)
- Book number (Book No.)
- Series year (Series of)
- Lastname of the party (for individuals) or signing party (for corporations/juridical entities)
"""
import argparse
import re
import sys
import time
from pathlib import Path

# Database integration
try:
    from database_manager import DatabaseManager  # type: ignore
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("Warning: database_manager module not found. Database logging disabled.")

def extract_date_of_notarization(text):
    """Extract date of notarization from text."""
    patterns = [
        # "SUBSCRIBED AND SWORN TO BEFORE ME this 12 FEB 2026 day of February, 2026"
        r"SUBSCRIBED AND SWORN TO BEFORE ME.*?this\s+(\d{1,2}\s+[A-Z]+\s+\d{4})",
        # "SUBSCRIBED AND SWORN TO BEFORE ME, a notary public ... this ____ day of FEB 02 2026"
        r"this\s+[^0-9]*?([A-Z]+\s+\d{1,2}\s+\d{4})",
        # "IN WITNESS WHEREOF, I have hereunto set my hand this FEB 02 2026"
        r"set my hand this\s+([A-Z]+\s+\d{1,2}\s+\d{4})",
        # "this 02 FEB 2026 day of February, 2026"
        r"this\s+(\d{1,2}\s+[A-Z]+\s+\d{4})\s+day",
        # "Date of Notarization: Feb. 02, 2020" (waiver)
        r"Date of Notarization:\s*([A-Za-z]+\.?\s*\d{1,2},?\s*\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            date_str = match.group(1).strip()
            # Clean up extra spaces
            date_str = re.sub(r'\s+', ' ', date_str)
            return date_str
    return None

def extract_document_number(text):
    """Extract document number from text."""
    patterns = [
        # "Doc. No. /;" or "Doc. No: 2"
        r"Doc\.?\s*No\.?\s*[:;]?\s*([^;\s]+)",
        # "Document No.:"
        r"Document\s+No\.?\s*[:;]?\s*([^;\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            doc_no = match.group(1).strip()
            # Remove non-alphanumeric characters at ends
            doc_no = re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', doc_no)
            # Check if doc_no is just a slash or invalid
            if doc_no in ['/', 'V', '']:
                return None
            return doc_no
    return None

def extract_document_type(text):
    """Extract type of legal document from text."""
    # Skip error lines
    if 'Error processing page:' in text:
        return None
    
    # Special case for judicial affidavit
    if 'JUDICIAL AFFIDAVIT' in text:
        return 'JUDICIAL AFFIDAVIT'
    
    # Look for lines in all caps (common for titles)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        # Skip empty lines and headers
        if not line or line.startswith('#') or 'REPUBLIC OF THE PHILIPPINES' in line:
            continue
        # Skip Q/A lines
        if line.startswith(('Q:', 'A:', 'Q.', 'A.')) or re.match(r'^\d+\.\s*[QA]', line):
            continue
        # Skip lines that contain "Error processing"
        if 'Error processing' in line:
            continue
        # Check if line looks like a title (all caps, maybe with spaces and punctuation)
        if line.isupper() and len(line) > 5 and len(line) < 100:
            # Exclude common phrases
            if any(phrase in line for phrase in ['SUBSCRIBED', 'WITNESS', 'ACKNOWLEDGMENT', 'NOTARY PUBLIC', 
                                                 'PETITIONER', 'RESPONDENT', 'REGIONAL TRIAL COURT']):
                continue
            # Check if next lines contain "I," or "We," indicating start of document
            next_lines = ' '.join(lines[i+1:i+3])
            if 'I,' in next_lines or 'We,' in next_lines:
                return line
    
    # Look for non-all-caps titles that are prominent (e.g., "For Nullity of Marriage")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Skip Q/A lines
        if line.startswith(('Q:', 'A:', 'Q.', 'A.')) or re.match(r'^\d+\.\s*[QA]', line):
            continue
        # Check if line appears before main content (first 20 lines)
        if i < 20 and len(line) > 10 and len(line) < 100:
            # Check if line contains typical document type words
            doc_keywords = ['affidavit', 'authorization', 'designation', 'verification', 
                           'certification', 'waiver', 'deed', 'contract', 'power', 'judicial']
            if any(keyword in line.lower() for keyword in doc_keywords):
                return line
            # Check if line is followed by "I," or "We,"
            next_lines = ' '.join(lines[i+1:i+3])
            if 'I,' in next_lines or 'We,' in next_lines:
                return line
    
    # Look for phrase "refer to a ..." (common in notarial certificates)
    match = re.search(r'refer to a\s+([A-Z][A-Za-z\s]+?) (?:signed|executed)', text, re.IGNORECASE)
    if match:
        doc_type = match.group(1).strip()
        return doc_type.upper()
    
    # Fallback: search for common document types
    common_types = [
        r'AFFIDAVIT OF LOSS',
        r'AUTHORIZATION AND DESIGNATION',
        r'JUDICIAL AFFIDAVIT',
        r'VERIFICATION',
        r'CERTIFICATION',
        r'WAIVER',
        r'DEED OF SALE',
        r'CONTRACT',
        r'POWER OF ATTORNEY',
        r'FOR NULLITY OF MARRIAGE',
        r'AFFIDAVIT OF BUSINESS CLOSURE',
        r'AFFIDAVIT OF ADJOINING OWNER',
    ]
    for pattern in common_types:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return None

def extract_lastname(text):
    """Extract lastname of the party from text."""
    # Pattern for "I, FIRST MIDDLE LASTNAME" (common in affidavits)
    match = re.search(r'I,\s+([A-Z][A-Z\s\.]+?)(?:,|\s+of|\s+Filipino)', text)
    if match:
        name = match.group(1).strip()
        parts = name.split()
        if parts:
            last = parts[-1]
            if last.isalpha() and len(last) > 1:
                return last
    
    # Pattern for "A: I, FIRST MIDDLE LASTNAME" (in Q&A judicial affidavits)
    match = re.search(r'A:\s*I,\s+([A-Z][A-Z\s\.]+?)(?:,|\s+of|\s+Filipino)', text)
    if match:
        name = match.group(1).strip()
        parts = name.split()
        if parts:
            last = parts[-1]
            if last.isalpha() and len(last) > 1:
                return last
    
    # Pattern for "We, spouses FIRST LAST and FIRST LAST"
    match = re.search(r'We,\s+spouses?\s+([A-Z][A-Z\s\.]+?)\s+and\s+([A-Z][A-Z\s\.]+)', text)
    if match:
        name1 = match.group(1).strip()
        parts = name1.split()
        if parts:
            last = parts[-1]
            if last.isalpha() and len(last) > 1:
                return last
    
    # Pattern for "We, FIRST LAST and FIRST LAST" (without spouses)
    match = re.search(r'We,\s+([A-Z][A-Z\s\.]+?)\s+and\s+([A-Z][A-Z\s\.]+)', text)
    if match:
        name1 = match.group(1).strip()
        parts = name1.split()
        if parts:
            last = parts[-1]
            if last.isalpha() and len(last) > 1:
                return last
    
    # Look for signature blocks - lines that start with all caps name pattern
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        # Match lines that start with all caps name (possibly with dots and spaces)
        # Exclude lines that contain common non-name words
        if re.match(r'^[A-Z][A-Z\s\.]*[A-Z](?:\s|$)', line):
            if any(word in line for word in ['AFFIANT', 'NOTARY', 'PUBLIC', 'WITNESS', 'SUBSCRIBED', 
                                             'ACKNOWLEDGMENT', 'LAND', 'OWNER', 'WAIVER', 'Q:', 'A:',
                                             'PETITIONER', 'RESPONDENT', 'CLINICAL', 'PSYCHOLOGIST',
                                             'LIC', 'NO', 'TIN', 'DRIVER', 'SIGNED', 'PRESENCE', 'OF:',
                                             'ATTY', 'ATTY.', 'NOTARY PUBLIC', 'ROLL', 'MCLE', 'IBP', 'PTR']):
                continue
            # Should have at least two parts (first and last name)
            parts = line.split()
            if 2 <= len(parts) <= 5:
                last = parts[-1]
                # Clean up trailing punctuation
                last = re.sub(r'[^A-Za-z]+$', '', last)
                if last.isalpha() and len(last) > 1:
                    return last
    
    return None

def extract_page_number(text):
    """Extract page number from text."""
    patterns = [
        r"Page\s+No\.?\s*[:;]?\s*([^;\s]+)",
        r"Page\s+No\.?\s*([^;\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            page_no = match.group(1).strip()
            # Remove non-alphanumeric characters at ends
            page_no = re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', page_no)
            if page_no in ['/', '']:
                return None
            return page_no
    return None

def extract_book_number(text):
    """Extract book number from text."""
    patterns = [
        r"Book\s+No\.?\s*[:;]?\s*([^;\s]+)",
        r"Book\s+No\.?\s*([^;\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            book_no = match.group(1).strip()
            # Remove non-alphanumeric characters at ends
            book_no = re.sub(r'^[^A-Za-z0-9]+|[^A-Za-z0-9]+$', '', book_no)
            if book_no in ['/', '']:
                return None
            return book_no
    return None

def extract_series_year(text):
    """Extract series year from text."""
    patterns = [
        r"Series\s+of\s+(\d{4})",
        r"Series\s+(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def extract_lastname_enhanced(text):
    """Extract lastname of the party, handling corporations/juridical entities and waivers."""
    # First check if this is a waiver document
    if 'WAIVER OF ELECTRONIC TRANSMITTAL' in text.upper():
        # Look for signatory information in waiver document
        # Pattern 1: Look for table rows with names like "NOEL I. CERIAS" or "Wilbert A. Bayonifa"
        # First try to find name in table after "SIGNATORY INFORMATION"
        lines = text.split('\n')
        in_signatory_section = False
        for line in lines:
            line = line.strip()
            if 'SIGNATORY INFORMATION' in line.upper():
                in_signatory_section = True
                continue
            if in_signatory_section:
                # Look for table row with name
                # Match patterns like: <td>NOEL I. CERIAS</td> or <td>Wilbert A. Bayonifa</td>
                td_match = re.search(r'<td>([A-Z][A-Za-z\s\.]+?)</td>', line)
                if td_match:
                    name = td_match.group(1).strip()
                    # Extract lastname (last part after spaces)
                    parts = name.split()
                    if parts:
                        last = parts[-1]
                        last = re.sub(r'[^A-Za-z]+$', '', last)
                        if last.isalpha() and len(last) > 1:
                            return last
        
        # Pattern 2: Look for name patterns in lines (non-table format)
        for line in lines:
            line = line.strip()
            # Look for all caps name pattern (e.g., "NOEL I. CERIAS")
            if re.match(r'^[A-Z][A-Z\s\.]+[A-Z]$', line):
                parts = line.split()
                if 2 <= len(parts) <= 4:
                    last = parts[-1]
                    last = re.sub(r'[^A-Za-z]+$', '', last)
                    if last.isalpha() and len(last) > 1:
                        return last
    
    # Check if this appears to be a corporation/juridical entity
    corp_keywords = [r'\bcorporation\b', r'\binc\.', r'\bllc\b', r'\bcompany\b', 
                     r'\bcorp\.', r'\bltd\.', r'\bco\.', r'\bincorporated\b',
                     r'\bcorporated\b', r'\bcorporations\b']
    
    is_corporation = False
    for pattern in corp_keywords:
        if re.search(pattern, text, re.IGNORECASE):
            is_corporation = True
            break
    
    # If corporation, look for signing party patterns
    if is_corporation:
        # Patterns for corporate signatories: "By:", "Per:", "For:", "Signed by:"
        signatory_patterns = [
            r'(?:By|Per|For|Signed\s+by)\s*:\s*([A-Z][A-Z\s\.]+?)(?:\s*$|\s*,|\s*\(|\.)',
            r'(?:BY|PER|FOR)\s*:\s*([A-Z][A-Z\s\.]+)',
        ]
        for pattern in signatory_patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                parts = name.split()
                if parts:
                    last = parts[-1]
                    last = re.sub(r'[^A-Za-z]+$', '', last)
                    if last.isalpha() and len(last) > 1:
                        return last
    
    # Fall back to original extract_lastname logic
    return extract_lastname(text)

# Keep original extract_lastname for backward compatibility
# but we'll use extract_lastname_enhanced in parse_markdown_file

def parse_markdown_file(file_path, db_manager=None, doc_id=None):
    """Parse a single markdown file and return extracted info.
    
    If db_manager and doc_id are provided, extracted data will be stored in database.
    """
    # Ensure file_path is a Path object
    file_path = Path(file_path)
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove markdown headers (# and ##) for cleaner text
    clean_content = re.sub(r'^#+\s.*$', '', content, flags=re.MULTILINE)
    
    info = {
        'filename': file_path.name,
        'date_of_notarization': extract_date_of_notarization(clean_content),
        'document_number': extract_document_number(clean_content),
        'document_type': extract_document_type(clean_content),
        'page_number': extract_page_number(clean_content),
        'book_number': extract_book_number(clean_content),
        'series_year': extract_series_year(clean_content),
        'lastname': extract_lastname_enhanced(clean_content),
    }
    
    # Store extracted data in database if db_manager and doc_id provided
    if db_manager and doc_id:
        try:
            # Determine if document is waiver
            is_waiver = False
            doc_type = info['document_type']
            if doc_type and 'WAIVER' in doc_type.upper():
                is_waiver = True
            
            # Determine if corporate (based on lastname extraction logic)
            is_corporate = False
            # Check if corporation patterns exist in text
            corp_patterns = [
                r'\b(?:INC|CORP|CORPORATION|COMPANY|CO\.|LTD|LLC)\b',
                r'\b(?:BY|PER|FOR|SIGNED BY)\s*:',
            ]
            for pattern in corp_patterns:
                if re.search(pattern, clean_content, re.IGNORECASE):
                    is_corporate = True
                    break
            
            # Calculate confidence score (simple heuristic)
            confidence = 0.0
            fields_found = sum(1 for field in ['date_of_notarization', 'document_number', 
                                              'document_type', 'lastname'] if info[field])
            confidence = fields_found / 4.0  # 0.0 to 1.0
            
            db_manager.add_extracted_data(
                document_id=doc_id,
                date_of_notarization=info['date_of_notarization'],
                document_number=info['document_number'],
                document_type=info['document_type'],
                page_number=info['page_number'],
                book_number=info['book_number'],
                series_year=info['series_year'],
                lastname=info['lastname'],
                is_waiver=is_waiver,
                is_corporate=is_corporate,
                confidence_score=confidence
            )
        except Exception as e:
            print(f"Warning: Failed to store extracted data in database: {e}")
    
    return info

def main():
    parser = argparse.ArgumentParser(description="Parse OCR output for document information")
    parser.add_argument("--input", default="ocr-output", help="Directory containing markdown files")
    parser.add_argument("--single", help="Parse a single markdown file")
    parser.add_argument("--no-db", action="store_true", help="Disable database logging")
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    
    if args.single:
        file_path = Path(args.single)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            sys.exit(1)
        files = [file_path]
    else:
        if not input_dir.exists():
            print(f"Input directory does not exist: {input_dir}")
            sys.exit(1)
        files = list(input_dir.glob("*.md"))
        if not files:
            print(f"No markdown files found in {input_dir}")
            return
    
    print(f"Found {len(files)} markdown file(s).")
    
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
    
    print("-" * 80)
    
    for file_path in files:
        start_time = time.time()
        print(f"Processing: {file_path.name}")
        
        # Try to find document in database by original filename
        doc_id = None
        if db_manager:
            try:
                # Extract original PDF filename (same stem as markdown file)
                original_filename = file_path.stem + ".pdf"
                document = db_manager.get_document(original_filename=original_filename)
                if document:
                    doc_id = document['id']
                    print(f"  Document ID: {doc_id}")
                    
                    # Log parsing start
                    db_manager.add_processing_log(
                        document_id=doc_id,
                        agent_name='parse',
                        operation='start',
                        log_message=f"Starting parsing of {file_path.name}"
                    )
                else:
                    print(f"  Warning: No database record found for {original_filename}")
            except Exception as e:
                print(f"  Warning: Database lookup failed: {e}")
        
        # Parse the file
        try:
            info = parse_markdown_file(file_path, db_manager, doc_id)
            parse_time = int((time.time() - start_time) * 1000)
            
            # Print results
            print(f"  Date of Notarization: {info['date_of_notarization'] or 'Not found'}")
            print(f"  Document Number: {info['document_number'] or 'Not found'}")
            print(f"  Document Type: {info['document_type'] or 'Not found'}")
            print(f"  Page No.: {info['page_number'] or 'Not found'}")
            print(f"  Book No.: {info['book_number'] or 'Not found'}")
            print(f"  Series Year: {info['series_year'] or 'Not found'}")
            print(f"  Lastname: {info['lastname'] or 'Not found'}")
            
            # Log successful parsing to database
            if db_manager and doc_id:
                try:
                    db_manager.add_processing_log(
                        document_id=doc_id,
                        agent_name='parse',
                        operation='complete',
                        log_message=f"Parsing completed for {file_path.name}",
                        processing_time_ms=parse_time
                    )
                    print(f"  Results logged to database")
                except Exception as e:
                    print(f"  Warning: Failed to log parsing completion: {e}")
            
        except Exception as e:
            print(f"  Error parsing {file_path.name}: {e}")
            
            # Log error to database
            if db_manager and doc_id:
                try:
                    db_manager.add_error_log(
                        document_id=doc_id,
                        agent_name='parse',
                        error_type='parse_error',
                        error_message=f"Failed to parse markdown file: {e}"
                    )
                except:
                    pass
        
        print("-" * 80)
    
    # Close database connection
    if db_manager:
        db_manager.close()

if __name__ == "__main__":
    main()