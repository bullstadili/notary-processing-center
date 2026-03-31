-- SQLite Database Schema for Notary Processing Center
-- Created: 2026-03-31

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ==================== CORE TABLES ====================

-- Documents table: Master list of all PDF files
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT NOT NULL UNIQUE,
    file_size_bytes INTEGER,
    file_hash TEXT, -- SHA-256 hash for deduplication
    file_path TEXT, -- Original path relative to project root
    page_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'processed', 'failed', 'skipped'))
);

-- OCR Results table: Store OCR processing results per page
CREATE TABLE IF NOT EXISTS ocr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    ocr_text TEXT,
    ocr_confidence REAL, -- Optional: could be derived from model if available
    ocr_engine TEXT DEFAULT 'olmocr-2-7b',
    ocr_parameters TEXT, -- JSON of parameters used (DPI, timeout, etc.)
    processing_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, page_number)
);

-- Extracted Data table: Store parsed/structured information
CREATE TABLE IF NOT EXISTS extracted_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL UNIQUE, -- One-to-one with document
    date_of_notarization TEXT,
    document_number TEXT,
    document_type TEXT,
    document_category TEXT, -- Standardized category (Affidavit, Waiver, Contract, etc.)
    page_number TEXT, -- Page No. from notarial register
    book_number TEXT, -- Book No.
    series_year TEXT, -- Series of
    lastname TEXT,
    is_waiver INTEGER DEFAULT 0, -- Boolean flag for waiver documents
    is_corporate INTEGER DEFAULT 0, -- Boolean flag for corporate documents
    extraction_method TEXT, -- 'regex', 'manual', 'ai', etc.
    confidence_score REAL, -- 0.0 to 1.0
    extraction_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Rename Operations table: Track all file rename operations
CREATE TABLE IF NOT EXISTS rename_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    original_filename TEXT NOT NULL,
    new_filename TEXT NOT NULL,
    rename_template TEXT, -- Template used for renaming
    rename_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    destination_path TEXT, -- Path where renamed file is stored
    success INTEGER DEFAULT 1, -- Boolean
    error_message TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- ==================== SUPPORT TABLES ====================

-- Processing Logs table: Detailed processing history
CREATE TABLE IF NOT EXISTS processing_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    agent_name TEXT NOT NULL, -- 'ocr', 'parse', 'rename', etc.
    operation TEXT NOT NULL, -- 'start', 'complete', 'error', 'retry'
    log_message TEXT,
    parameters TEXT, -- JSON of parameters used
    processing_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Error Logs table: Store detailed error information
CREATE TABLE IF NOT EXISTS error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    agent_name TEXT NOT NULL,
    error_type TEXT, -- 'ocr_api_error', 'parse_error', 'file_not_found', etc.
    error_message TEXT,
    error_details TEXT, -- JSON with stack trace, context, etc.
    retry_count INTEGER DEFAULT 0,
    resolved INTEGER DEFAULT 0, -- Boolean
    resolved_at TIMESTAMP,
    resolved_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

-- Audit Log table: For tracking all significant actions
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT DEFAULT 'system',
    action TEXT NOT NULL, -- 'create', 'update', 'delete', 'rename', 'export', etc.
    table_name TEXT, -- Which table was affected
    record_id INTEGER, -- Which record was affected
    old_values TEXT, -- JSON representation of old values
    new_values TEXT, -- JSON representation of new values
    ip_address TEXT DEFAULT '127.0.0.1',
    user_agent TEXT DEFAULT 'kilo-agent',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==================== INDEXES ====================

-- Documents table indexes
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_original_filename ON documents(original_filename);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);

-- OCR Results indexes
CREATE INDEX IF NOT EXISTS idx_ocr_results_document_id ON ocr_results(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_page_number ON ocr_results(page_number);

-- Extracted Data indexes
CREATE INDEX IF NOT EXISTS idx_extracted_data_document_id ON extracted_data(document_id);
CREATE INDEX IF NOT EXISTS idx_extracted_data_document_type ON extracted_data(document_type);
CREATE INDEX IF NOT EXISTS idx_extracted_data_lastname ON extracted_data(lastname);
CREATE INDEX IF NOT EXISTS idx_extracted_data_date ON extracted_data(date_of_notarization);

-- Rename Operations indexes
CREATE INDEX IF NOT EXISTS idx_rename_operations_document_id ON rename_operations(document_id);
CREATE INDEX IF NOT EXISTS idx_rename_operations_new_filename ON rename_operations(new_filename);

-- Processing Logs indexes
CREATE INDEX IF NOT EXISTS idx_processing_logs_document_id ON processing_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_logs_agent_name ON processing_logs(agent_name);
CREATE INDEX IF NOT EXISTS idx_processing_logs_created_at ON processing_logs(created_at);

-- Error Logs indexes
CREATE INDEX IF NOT EXISTS idx_error_logs_document_id ON error_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_resolved ON error_logs(resolved);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON error_logs(created_at);

-- Audit Log indexes
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);

