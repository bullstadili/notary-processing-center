#!/usr/bin/env python3
"""
OCR Processor using local olmocr-2-7b model.
Processes PDF files from input folder, outputs markdown to ocr-output folder.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import requests
import time
from pathlib import Path

# Database integration
try:
    from database_manager import DatabaseManager  # type: ignore
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("Warning: database_manager module not found. Database logging disabled.")

MODEL_ENDPOINT = "http://127.0.0.1:1234/v1/chat/completions"
MODEL_NAME = "allenai/olmocr-2-7b"
TEMPERATURE_BY_ATTEMPT = [0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 0.9, 1.0]
OLMOCR_PROMPT = (
    "Attached is one page of a document that you must process. "
    "Just return the plain text representation of this document as if you were reading it naturally. Convert equations to LateX and tables to HTML.\n"
    "If there are any figures or charts, label them with the following markdown syntax ![Alt text describing the contents of the figure](page_startx_starty_width_height.png)\n"
    "Return your output as markdown, with a front matter section on top specifying values for the primary_language, is_rotation_valid, rotation_correction, is_table, and is_diagram parameters."
)

def parse_olmocr_response(content):
    """Parse olmOCR response to extract natural text from front matter format."""
    if not content:
        return ""
    
    # Check if response contains YAML front matter
    if content.startswith('---\n'):
        parts = content.split('\n---\n', 1)
        if len(parts) == 2:
            # front_matter = parts[0][4:]  # Remove initial '---\n'
            natural_text = parts[1].strip()
            return natural_text
    
    # If no front matter, return content as-is
    return content.strip()

def maybe_resize_image(image_path, max_width=800):
    """Resize image if width exceeds max_width, return new path (maybe same)."""
    # Get image dimensions using identify
    try:
        output = subprocess.run(["identify", "-format", "%w %h", image_path],
                               capture_output=True, text=True, check=True)
        width, height = map(int, output.stdout.strip().split())
        if width <= max_width:
            return image_path
        # Resize using convert, also ensure RGB and remove alpha
        new_path = image_path.with_stem(image_path.stem + "_resized")
        subprocess.run(["convert", image_path, "-resize", f"{max_width}x", "-alpha", "remove", "-background", "white", "-flatten", new_path],
                      check=True, capture_output=True)
        return new_path
    except Exception as e:
        print(f"Resize failed for {image_path}: {e}, using original")
        return image_path

def extract_text_from_image(image_path, timeout=500, max_retries=3):
    """Send image to OCR model and return extracted text."""
    image_path = Path(image_path)
    # Resize if needed
    resized_path = maybe_resize_image(image_path)
    
    try:
        for attempt in range(max_retries):
            try:
                with open(resized_path, "rb") as f:
                    base64_image = base64.b64encode(f.read()).decode('utf-8')
                
                temperature = TEMPERATURE_BY_ATTEMPT[min(attempt, len(TEMPERATURE_BY_ATTEMPT) - 1)]
                payload = {
                    "model": MODEL_NAME,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": OLMOCR_PROMPT},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                            ]
                        }
                    ],
                    "max_tokens": 8000,
                    "temperature": temperature,
                }
                
                headers = {"Content-Type": "application/json"}
                response = requests.post(MODEL_ENDPOINT, headers=headers, json=payload, timeout=timeout)
                if response.status_code != 200:
                    print(f"API error {response.status_code}: {response.text[:200]}")
                    if attempt < max_retries - 1:
                        print(f"Retrying... (attempt {attempt + 1}/{max_retries})")
                        continue
                    return ""
                response.raise_for_status()
                result = response.json()
                content = result['choices'][0]['message']['content']
                return parse_olmocr_response(content.strip())
            except requests.exceptions.Timeout:
                print(f"Timeout processing image {image_path.name} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    continue
                return ""
            except Exception as e:
                print(f"Error processing image {image_path}: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying... (attempt {attempt + 1}/{max_retries})")
                    continue
                return ""
        return ""
    finally:
        # Clean up resized file if different from original
        if resized_path != image_path and resized_path.exists():
            resized_path.unlink()

def pdf_to_images(pdf_path, output_dir, dpi=150):
    """Convert PDF pages to PNG images using pdftoppm."""
    pdf_path = Path(pdf_path)
    stem = pdf_path.stem
    # pdftoppm -png -r 200 input.pdf output_prefix
    cmd = ["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(output_dir / stem)]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"pdftoppm failed: {e.stderr.decode()}")
        raise
    
    # Collect generated PNG files
    pattern = str(output_dir / f"{stem}-*.png")
    import glob
    images = sorted(glob.glob(pattern))
    # If pdftoppm uses single digit numbering?
    if not images:
        # try alternative pattern
        pattern = str(output_dir / f"{stem}_*.png")
        images = sorted(glob.glob(pattern))
    if not images:
        # maybe no dash
        pattern = str(output_dir / f"{stem}*.png")
        images = sorted(glob.glob(pattern))
    return images

def calculate_page_timeout(base_timeout, page_count, pdf_size_bytes=None):
    """Calculate per-page timeout based on document size and page count."""
    # Base timeout per page increases with page count
    # Add 30% extra timeout for each page beyond the first
    page_factor = 1.0 + (page_count - 1) * 0.3
    
    # Consider file size if provided (in MB)
    size_factor = 1.0
    if pdf_size_bytes:
        size_mb = pdf_size_bytes / (1024 * 1024)
        # For large files, add extra timeout more generously
        # 1MB = 0.2x factor, max 5x factor for 20MB+ files
        size_factor = 1.0 + min(5.0, size_mb * 0.2)
    
    # Combined factor, cap at 10x
    combined_factor = min(10.0, page_factor * size_factor)
    
    # Calculate final timeout, cap at 2000 seconds (33 minutes) per page
    page_timeout = min(2000, int(base_timeout * combined_factor))
    
    return page_timeout

def process_pdf(pdf_path, output_dir, dpi=150, timeout=500, max_retries=3, force=False):
    """Process a single PDF file with database integration."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Output markdown file path
    md_path = output_dir / f"{pdf_path.stem}.md"
    
    # Database integration
    doc_id = None
    db_manager = None
    skip_processing = False
    skip_reason = ""
    
    if DATABASE_AVAILABLE:
        try:
            db_manager = DatabaseManager()  # type: ignore
            
            # Check if document already exists in database
            existing_doc = db_manager.get_document(original_filename=pdf_path.name)
            
            if existing_doc:
                doc_id = existing_doc['id']
                current_status = existing_doc['status']
                
                # If document is already processed and force flag is not set, skip
                if current_status == 'processed' and not force:
                    skip_processing = True
                    skip_reason = f"Document already processed (status: {current_status})"
                    print(f"Skipping {pdf_path.name}: {skip_reason}")
                    
                    # Log skip to database
                    db_manager.add_processing_log(
                        document_id=doc_id,
                        agent_name='ocr',
                        operation='skip',
                        log_message=f"Skipped - {skip_reason}"
                    )
                    return
                
                # Update status to processing if not already processing
                if current_status != 'processing':
                    db_manager.update_document_status(doc_id, 'processing')
                
                # Log processing start (resume/retry)
                db_manager.add_processing_log(
                    document_id=doc_id,
                    agent_name='ocr',
                    operation='start',
                    log_message=f"{'Resuming' if current_status == 'failed' else 'Starting'} OCR processing for {pdf_path.name}",
                    parameters={"dpi": dpi, "timeout": timeout, "max_retries": max_retries}
                )
                
            else:
                # Document doesn't exist, add it to database
                file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
                file_hash = db_manager.calculate_file_hash(str(pdf_path))
                abs_path = str(pdf_path.resolve())
                
                doc_id = db_manager.add_document(
                    original_filename=pdf_path.name,
                    file_path=abs_path,
                    file_size_bytes=file_size,
                    file_hash=file_hash,
                    page_count=0,  # Will be updated after PDF conversion
                    status='processing'
                )
                
                # Log processing start (new document)
                db_manager.add_processing_log(
                    document_id=doc_id,
                    agent_name='ocr',
                    operation='start',
                    log_message=f"Starting OCR processing for {pdf_path.name}",
                    parameters={"dpi": dpi, "timeout": timeout, "max_retries": max_retries}
                )
                
        except Exception as e:
            print(f"Warning: Database integration failed: {e}")
            doc_id = None
            db_manager = None
    
    # Fallback check: if database not available, check if output file exists
    if not db_manager and md_path.exists() and not force:
        print(f"Output already exists: {md_path}")
        print("Note: Database not available, skipping based on file existence")
        return
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        print(f"Converting PDF {pdf_path.name} to images (DPI {dpi})...")
        try:
            images = pdf_to_images(pdf_path, tmpdir, dpi)
        except Exception as e:
            print(f"Failed to convert PDF {pdf_path}: {e}")
            if db_manager and doc_id:
                try:
                    db_manager.update_document_status(doc_id, 'failed')
                    db_manager.add_error_log(
                        document_id=doc_id,
                        agent_name='ocr',
                        error_type='pdf_conversion_error',
                        error_message=f"Failed to convert PDF: {e}"
                    )
                except:
                    pass
            return
        
        if not images:
            print(f"No images generated for {pdf_path}")
            if db_manager and doc_id:
                try:
                    db_manager.update_document_status(doc_id, 'failed')
                    db_manager.add_error_log(
                        document_id=doc_id,
                        agent_name='ocr',
                        error_type='no_images_generated',
                        error_message="PDF conversion produced no images"
                    )
                except:
                    pass
            return
        
        # Get PDF file size for timeout calculation
        pdf_size = pdf_path.stat().st_size if pdf_path.exists() else None
        
        # Calculate per-page timeout based on document size
        page_count = len(images)
        page_timeout = calculate_page_timeout(timeout, page_count, pdf_size)
        if page_timeout != timeout:
            print(f"  Adjusted per-page timeout: {page_timeout}s (base: {timeout}s, pages: {page_count})")
        
        print(f"Found {page_count} pages. Processing OCR...")
        pages_text = []
        processing_start = time.time()
        
        for i, img_path in enumerate(images, start=1):
            print(f"  Page {i}...")
            page_start = time.time()
            text = extract_text_from_image(img_path, timeout=page_timeout, max_retries=max_retries)
            page_time = int((time.time() - page_start) * 1000)  # milliseconds
            
            pages_text.append((i, text))
            
            # Log OCR result for this page to database
            if db_manager and doc_id:
                try:
                    ocr_params = {
                        "dpi": dpi,
                        "timeout": page_timeout,
                        "max_retries": max_retries,
                        "page_number": i
                    }
                    db_manager.add_ocr_result(
                        document_id=doc_id,
                        page_number=i,
                        ocr_text=text,
                        ocr_parameters=ocr_params,
                        processing_time_ms=page_time
                    )
                except Exception as e:
                    print(f"Warning: Failed to log OCR result for page {i}: {e}")
        
        total_time = int((time.time() - processing_start) * 1000)
        
        # Write markdown
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# {pdf_path.name}\n\n")
            for page_num, text in pages_text:
                f.write(f"## Page {page_num}\n\n")
                f.write(text)
                f.write("\n\n")
        
        print(f"OCR output written to {md_path}")
        
        # Update database with completion status
        if db_manager and doc_id:
            try:
                db_manager.update_document_status(doc_id, 'processed')
                db_manager.add_processing_log(
                    document_id=doc_id,
                    agent_name='ocr',
                    operation='complete',
                    log_message=f"OCR completed successfully for {pdf_path.name}",
                    parameters={"pages": page_count, "total_time_ms": total_time},
                    processing_time_ms=total_time
                )
                print(f"  Processing logged to database (Document ID: {doc_id})")
            except Exception as e:
                print(f"Warning: Failed to update database completion status: {e}")

