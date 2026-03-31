#!/usr/bin/env python3
"""
Validation Dashboard for Notary Processing Center.
Web-based interface for reviewing and correcting OCR-extracted data.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'notary-validation-secret-key-change-in-production'
DATABASE_PATH = 'notary_processing.db'

def get_db_connection():
    """Get SQLite database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_documents_needing_validation(limit=50, confidence_threshold=0.8):
    """Retrieve documents that need validation (low confidence or not validated)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT 
        d.id AS doc_id,
        d.original_filename,
        d.status,
        d.created_at AS doc_created,
        ed.id AS extraction_id,
        ed.date_of_notarization,
        ed.document_number,
        ed.document_type,
        ed.document_category,
        ed.page_number,
        ed.book_number,
        ed.series_year,
        ed.lastname,
        ed.is_waiver,
        ed.is_corporate,
        ed.extraction_method,
        ed.confidence_score,
        ed.validated,
        ed.validated_at,
        ed.validated_by,
        ed.correction_notes,
        (SELECT COUNT(*) FROM ocr_results ocr WHERE ocr.document_id = d.id) AS page_count,
        (SELECT COUNT(*) FROM error_logs el WHERE el.document_id = d.id AND el.resolved = 0) AS error_count
    FROM documents d
    LEFT JOIN extracted_data ed ON d.id = ed.document_id
    WHERE ed.id IS NOT NULL 
        AND (ed.validated = 0 OR ed.confidence_score < ?)
    ORDER BY ed.confidence_score ASC, d.created_at DESC
    LIMIT ?
    """
    
    cursor.execute(query, (confidence_threshold, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_document_details(doc_id):
    """Get detailed information for a specific document."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get document and extracted data
    query = """
    SELECT 
        d.*,
        ed.*,
        (SELECT GROUP_CONCAT(ocr_text, '\n--- PAGE BREAK ---\n') 
         FROM ocr_results ocr 
         WHERE ocr.document_id = d.id 
         ORDER BY ocr.page_number) AS full_ocr_text
    FROM documents d
    LEFT JOIN extracted_data ed ON d.id = ed.document_id
    WHERE d.id = ?
    """
    
    cursor.execute(query, (doc_id,))
    doc = cursor.fetchone()
    
    if not doc:
        conn.close()
        return None
    
    # Get OCR results per page
    cursor.execute("""
        SELECT page_number, ocr_text, ocr_confidence, processing_time_ms
        FROM ocr_results
        WHERE document_id = ?
        ORDER BY page_number
    """, (doc_id,))
    ocr_pages = cursor.fetchall()
    
    # Get rename operations if any
    cursor.execute("""
        SELECT new_filename, rename_timestamp, success, error_message
        FROM rename_operations
        WHERE document_id = ?
        ORDER BY rename_timestamp DESC
    """, (doc_id,))
    rename_ops = cursor.fetchall()
    
    # Get error logs
    cursor.execute("""
        SELECT error_type, error_message, created_at, resolved
        FROM error_logs
        WHERE document_id = ?
        ORDER BY created_at DESC
    """, (doc_id,))
    errors = cursor.fetchall()
    
    conn.close()
    
    return {
        'document': dict(doc),
        'ocr_pages': [dict(page) for page in ocr_pages],
        'rename_ops': [dict(op) for op in rename_ops],
        'errors': [dict(err) for err in errors]
    }

def update_extracted_data(extraction_id, updates, validated_by='dashboard'):
    """Update extracted data with corrections."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current values for audit log (trigger will handle)
    cursor.execute("SELECT * FROM extracted_data WHERE id = ?", (extraction_id,))
    current = cursor.fetchone()
    
    if not current:
        conn.close()
        return False
    
    # Build update query dynamically
    set_clauses = []
    params = []
    
    field_map = {
        'date_of_notarization': 'date_of_notarization',
        'document_number': 'document_number',
        'document_type': 'document_type',
        'document_category': 'document_category',
        'page_number': 'page_number',
        'book_number': 'book_number',
        'series_year': 'series_year',
        'lastname': 'lastname',
        'is_waiver': 'is_waiver',
        'is_corporate': 'is_corporate',
        'correction_notes': 'correction_notes'
    }
    
    for field, db_field in field_map.items():
        if field in updates:
            set_clauses.append(f"{db_field} = ?")
            params.append(updates[field])
    
    # Always mark as validated when updating
    set_clauses.append("validated = 1")
    set_clauses.append("validated_at = CURRENT_TIMESTAMP")
    set_clauses.append("validated_by = ?")
    params.append(validated_by)
    
    # Add extraction_id to params
    params.append(extraction_id)
    
    query = f"UPDATE extracted_data SET {', '.join(set_clauses)} WHERE id = ?"
    
    try:
        cursor.execute(query, params)
        conn.commit()
        success = cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        success = False
    
    conn.close()
    return success

def get_validation_stats():
    """Get statistics for validation dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    # Total documents with extracted data
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN validated = 1 THEN 1 ELSE 0 END) as validated,
            SUM(CASE WHEN validated = 0 THEN 1 ELSE 0 END) as pending,
            AVG(confidence_score) as avg_confidence
        FROM extracted_data
    """)
    stats['extraction'] = dict(cursor.fetchone())
    
    # By document type
    cursor.execute("""
        SELECT 
            document_type,
            COUNT(*) as count,
            AVG(confidence_score) as avg_confidence,
            SUM(CASE WHEN validated = 1 THEN 1 ELSE 0 END) as validated
        FROM extracted_data
        WHERE document_type IS NOT NULL
        GROUP BY document_type
        ORDER BY count DESC
    """)
    stats['by_type'] = [dict(row) for row in cursor.fetchall()]
    
    # Recent validation activity
    cursor.execute("""
        SELECT 
            validated_by,
            COUNT(*) as count,
            MAX(validated_at) as last_validated
        FROM extracted_data
        WHERE validated = 1 AND validated_by IS NOT NULL
        GROUP BY validated_by
        ORDER BY count DESC
    """)
    stats['validators'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return stats

# Flask Routes

@app.route('/')
def index():
    """Main dashboard page."""
    stats = get_validation_stats()
    documents = get_documents_needing_validation(limit=20)
    return render_template('index.html', stats=stats, documents=documents)

@app.route('/document/<int:doc_id>')
def document_detail(doc_id):
    """Document detail page for validation."""
    doc_details = get_document_details(doc_id)
    if not doc_details:
        flash('Document not found.', 'error')
        return redirect(url_for('index'))
    
    return render_template('document_detail.html', doc=doc_details)

@app.route('/api/validate/<int:extraction_id>', methods=['POST'])
def api_validate(extraction_id):
    """API endpoint to validate/correct extracted data."""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    updates = data.get('updates', {})
    
    # Validate updates
    allowed_fields = {
        'date_of_notarization', 'document_number', 'document_type',
        'document_category', 'page_number', 'book_number', 'series_year',
        'lastname', 'is_waiver', 'is_corporate', 'correction_notes'
    }
    
    for field in updates:
        if field not in allowed_fields:
            return jsonify({'success': False, 'error': f'Invalid field: {field}'}), 400
    
    # Convert boolean fields
    if 'is_waiver' in updates:
        updates['is_waiver'] = 1 if updates['is_waiver'] else 0
    if 'is_corporate' in updates:
        updates['is_corporate'] = 1 if updates['is_corporate'] else 0
    
    success = update_extracted_data(extraction_id, updates, validated_by='web_dashboard')
    
    if success:
        return jsonify({'success': True, 'message': 'Validation saved.'})
    else:
        return jsonify({'success': False, 'error': 'Failed to save validation.'}), 500

@app.route('/api/documents/needing_validation')
def api_documents_needing_validation():
    """API endpoint for documents needing validation."""
    limit = request.args.get('limit', 50, type=int)
    confidence = request.args.get('confidence_threshold', 0.8, type=float)
    
    documents = get_documents_needing_validation(limit=limit, confidence_threshold=confidence)
    return jsonify({'documents': documents})

@app.route('/api/stats')
def api_stats():
    """API endpoint for validation statistics."""
    stats = get_validation_stats()
    return jsonify(stats)

# HTML Templates (inline for simplicity)
@app.route('/templates')
def templates():
    """Serve template definitions (for debugging)."""
    return "Templates are inline in this application."

# Create inline templates using render_template_string
def render_template(template_name, **context):
    """Custom render_template that uses inline templates."""
    templates = {
        'index.html': '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Notary Validation Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css" rel="stylesheet">
    <style>
        body { padding-top: 20px; background-color: #f8f9fa; }
        .stat-card { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .confidence-bar { height: 10px; background: #e9ecef; border-radius: 5px; overflow: hidden; }
        .confidence-fill { height: 100%; background: linear-gradient(90deg, #dc3545, #ffc107, #28a745); }
        .low-confidence { color: #dc3545; font-weight: bold; }
        .medium-confidence { color: #ffc107; font-weight: bold; }
        .high-confidence { color: #28a745; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">📋 Notary Validation Dashboard</h1>
        
        <!-- Stats Row -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <h3>{{ stats.extraction.total }}</h3>
                    <p class="text-muted">Total Documents</p>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <h3 class="text-success">{{ stats.extraction.validated }}</h3>
                    <p class="text-muted">Validated</p>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <h3 class="text-warning">{{ stats.extraction.pending }}</h3>
                    <p class="text-muted">Pending Validation</p>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <h3>{{ "%.2f"|format(stats.extraction.avg_confidence) }}</h3>
                    <p class="text-muted">Avg Confidence</p>
                </div>
            </div>
        </div>
        
        <!-- Documents Needing Validation -->
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">📄 Documents Needing Validation</h5>
            </div>
            <div class="card-body">
                {% if documents %}
                <div class="table-responsive">
                    <table class="table table-hover" id="documentsTable">
                        <thead>
                            <tr>
                                <th>Filename</th>
                                <th>Document Type</th>
                                <th>Last Name</th>
                                <th>Date</th>
                                <th>Confidence</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for doc in documents %}
                            <tr>
                                <td>{{ doc.original_filename }}</td>
                                <td>{{ doc.document_type or 'Unknown' }}</td>
                                <td>{{ doc.lastname or 'Not found' }}</td>
                                <td>{{ doc.date_of_notarization or 'Not found' }}</td>
                                <td>
                                    {% set confidence = doc.confidence_score or 0 %}
                                    <div class="confidence-bar">
                                        <div class="confidence-fill" style="width: {{ confidence * 100 }}%"></div>
                                    </div>
                                    <small>
                                        {% if confidence < 0.5 %}
                                            <span class="low-confidence">{{ "%.1f"|format(confidence * 100) }}%</span>
                                        {% elif confidence < 0.8 %}
                                            <span class="medium-confidence">{{ "%.1f"|format(confidence * 100) }}%</span>
                                        {% else %}
                                            <span class="high-confidence">{{ "%.1f"|format(confidence * 100) }}%</span>
                                        {% endif %}
                                    </small>
                                </td>
                                <td>
                                    {% if doc.validated %}
                                        <span class="badge bg-success">Validated</span>
                                    {% else %}
                                        <span class="badge bg-warning">Pending</span>
                                    {% endif %}
                                </td>
                                <td>
                                    <a href="/document/{{ doc.doc_id }}" class="btn btn-sm btn-primary">Validate</a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <div class="alert alert-success">
                    <i class="bi bi-check-circle"></i> All documents have been validated!
                </div>
                {% endif %}
            </div>
        </div>
        
        <!-- Document Type Breakdown -->
        <div class="card mt-4">
            <div class="card-header">
                <h5 class="mb-0">📊 Document Type Statistics</h5>
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Document Type</th>
                                <th>Count</th>
                                <th>Avg Confidence</th>
                                <th>Validated</th>
                                <th>Pending</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for type_stat in stats.by_type %}
                            <tr>
                                <td>{{ type_stat.document_type }}</td>
                                <td>{{ type_stat.count }}</td>
                                <td>{{ "%.2f"|format(type_stat.avg_confidence) }}</td>
                                <td>{{ type_stat.validated }}</td>
                                <td>{{ type_stat.count - type_stat.validated }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/dataTables.bootstrap5.min.js"></script>
    <script>
        $(document).ready(function() {
            $('#documentsTable').DataTable({
                pageLength: 10,
                order: [[4, 'asc']] // Sort by confidence (lowest first)
            });
        });
    </script>
</body>
</html>
        ''',
        'document_detail.html': '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Validate Document - Notary Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        body { padding-top: 20px; background-color: #f8f9fa; }
        .card { margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .field-group { margin-bottom: 15px; }
        .ocr-preview { max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 0.9em; background: #f8f9fa; padding: 10px; border-radius: 5px; }
        .page-break { border-top: 1px dashed #ccc; margin: 10px 0; padding-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h1><i class="bi bi-file-earmark-text"></i> Validate Document</h1>
            <a href="/" class="btn btn-outline-secondary">← Back to Dashboard</a>
        </div>
        
        {% set doc = doc.document %}
        
        <!-- Document Info -->
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">📄 Document Information</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Filename:</strong> {{ doc.original_filename }}</p>
                        <p><strong>Status:</strong> 
                            <span class="badge bg-{{ 'success' if doc.validated else 'warning' }}">
                                {{ 'Validated' if doc.validated else 'Pending Validation' }}
                            </span>
                        </p>
                        <p><strong>Confidence Score:</strong> 
                            <span class="badge bg-{{ 'success' if doc.confidence_score >= 0.8 else 'warning' if doc.confidence_score >= 0.5 else 'danger' }}">
                                {{ "%.1f"|format(doc.confidence_score * 100) }}%
                            </span>
                        </p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>Extraction Method:</strong> {{ doc.extraction_method or 'regex' }}</p>
                        <p><strong>Extracted On:</strong> {{ doc.extraction_timestamp }}</p>
                        {% if doc.validated %}
                        <p><strong>Validated By:</strong> {{ doc.validated_by or 'System' }}</p>
                        <p><strong>Validated On:</strong> {{ doc.validated_at }}</p>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Validation Form -->
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">✏️ Edit & Validate Extracted Data</h5>
            </div>
            <div class="card-body">
                <form id="validationForm">
                    <input type="hidden" id="extractionId" value="{{ doc.id }}">
                    
                    <div class="row">
                        <div class="col-md-6">
                            <div class="field-group">
                                <label class="form-label"><strong>Date of Notarization</strong></label>
                                <input type="text" class="form-control" id="date_of_notarization" 
                                       value="{{ doc.date_of_notarization or '' }}">
                                <small class="form-text text-muted">Format: DD MMM YYYY (e.g., 02 FEB 2026)</small>
                            </div>
                            
                            <div class="field-group">
                                <label class="form-label"><strong>Document Number</strong></label>
                                <input type="text" class="form-control" id="document_number" 
                                       value="{{ doc.document_number or '' }}">
                            </div>
                            
                            <div class="field-group">
                                <label class="form-label"><strong>Document Type</strong></label>
                                <input type="text" class="form-control" id="document_type" 
                                       value="{{ doc.document_type or '' }}">
                            </div>
                            
                            <div class="field-group">
                                <label class="form-label"><strong>Document Category</strong></label>
                                <input type="text" class="form-control" id="document_category" 
                                       value="{{ doc.document_category or '' }}">
                            </div>
                        </div>
                        
                        <div class="col-md-6">
                            <div class="field-group">
                                <label class="form-label"><strong>Last Name</strong></label>
                                <input type="text" class="form-control" id="lastname" 
                                       value="{{ doc.lastname or '' }}">
                            </div>
                            
                            <div class="field-group">
                                <label class="form-label"><strong>Page Number (Register)</strong></label>
                                <input type="text" class="form-control" id="page_number" 
                                       value="{{ doc.page_number or '' }}">
                            </div>
                            
                            <div class="field-group">
                                <label class="form-label"><strong>Book Number</strong></label>
                                <input type="text" class="form-control" id="book_number" 
                                       value="{{ doc.book_number or '' }}">
                            </div>
                            
                            <div class="field-group">
                                <label class="form-label"><strong>Series Year</strong></label>
                                <input type="text" class="form-control" id="series_year" 
                                       value="{{ doc.series_year or '' }}">
                            </div>
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-6">
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="is_waiver" 
                                       {{ 'checked' if doc.is_waiver else '' }}>
                                <label class="form-check-label" for="is_waiver">
                                    <strong>Is Waiver Document</strong>
                                </label>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="is_corporate" 
                                       {{ 'checked' if doc.is_corporate else '' }}>
                                <label class="form-check-label" for="is_corporate">
                                    <strong>Is Corporate Document</strong>
                                </label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="field-group">
                        <label class="form-label"><strong>Correction Notes</strong></label>
                        <textarea class="form-control" id="correction_notes" rows="3">{{ doc.correction_notes or '' }}</textarea>
                        <small class="form-text text-muted">Optional notes about corrections made.</small>
                    </div>
                    
                    <div class="d-grid gap-2 d-md-flex justify-content-md-end mt-4">
                        <button type="button" class="btn btn-secondary" onclick="resetForm()">Reset</button>
                        <button type="button" class="btn btn-success" onclick="saveValidation()">
                            <i class="bi bi-check-circle"></i> Save & Validate
                        </button>
                    </div>
                </form>
                
                <div id="validationMessage" class="mt-3" style="display: none;"></div>
            </div>
        </div>
        
        <!-- OCR Preview -->
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">🔍 OCR Text Preview</h5>
            </div>
            <div class="card-body">
                <div class="ocr-preview">
                    {% for page in doc.ocr_pages %}
                        <div class="page-break">
                            <small class="text-muted">Page {{ page.page_number }}</small>
                            <pre style="white-space: pre-wrap; margin-top: 5px;">{{ page.ocr_text }}</pre>
                        </div>
                    {% else %}
                        <p class="text-muted">No OCR text available.</p>
                    {% endfor %}
                </div>
            </div>
        </div>
        
        <!-- Rename History -->
        {% if doc.rename_ops %}
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">📁 Rename History</h5>
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>New Filename</th>
                                <th>Timestamp</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for op in doc.rename_ops %}
                            <tr>
                                <td>{{ op.new_filename }}</td>
                                <td>{{ op.rename_timestamp }}</td>
                                <td>
                                    {% if op.success %}
                                        <span class="badge bg-success">Success</span>
                                    {% else %}
                                        <span class="badge bg-danger">Failed</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        {% endif %}
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function saveValidation() {
            const extractionId = document.getElementById('extractionId').value;
            const updates = {
                date_of_notarization: document.getElementById('date_of_notarization').value,
                document_number: document.getElementById('document_number').value,
                document_type: document.getElementById('document_type').value,
                document_category: document.getElementById('document_category').value,
                page_number: document.getElementById('page_number').value,
                book_number: document.getElementById('book_number').value,
                series_year: document.getElementById('series_year').value,
                lastname: document.getElementById('lastname').value,
                is_waiver: document.getElementById('is_waiver').checked,
                is_corporate: document.getElementById('is_corporate').checked,
                correction_notes: document.getElementById('correction_notes').value
            };
            
            fetch(`/api/validate/${extractionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ updates: updates })
            })
            .then(response => response.json())
            .then(data => {
                const messageDiv = document.getElementById('validationMessage');
                if (data.success) {
                    messageDiv.innerHTML = `
                        <div class="alert alert-success alert-dismissible fade show" role="alert">
                            <i class="bi bi-check-circle"></i> Validation saved successfully!
                            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        </div>
                    `;
                    // Refresh page after 2 seconds to show updated status
                    setTimeout(() => window.location.reload(), 2000);
                } else {
                    messageDiv.innerHTML = `
                        <div class="alert alert-danger alert-dismissible fade show" role="alert">
                            <i class="bi bi-exclamation-triangle"></i> Error: ${data.error || 'Failed to save validation.'}
                            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                        </div>
                    `;
                }
                messageDiv.style.display = 'block';
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('validationMessage').innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle"></i> Network error. Please try again.
                    </div>
                `;
                document.getElementById('validationMessage').style.display = 'block';
            });
        }
        
        function resetForm() {
            if (confirm('Reset all changes?')) {
                document.getElementById('validationForm').reset();
            }
        }
    </script>
</body>
</html>
        '''
    }
    
    if template_name not in templates:
        return f"Template {template_name} not found.", 404
    
    from flask import render_template_string
    return render_template_string(templates[template_name], **context)

if __name__ == '__main__':
    print("Starting Validation Dashboard...")
    print("Open http://localhost:5001 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5001)