-- ==================== VIEWS ====================

-- View for document processing status
CREATE VIEW IF NOT EXISTS vw_document_status AS
SELECT 
    d.id,
    d.original_filename,
    d.status,
    d.created_at,
    d.updated_at,
    CASE WHEN ocr.id IS NOT NULL THEN 1 ELSE 0 END AS has_ocr,
    CASE WHEN ed.id IS NOT NULL THEN 1 ELSE 0 END AS has_extracted_data,
    CASE WHEN ro.id IS NOT NULL THEN 1 ELSE 0 END AS has_rename,
    COUNT(DISTINCT ocr.page_number) AS pages_processed,
    COUNT(DISTINCT el.id) AS error_count
FROM documents d
LEFT JOIN ocr_results ocr ON d.id = ocr.document_id
LEFT JOIN extracted_data ed ON d.id = ed.document_id
LEFT JOIN rename_operations ro ON d.id = ro.document_id
LEFT JOIN error_logs el ON d.id = el.document_id AND el.resolved = 0
GROUP BY d.id, d.original_filename, d.status, d.created_at, d.updated_at;

-- View for extraction statistics
CREATE VIEW IF NOT EXISTS vw_extraction_stats AS
SELECT 
    document_type,
    COUNT(*) AS total_documents,
    SUM(CASE WHEN date_of_notarization IS NOT NULL THEN 1 ELSE 0 END) AS has_date,
    SUM(CASE WHEN document_number IS NOT NULL THEN 1 ELSE 0 END) AS has_doc_no,
    SUM(CASE WHEN lastname IS NOT NULL THEN 1 ELSE 0 END) AS has_lastname,
    ROUND(AVG(confidence_score), 2) AS avg_confidence
FROM extracted_data
GROUP BY document_type;

-- View for processing timeline
CREATE VIEW IF NOT EXISTS vw_processing_timeline AS
SELECT 
    d.original_filename,
    MIN(CASE WHEN pl.agent_name = 'ocr' AND pl.operation = 'start' THEN pl.created_at END) AS ocr_start,
    MIN(CASE WHEN pl.agent_name = 'ocr' AND pl.operation = 'complete' THEN pl.created_at END) AS ocr_complete,
    MIN(CASE WHEN pl.agent_name = 'parse' AND pl.operation = 'start' THEN pl.created_at END) AS parse_start,
    MIN(CASE WHEN pl.agent_name = 'parse' AND pl.operation = 'complete' THEN pl.created_at END) AS parse_complete,
    MIN(CASE WHEN pl.agent_name = 'rename' AND pl.operation = 'start' THEN pl.created_at END) AS rename_start,
    MIN(CASE WHEN pl.agent_name = 'rename' AND pl.operation = 'complete' THEN pl.created_at END) AS rename_complete
FROM documents d
LEFT JOIN processing_logs pl ON d.id = pl.document_id
GROUP BY d.id, d.original_filename;

-- ==================== TRIGGERS ====================

-- Trigger to update documents.updated_at on any related table change
CREATE TRIGGER IF NOT EXISTS trg_update_document_timestamp
AFTER UPDATE ON documents
BEGIN
    UPDATE documents SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Trigger for audit logging on extracted_data changes
CREATE TRIGGER IF NOT EXISTS trg_audit_extracted_data_update
AFTER UPDATE ON extracted_data
BEGIN
    INSERT INTO audit_log (action, table_name, record_id, old_values, new_values)
    VALUES ('update', 'extracted_data', NEW.id, 
            json_object('date_of_notarization', OLD.date_of_notarization,
                       'document_number', OLD.document_number,
                       'document_type', OLD.document_type,
                       'lastname', OLD.lastname),
            json_object('date_of_notarization', NEW.date_of_notarization,
                       'document_number', NEW.document_number,
                       'document_type', NEW.document_type,
                       'lastname', NEW.lastname));
END;

-- Trigger for audit logging on rename operations
CREATE TRIGGER IF NOT EXISTS trg_audit_rename_create
AFTER INSERT ON rename_operations
BEGIN
    INSERT INTO audit_log (action, table_name, record_id, new_values)
    VALUES ('rename', 'rename_operations', NEW.id,
            json_object('document_id', NEW.document_id,
                       'original_filename', NEW.original_filename,
                       'new_filename', NEW.new_filename,
                       'success', NEW.success));
END;