def check_dependencies():
    """Ensure required tools are available."""
    import shutil
    for cmd in ["pdftoppm", "identify", "convert"]:
        if shutil.which(cmd) is None:
            print(f"Error: {cmd} not found in PATH. Please install required tools.")
            sys.exit(1)
    try:
        import requests
    except ImportError:
        print("Error: Python module 'requests' not installed. Run: python3 -m pip install --user requests")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="OCR PDFs using local AI model")
    parser.add_argument("--input", default="input", help="Input directory containing PDFs")
    parser.add_argument("--output", default="ocr-output", help="Output directory for markdown files")
    parser.add_argument("--single", help="Process a single PDF file")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for PDF to image conversion")
    parser.add_argument("--timeout", type=int, default=500, help="Timeout for API requests in seconds")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum retries for API requests")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")
    args = parser.parse_args()
    
    check_dependencies()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    
    if args.single:
        pdf_path = Path(args.single)
        if not pdf_path.exists():
            print(f"File not found: {pdf_path}")
            sys.exit(1)
        process_pdf(pdf_path, output_dir, args.dpi, args.timeout, args.max_retries, args.force)
    else:
        if not input_dir.exists():
            print(f"Input directory does not exist: {input_dir}")
            sys.exit(1)
        
        pdf_files = list(input_dir.glob("*.pdf"))
        if not pdf_files:
            print(f"No PDF files found in {input_dir}")
            return
        
        print(f"Found {len(pdf_files)} PDF files.")
        for pdf in pdf_files:
            print(f"\nProcessing {pdf.name}...")
            process_pdf(pdf, output_dir, args.dpi, args.timeout, args.max_retries, args.force)

if __name__ == "__main__":
    main()