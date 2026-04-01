# Notary Processing Center

A system for automating OCR, parsing, and renaming of notarial documents using AI-powered agents.

## Overview

This project provides a set of agents for processing notarial PDF documents:
- **OCR Agent**: Extracts text from PDFs using a local AI model (olmocr-2-7b)
- **Parse Agent**: Extracts key information (dates, document numbers, names, etc.) from OCR output
- **Rename Agent**: Renames PDF files based on extracted information with standardized naming
- **Database Agent**: Manages SQLite database for tracking processing history and audit trails
- **Main GUI Agent**: Integrated desktop interface for running all agents from a single application
- **Validation GUI Agent**: Desktop Tkinter interface for reviewing and correcting extracted data

## Project Structure

```
notary-processing-center/
├── .gitignore
├── README.md
├── AGENTS.md                    # Detailed agent documentation
├── ocr_processor.py            # OCR processing logic
├── document_parser.py          # Document parsing logic
├── rename_agent.py             # File renaming logic
├── database_manager.py         # Database operations
├── database_admin.py           # Database administration
├── database_schema.sqlite.sql  # SQL schema
├── init_database.py            # Database initialization
├── main_gui.py           # Main desktop interface for all agents
├── validation_gui.py           # Tkinter GUI for data validation
├── utils/                      # Utility scripts
│   ├── analyze_dates.py        # Date analysis utilities
│   ├── check_ocr_status.py     # OCR status checking
│   ├── import_rename_ops.py    # Import rename operations from logs
│   └── reprocess_failed.py     # Failed document reprocessing
├── input/                      # Input PDF files
├── ocr-output/                 # OCR markdown output
├── renamed/                    # Renamed PDF files
└── __pycache__/                # Python cache
```

## Quick Start

### Prerequisites

1. **Python 3.8+**
2. **Poppler** (for PDF to image conversion):
   ```bash
   brew install poppler  # macOS
   # or apt-get install poppler-utils on Linux
   ```
3. **Local AI Model Server**: Running olmocr-2-7b at `http://127.0.0.1:1234`
4. **Kilo CLI**: For running agents

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd notary-processing-center
   ```

2. Install Python dependencies:
   ```bash
   python3 -m pip install --user requests
   ```

3. Initialize the database:
   ```bash
   kilo agent database -- init --force
   ```

## Usage

### OCR Processing

Process all PDFs in the `input/` directory:
```bash
kilo agent ocr
```

Process a single PDF:
```bash
kilo agent ocr -- --single input/example.pdf
```

### Document Parsing

Parse OCR results to extract information:
```bash
kilo agent parse
```

### File Renaming

Rename PDFs based on extracted data:
```bash
kilo agent rename
```

### Database Administration

Initialize database:
```bash
kilo agent database -- init
```

View statistics:
```bash
kilo agent database -- stats
```

### Main GUI

Run the integrated desktop interface:
```bash
python3 main_gui.py
```

This opens a tabbed application with access to all agents.

## Data Flow

1. **Input**: PDF files placed in `input/` directory
2. **OCR**: PDFs converted to text via AI model → `ocr-output/` markdown files
3. **Parsing**: Extract metadata (dates, document numbers, names, etc.)
4. **Renaming**: Generate standardized filenames → `renamed/` directory
5. **Database**: All steps tracked in SQLite database for audit trail

## File Naming Conventions

### Notarized Documents
`{YYYY-MM-DD}-D{DocumentNumber}-{DocumentType}-{Lastname}.pdf`

Example: `2026-02-02-D12345-AFFIDAVIT_OF_LOSS-SMITH.pdf`

### Waiver Documents
`{YYYY-MM-DD}-{Lastname}-WAIVER_OF_ELECTRONIC_TRANSMITTAL.pdf`

Example: `2026-02-02-JOHNSON-WAIVER_OF_ELECTRONIC_TRANSMITTAL.pdf`

## Database Schema

The SQLite database (`notary_processing.db`) includes:
- `documents`: Master list of PDF files
- `ocr_results`: OCR processing results per page
- `extracted_data`: Parsed document information
- `rename_operations`: File rename history
- `processing_logs`: Detailed processing history
- `error_logs`: Error tracking
- `audit_log`: Audit trail of all significant actions

## Notes

- Original PDFs remain unchanged in `input/`
- All processing steps are logged for compliance
- The system skips already processed files
- Large PDFs may require adjustment of DPI settings
- Missing fields in documents result in fallback naming strategies

## License

This project is for internal use.
