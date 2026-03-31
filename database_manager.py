#!/usr/bin/env python3
"""
Database Manager for Notary Processing Center.
Provides CRUD operations and database administration functions.
All agents should delegate to this module for database operations.
"""
import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database operations for the notary processing system."""
    
    def __init__(self, db_path: str = "notary_processing.db"):
        self.db_path = Path(db_path)
        self.conn = None
        self.cursor = None
        
    def connect(self) -> sqlite3.Connection:
        """Establish database connection."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            self.cursor = self.conn.cursor()
            # Enable foreign keys
            self.cursor.execute("PRAGMA foreign_keys = ON")
            logger.info(f"Connected to database: {self.db_path}")
            return self.conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def initialize_database(self, schema_file: str = "database_schema.sqlite.sql"):
        """Initialize database with schema if not exists."""
        try:
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            
            self.connect()
            self.cursor.executescript(schema_sql)
            self.conn.commit()
            logger.info(f"Database initialized from {schema_file}")
            return True
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
        finally:
            self.close()
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    # ==================== DOCUMENT OPERATIONS ====================
    
    def add_document(self, original_filename: str, file_path: str = None, 
                     file_size_bytes: int = None, file_hash: str = None,
                     page_count: int = None, status: str = 'pending') -> int:
        """Add a new document to the database."""
        with self:
            try:
                self.cursor.execute("""
                    INSERT INTO documents 
                    (original_filename, file_path, file_size_bytes, file_hash, page_count, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (original_filename, file_path, file_size_bytes, file_hash, page_count, status))
                doc_id = self.cursor.lastrowid
                self.conn.commit()
                
                # Log the operation
                self.add_processing_log(doc_id, 'database', 'create', 
                                       f"Document added: {original_filename}")
                logger.info(f"Added document {original_filename} with ID {doc_id}")
                return doc_id
            except sqlite3.IntegrityError:
                # Document already exists, return existing ID
                self.cursor.execute("SELECT id FROM documents WHERE original_filename = ?", 
                                  (original_filename,))
                row = self.cursor.fetchone()
                if row:
                    logger.info(f"Document {original_filename} already exists with ID {row['id']}")
                    return row['id']
                raise
    
    def update_document_status(self, document_id: int, status: str) -> bool:
        """Update document status."""
        with self:
            try:
                self.cursor.execute("""
                    UPDATE documents SET status = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (status, document_id))
                self.conn.commit()
                
                self.add_processing_log(document_id, 'database', 'update', 
                                       f"Status updated to {status}")
                logger.debug(f"Updated document {document_id} status to {status}")
                return True
            except sqlite3.Error as e:
                logger.error(f"Failed to update document status: {e}")
                return False
    
    def get_document(self, document_id: int = None, original_filename: str = None) -> Optional[Dict]:
        """Get document by ID or filename."""
        with self:
            if document_id:
                self.cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
            elif original_filename:
                self.cursor.execute("SELECT * FROM documents WHERE original_filename = ?", 
                                  (original_filename,))
            else:
                return None
            
            row = self.cursor.fetchone()
            return dict(row) if row else None
    
    def get_documents_by_status(self, status: str) -> List[Dict]:
        """Get all documents with given status."""
        with self:
            self.cursor.execute("SELECT * FROM documents WHERE status = ? ORDER BY created_at", 
                              (status,))
            return [dict(row) for row in self.cursor.fetchall()]
    
    # ==================== OCR OPERATIONS ====================
    
    def add_ocr_result(self, document_id: int, page_number: int, ocr_text: str,
                       ocr_confidence: float = None, ocr_parameters: Dict = None,
                       processing_time_ms: int = None) -> int:
        """Add OCR result for a document page."""
        with self:
            try:
                params_json = json.dumps(ocr_parameters) if ocr_parameters else None
                self.cursor.execute("""
                    INSERT INTO ocr_results 
                    (document_id, page_number, ocr_text, ocr_confidence, ocr_parameters, processing_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (document_id, page_number, ocr_text, ocr_confidence, params_json, processing_time_ms))
                ocr_id = self.cursor.lastrowid
                self.conn.commit()
                
                self.add_processing_log(document_id, 'ocr', 'complete', 
                                       f"OCR completed for page {page_number}")
                logger.debug(f"Added OCR result for document {document_id}, page {page_number}")
                return ocr_id
            except sqlite3.IntegrityError:
                # Update existing OCR result
                self.cursor.execute("""
                    UPDATE ocr_results 
                    SET ocr_text = ?, ocr_confidence = ?, ocr_parameters = ?, processing_time_ms = ?
                    WHERE document_id = ? AND page_number = ?
                """, (ocr_text, ocr_confidence, params_json, processing_time_ms, document_id, page_number))
                self.conn.commit()
                logger.debug(f"Updated OCR result for document {document_id}, page {page_number}")
                return 0  # Return 0 to indicate update rather than insert
    
    def get_ocr_results(self, document_id: int) -> List[Dict]:
        """Get all OCR results for a document."""
        with self:
            self.cursor.execute("""
                SELECT * FROM ocr_results 
                WHERE document_id = ? 
                ORDER BY page_number
            """, (document_id,))
            return [dict(row) for row in self.cursor.fetchall()]
    
    def get_full_ocr_text(self, document_id: int) -> str:
        """Get concatenated OCR text for all pages of a document."""
        with self:
            self.cursor.execute("""
                SELECT ocr_text FROM ocr_results 
                WHERE document_id = ? 
                ORDER BY page_number
            """, (document_id,))
            results = self.cursor.fetchall()
            return "\n\n--- Page Break ---\n\n".join([row['ocr_text'] for row in results if row['ocr_text']])
    
    # ==================== EXTRACTION OPERATIONS ====================
    
    def add_extracted_data(self, document_id: int, date_of_notarization: str = None,
                          document_number: str = None, document_type: str = None,
                          page_number: str = None, book_number: str = None,
                          series_year: str = None, lastname: str = None,
                          is_waiver: bool = False, is_corporate: bool = False,
                          confidence_score: float = None) -> int:
        """Add extracted data for a document."""
        with self:
            try:
                # Convert booleans to integers for SQLite
                is_waiver_int = 1 if is_waiver else 0
                is_corporate_int = 1 if is_corporate else 0
                
                self.cursor.execute("""
                    INSERT INTO extracted_data 
                    (document_id, date_of_notarization, document_number, document_type, 
                     page_number, book_number, series_year, lastname, is_waiver, is_corporate, confidence_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (document_id, date_of_notarization, document_number, document_type,
                      page_number, book_number, series_year, lastname, 
                      is_waiver_int, is_corporate_int, confidence_score))
                ext_id = self.cursor.lastrowid
                self.conn.commit()
                
                # Update document status
                self.update_document_status(document_id, 'processed')
                
                self.add_processing_log(document_id, 'parse', 'complete', 
                                       f"Extracted data: {document_type}")
                logger.info(f"Added extracted data for document {document_id}: {document_type}")
                return ext_id
            except sqlite3.IntegrityError:
                # Update existing extracted data
                self.cursor.execute("""
                    UPDATE extracted_data 
                    SET date_of_notarization = ?, document_number = ?, document_type = ?,
                        page_number = ?, book_number = ?, series_year = ?, lastname = ?,
                        is_waiver = ?, is_corporate = ?, confidence_score = ?,
                        extraction_timestamp = CURRENT_TIMESTAMP
                    WHERE document_id = ?
                """, (date_of_notarization, document_number, document_type,
                      page_number, book_number, series_year, lastname,
                      is_waiver_int, is_corporate_int, confidence_score, document_id))
                self.conn.commit()
                logger.info(f"Updated extracted data for document {document_id}")
                return 0
    
    def get_extracted_data(self, document_id: int) -> Optional[Dict]:
        """Get extracted data for a document."""
        with self:
            self.cursor.execute("SELECT * FROM extracted_data WHERE document_id = ?", 
                              (document_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== RENAME OPERATIONS ====================
    
    def add_rename_operation(self, document_id: int, original_filename: str, 
                            new_filename: str, rename_template: str = None,
                            destination_path: str = None, success: bool = True,
                            error_message: str = None) -> int:
        """Record a file rename operation."""
        with self:
            try:
                success_int = 1 if success else 0
                self.cursor.execute("""
                    INSERT INTO rename_operations 
                    (document_id, original_filename, new_filename, rename_template, 
                     destination_path, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (document_id, original_filename, new_filename, rename_template,
                      destination_path, success_int, error_message))
                rename_id = self.cursor.lastrowid
                self.conn.commit()
                
                # Update document status
                if success:
                    self.update_document_status(document_id, 'processed')
                
                self.add_processing_log(document_id, 'rename', 'complete' if success else 'error',
                                       f"Renamed: {original_filename} -> {new_filename}")
                logger.info(f"Recorded rename operation for document {document_id}")
                return rename_id
            except sqlite3.Error as e:
                logger.error(f"Failed to record rename operation: {e}")
                return -1
    
    def get_rename_history(self, document_id: int = None) -> List[Dict]:
        """Get rename history for a document or all documents."""
        with self:
            if document_id:
                self.cursor.execute("""
                    SELECT * FROM rename_operations 
                    WHERE document_id = ? 
                    ORDER BY rename_timestamp DESC
                """, (document_id,))
            else:
                self.cursor.execute("""
                    SELECT * FROM rename_operations 
                    ORDER BY rename_timestamp DESC
                """)
            return [dict(row) for row in self.cursor.fetchall()]
    
    # ==================== LOGGING OPERATIONS ====================
    
    def add_processing_log(self, document_id: int, agent_name: str, operation: str,
                          log_message: str = None, parameters: Dict = None,
                          processing_time_ms: int = None) -> int:
        """Add a processing log entry."""
        with self:
            try:
                params_json = json.dumps(parameters) if parameters else None
                self.cursor.execute("""
                    INSERT INTO processing_logs 
                    (document_id, agent_name, operation, log_message, parameters, processing_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (document_id, agent_name, operation, log_message, params_json, processing_time_ms))
                log_id = self.cursor.lastrowid
                self.conn.commit()
                return log_id
            except sqlite3.Error as e:
                logger.error(f"Failed to add processing log: {e}")
                return -1
    
    def add_error_log(self, document_id: int = None, agent_name: str = None,
                     error_type: str = None, error_message: str = None,
                     error_details: Dict = None) -> int:
        """Add an error log entry."""
        with self:
            try:
                details_json = json.dumps(error_details) if error_details else None
                self.cursor.execute("""
                    INSERT INTO error_logs 
                    (document_id, agent_name, error_type, error_message, error_details)
                    VALUES (?, ?, ?, ?, ?)
                """, (document_id, agent_name, error_type, error_message, details_json))
                error_id = self.cursor.lastrowid
                self.conn.commit()
                logger.error(f"Error logged: {error_type} - {error_message}")
                return error_id
            except sqlite3.Error as e:
                logger.error(f"Failed to add error log: {e}")
                return -1
    
    # ==================== UTILITY OPERATIONS ====================
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate file hash: {e}")
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self:
            stats = {}
            
            # Document counts by status
            self.cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM documents 
                GROUP BY status
            """)
            stats['documents_by_status'] = {row['status']: row['count'] for row in self.cursor.fetchall()}
            
            # Total documents
            self.cursor.execute("SELECT COUNT(*) as total FROM documents")
            stats['total_documents'] = self.cursor.fetchone()['total']
            
            # Documents with OCR
            self.cursor.execute("""
                SELECT COUNT(DISTINCT document_id) as count FROM ocr_results
            """)
            stats['documents_with_ocr'] = self.cursor.fetchone()['count']
            
            # Documents with extracted data
            self.cursor.execute("SELECT COUNT(*) as count FROM extracted_data")
            stats['documents_extracted'] = self.cursor.fetchone()['count']
            
            # Documents renamed
            self.cursor.execute("""
                SELECT COUNT(DISTINCT document_id) as count FROM rename_operations WHERE success = 1
            """)
            stats['documents_renamed'] = self.cursor.fetchone()['count']
            
            # Recent errors
            self.cursor.execute("""
                SELECT COUNT(*) as count FROM error_logs 
                WHERE resolved = 0 AND created_at > datetime('now', '-7 days')
            """)
            stats['recent_unresolved_errors'] = self.cursor.fetchone()['count']
            
            return stats
    
    def backup_database(self, backup_path: str = None) -> bool:
        """Create a backup of the database."""
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"notary_processing_backup_{timestamp}.db"
        
        try:
            with self:
                # Use SQLite's backup API
                backup_conn = sqlite3.connect(backup_path)
                self.conn.backup(backup_conn)
                backup_conn.close()
                logger.info(f"Database backed up to {backup_path}")
                return True
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return False
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute a custom SQL query (read-only)."""
        with self:
            try:
                self.cursor.execute(query, params)
                return [dict(row) for row in self.cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error(f"Query execution failed: {e}")
                raise

# Singleton instance for easy import
db_manager = DatabaseManager()

def init_database():
    """Initialize database (convenience function)."""
    manager = DatabaseManager()
    return manager.initialize_database()

if __name__ == "__main__":
    # Test the database manager
    print("Testing Database Manager...")
    
    # Initialize database
    manager = DatabaseManager()
    if manager.initialize_database():
        print("Database initialized successfully")
        
        # Get statistics
        stats = manager.get_statistics()
        print(f"Statistics: {stats}")
        
        manager.close()
        print("Test completed")