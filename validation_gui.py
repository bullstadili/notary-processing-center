#!/usr/bin/env python3
"""
Simple Tkinter GUI for validating OCR-extracted data.
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sqlite3
from pathlib import Path
import sys
from datetime import datetime

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent))

try:
    from database_manager import DatabaseManager
    from rename_agent import rename_file, get_extracted_info
    DATABASE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import modules: {e}")
    DATABASE_AVAILABLE = False

DATABASE_PATH = "notary_processing.db"

class ValidationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Notary Validation GUI")
        self.root.geometry("1200x700")
        
        # Configure dark theme
        self.configure_dark_theme()
        
        # Current document state
        self.current_doc_id = None
        self.current_extraction_id = None
        self.current_filename = None
        self.documents = []  # Store loaded documents for selection
        
        # Create main frames
        self.setup_ui()
        
        # Load documents
        self.load_documents()
    
    def configure_dark_theme(self):
        """Configure dark theme colors for the GUI."""
        # Configure root window
        self.root.configure(bg='#2b2b2b')
        
        # Configure ttk style
        style = ttk.Style()
        style.theme_use('clam')  # 'clam' theme works well with custom colors
        
        # Configure colors
        bg_color = '#2b2b2b'
        fg_color = '#ffffff'
        entry_bg = '#3c3c3c'
        entry_fg = '#ffffff'
        select_bg = '#4a4a4a'
        select_fg = '#ffffff'
        button_bg = '#3c3c3c'
        button_fg = '#ffffff'
        listbox_bg = '#3c3c3c'
        listbox_fg = '#ffffff'
        text_bg = '#3c3c3c'
        text_fg = '#ffffff'
        
        # Configure ttk widget styles
        style.configure('TFrame', background=bg_color)
        style.configure('TLabelFrame', background=bg_color, foreground=fg_color)
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        style.configure('TEntry', fieldbackground=entry_bg, foreground=entry_fg, insertcolor=fg_color)
        style.configure('TButton', background=button_bg, foreground=button_fg)
        style.configure('TCheckbutton', background=bg_color, foreground=fg_color)
        style.configure('TScrollbar', background=button_bg, troughcolor=bg_color)
        
        # Configure tk widgets (Listbox, Text, etc.)
        self.root.option_add('*Listbox*background', listbox_bg)
        self.root.option_add('*Listbox*foreground', listbox_fg)
        self.root.option_add('*Listbox*selectBackground', select_bg)
        self.root.option_add('*Listbox*selectForeground', select_fg)
        self.root.option_add('*Text*background', text_bg)
        self.root.option_add('*Text*foreground', text_fg)
        self.root.option_add('*Text*selectBackground', select_bg)
        self.root.option_add('*Text*selectForeground', select_fg)
        self.root.option_add('*Scrollbar*background', button_bg)
        self.root.option_add('*Scrollbar*troughColor', bg_color)
        
    def setup_ui(self):
        """Setup the main UI layout."""
        # Top status bar
        status_frame = ttk.Frame(self.root, padding="5")
        status_frame.grid(row=0, column=0, columnspan=2, sticky="we")
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT, padx=(0, 5))
        self.status_label = ttk.Label(status_frame, text="Ready", foreground="#90ee90")
        self.status_label.pack(side=tk.LEFT)
        
        # Left panel: Document list
        left_frame = ttk.LabelFrame(self.root, text="Documents Needing Validation", padding="10")
        left_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.doc_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                                       height=20, width=50, font=('TkDefaultFont', 10))
        self.doc_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.doc_listbox.yview)
        
        # Bind selection event
        self.doc_listbox.bind('<<ListboxSelect>>', self.on_document_select)
        
        # Refresh button
        ttk.Button(left_frame, text="Refresh List", command=self.load_documents).pack(pady=5)
        
        # Right panel: Document details
        right_frame = ttk.LabelFrame(self.root, text="Document Details", padding="10")
        right_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)
        
        # Create form fields
        self.create_form(right_frame)
    
    def create_form(self, parent):
        """Create the form for editing document details."""
        # Form fields
        fields = [
            ("original_filename", "Original Filename:", True),
            ("date_of_notarization", "Date of Notarization:", False),
            ("document_number", "Document Number:", False),
            ("document_type", "Document Type:", False),
            ("lastname", "Last Name:", False),
            ("page_number", "Page Number:", False),
            ("book_number", "Book Number:", False),
            ("series_year", "Series Year:", False),
        ]
        
        # Create entries
        self.entries = {}
        row = 0
        
        for field, label, readonly in fields:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            if readonly:
                entry = ttk.Entry(parent, width=50)
                entry.config(state='readonly')
            else:
                entry = ttk.Entry(parent, width=50)
                # Bind field changes to update filename preview
                entry.bind('<KeyRelease>', self.on_field_change)
                entry.bind('<FocusOut>', self.on_field_change)
            entry.grid(row=row, column=1, sticky="we", pady=2, padx=(5, 0))
            self.entries[field] = entry
            row += 1
        
        # Checkboxes
        self.is_waiver_var = tk.BooleanVar()
        self.is_corporate_var = tk.BooleanVar()
        
        # Bind checkbox changes to update filename preview
        self.is_waiver_var.trace_add('write', lambda *args: self.on_field_change())
        self.is_corporate_var.trace_add('write', lambda *args: self.on_field_change())
        
        ttk.Checkbutton(parent, text="Is Waiver Document", 
                       variable=self.is_waiver_var).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        ttk.Checkbutton(parent, text="Is Corporate Document", 
                       variable=self.is_corporate_var).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Confidence score
        ttk.Label(parent, text="Confidence Score:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.confidence_label = ttk.Label(parent, text="0.0")
        self.confidence_label.grid(row=row, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        row += 1
        
        # Filename preview
        ttk.Label(parent, text="Filename Preview:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.filename_preview = ttk.Label(parent, text="", font=('TkFixedFont', 10))
        self.filename_preview.grid(row=row, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        row += 1
        
        # OCR Preview
        ttk.Label(parent, text="OCR Preview:").grid(row=row, column=0, sticky=tk.NW, pady=2)
        self.ocr_text = scrolledtext.ScrolledText(parent, width=60, height=15, wrap=tk.WORD)
        self.ocr_text.grid(row=row, column=1, sticky="we", pady=2, padx=(5, 0))
        row += 1
        
        # Button frame
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="Save Validation", 
                  command=self.save_validation).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Rename File", 
                  command=self.rename_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Dry Run Rename", 
                  command=lambda: self.rename_file(dry_run=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Form", 
                  command=self.clear_form).pack(side=tk.LEFT, padx=5)
        
        # Configure column weights
        parent.columnconfigure(1, weight=1)
    
    def load_documents(self):
        """Load documents needing validation from database."""
        if not DATABASE_AVAILABLE:
            messagebox.showerror("Error", "Database module not available")
            return
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
            SELECT 
                d.id as doc_id,
                d.original_filename,
                ed.id as extraction_id,
                ed.document_type,
                ed.lastname,
                ed.confidence_score,
                ed.validated
            FROM documents d
            JOIN extracted_data ed ON d.id = ed.document_id
            WHERE ed.validated = 0 OR ed.confidence_score < 0.8
            ORDER BY ed.confidence_score ASC, d.created_at DESC
            LIMIT 100
            """
            
            cursor.execute(query)
            self.documents = cursor.fetchall()  # Store documents for selection
            
            # Clear listbox
            self.doc_listbox.delete(0, tk.END)
            
            # Add documents to listbox
            for doc in self.documents:
                display_text = f"{doc['original_filename']}"
                if doc['document_type']:
                    display_text += f" - {doc['document_type']}"
                if doc['lastname']:
                    display_text += f" ({doc['lastname']})"
                if doc['confidence_score']:
                    display_text += f" [{doc['confidence_score']:.2f}]"
                
                self.doc_listbox.insert(tk.END, display_text)
                # Color code by confidence (dark theme)
                bg_color = '#442222' if (doc['confidence_score'] or 0) < 0.5 else \
                          '#444422' if (doc['confidence_score'] or 0) < 0.8 else '#224422'
                self.doc_listbox.itemconfig(tk.END, {'bg': bg_color})
            
            conn.close()
            self.status_label.config(text=f"Loaded {len(self.documents)} documents", foreground="#90ee90")
            
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load documents:\n{str(e)}")
            self.status_label.config(text="Error loading documents", foreground="#ff6666")
    
    def on_field_change(self, *args):
        """Handle field changes to update filename preview."""
        self.update_filename_preview()
    
    def on_document_select(self, event):
        """Handle document selection from list."""
        selection = self.doc_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        
        if index >= len(self.documents):
            return
        
        doc = self.documents[index]
        self.current_doc_id = doc['doc_id']
        self.current_extraction_id = doc['extraction_id']
        self.current_filename = doc['original_filename']
        
        # Get full document details from database
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT ed.* FROM extracted_data ed 
                WHERE ed.id = ?
            """, (self.current_extraction_id,))
            
            full_doc = cursor.fetchone()
            
            if not full_doc:
                messagebox.showerror("Error", "Document details not found in database")
                return
            
            # Update form fields
            self.entries['original_filename'].config(state='normal')
            self.entries['original_filename'].delete(0, tk.END)
            self.entries['original_filename'].insert(0, doc['original_filename'])
            self.entries['original_filename'].config(state='readonly')
            
            # Update other fields
            for field in ['date_of_notarization', 'document_number', 'document_type', 
                         'lastname', 'page_number', 'book_number', 'series_year']:
                self.entries[field].delete(0, tk.END)
                if full_doc[field]:
                    self.entries[field].insert(0, full_doc[field])
            
            # Update checkboxes
            self.is_waiver_var.set(bool(full_doc['is_waiver']))
            self.is_corporate_var.set(bool(full_doc['is_corporate']))
            
            # Update confidence score
            confidence = full_doc['confidence_score'] or 0.0
            self.confidence_label.config(text=f"{confidence:.2f}")
            
            # Update filename preview
            self.update_filename_preview()
            
            # Load OCR text
            self.load_ocr_text(self.current_doc_id)
            
            self.status_label.config(text=f"Loaded: {doc['original_filename']}", foreground="#66aaff")
            
            conn.close()
            
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load document details:\n{str(e)}")
    
    def load_ocr_text(self, doc_id):
        """Load OCR text for the selected document."""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT ocr_text FROM ocr_results 
                WHERE document_id = ? 
                ORDER BY page_number
            """, (doc_id,))
            
            results = cursor.fetchall()
            ocr_text = "\n\n--- Page Break ---\n\n".join([row[0] for row in results if row[0]])
            
            self.ocr_text.delete(1.0, tk.END)
            self.ocr_text.insert(1.0, ocr_text if ocr_text else "No OCR text available")
            
            conn.close()
        except Exception as e:
            self.ocr_text.delete(1.0, tk.END)
            self.ocr_text.insert(1.0, f"Error loading OCR text: {str(e)}")
    
    def update_filename_preview(self):
        """Update the filename preview based on current field values."""
        if not self.current_filename:
            return
        
        # Get field values
        date = self.entries['date_of_notarization'].get()
        doc_no = self.entries['document_number'].get()
        doc_type = self.entries['document_type'].get()
        lastname = self.entries['lastname'].get()
        is_waiver = self.is_waiver_var.get()
        
        # Simple filename generation (simplified version)
        original_stem = Path(self.current_filename).stem
        
        # Basic sanitization
        def sanitize(text):
            if not text:
                return ""
            return text.upper().replace(" ", "_").replace("/", "_").replace("\\", "_")
        
        sanitized_lastname = sanitize(lastname)
        sanitized_doctype = sanitize(doc_type)
        sanitized_docno = sanitize(doc_no)
        
        # Very simple logic for preview
        parts = []
        if date:
            # Try to convert date to ISO format (simplified)
            try:
                # Simple date parsing for preview
                if "FEB" in date.upper():
                    month = "02"
                elif "MAR" in date.upper():
                    month = "03"
                else:
                    month = "01"
                # Extract year (last 4 digits)
                import re
                year_match = re.search(r'\d{4}', date)
                year = year_match.group(0) if year_match else "2026"
                # Extract day (first 1-2 digits)
                day_match = re.search(r'\b(\d{1,2})\b', date)
                day = day_match.group(1).zfill(2) if day_match else "01"
                iso_date = f"{year}-{month}-{day}"
                parts.append(iso_date)
            except:
                parts.append("DATE")
        
        if sanitized_docno and not is_waiver:
            parts.append(f"D{sanitized_docno}")
        
        if sanitized_doctype:
            parts.append(sanitized_doctype)
        
        if sanitized_lastname:
            parts.append(sanitized_lastname)
        
        if parts:
            filename = "-".join(parts) + ".pdf"
        else:
            filename = f"{original_stem}_renamed.pdf"
        
        self.filename_preview.config(text=filename)
    
    def save_validation(self):
        """Save validation changes to database."""
        if not self.current_extraction_id:
            messagebox.showwarning("No Selection", "Please select a document first")
            return
        
        if not DATABASE_AVAILABLE:
            messagebox.showerror("Error", "Database module not available")
            return
        
        try:
            db_manager = DatabaseManager()
            conn = db_manager.connect()
            cursor = conn.cursor()
            
            # Get current values for comparison (optional)
            cursor.execute("SELECT * FROM extracted_data WHERE id = ?", (self.current_extraction_id,))
            current = cursor.fetchone()
            
            # Prepare update data
            updates = {
                'date_of_notarization': self.entries['date_of_notarization'].get() or None,
                'document_number': self.entries['document_number'].get() or None,
                'document_type': self.entries['document_type'].get() or None,
                'lastname': self.entries['lastname'].get() or None,
                'page_number': self.entries['page_number'].get() or None,
                'book_number': self.entries['book_number'].get() or None,
                'series_year': self.entries['series_year'].get() or None,
                'is_waiver': 1 if self.is_waiver_var.get() else 0,
                'is_corporate': 1 if self.is_corporate_var.get() else 0,
                'validated': 1,
                'validated_at': datetime.now().isoformat(),
                'validated_by': 'tkinter_gui'
            }
            
            # Build update query
            set_clauses = []
            params = []
            for field, value in updates.items():
                if field in ['validated', 'validated_at', 'validated_by']:
                    continue  # Handle separately
                set_clauses.append(f"{field} = ?")
                params.append(value)
            
            # Add validation fields
            set_clauses.append("validated = 1")
            set_clauses.append("validated_at = ?")
            set_clauses.append("validated_by = ?")
            params.append(datetime.now().isoformat())
            params.append('tkinter_gui')
            
            # Add extraction_id
            params.append(self.current_extraction_id)
            
            query = f"UPDATE extracted_data SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
            
            # Update confidence score based on filled fields
            filled_fields = sum(1 for field in ['date_of_notarization', 'document_number', 
                                               'document_type', 'lastname'] 
                               if updates.get(field))
            new_confidence = filled_fields / 4.0
            
            cursor.execute("UPDATE extracted_data SET confidence_score = ? WHERE id = ?",
                          (new_confidence, self.current_extraction_id))
            conn.commit()
            
            db_manager.close()
            
            # Update UI
            self.confidence_label.config(text=f"{new_confidence:.2f}")
            self.status_label.config(text="Validation saved successfully", foreground="#90ee90")
            
            # Refresh document list to show updated status
            self.load_documents()
            
            messagebox.showinfo("Success", "Validation saved successfully")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save validation:\n{str(e)}")
    
    def update_extracted_data(self):
        """Update extracted_data with current GUI values without marking as validated."""
        if not self.current_extraction_id:
            return False
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Prepare update data
            updates = {
                'date_of_notarization': self.entries['date_of_notarization'].get() or None,
                'document_number': self.entries['document_number'].get() or None,
                'document_type': self.entries['document_type'].get() or None,
                'lastname': self.entries['lastname'].get() or None,
                'page_number': self.entries['page_number'].get() or None,
                'book_number': self.entries['book_number'].get() or None,
                'series_year': self.entries['series_year'].get() or None,
                'is_waiver': 1 if self.is_waiver_var.get() else 0,
                'is_corporate': 1 if self.is_corporate_var.get() else 0,
            }
            
            # Build update query
            set_clauses = []
            params = []
            for field, value in updates.items():
                set_clauses.append(f"{field} = ?")
                params.append(value)
            
            params.append(self.current_extraction_id)
            query = f"UPDATE extracted_data SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, params)
            
            # Update confidence score based on filled fields
            filled_fields = sum(1 for field in ['date_of_notarization', 'document_number', 
                                               'document_type', 'lastname'] 
                               if updates.get(field))
            new_confidence = filled_fields / 4.0
            cursor.execute("UPDATE extracted_data SET confidence_score = ? WHERE id = ?",
                          (new_confidence, self.current_extraction_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error updating extracted data: {e}")
            return False
    
    def rename_file(self, dry_run=False):
        """Rename the selected file."""
        if not self.current_doc_id or not self.current_filename:
            messagebox.showwarning("No Selection", "Please select a document first")
            return
        
        if not DATABASE_AVAILABLE:
            messagebox.showerror("Error", "Database module not available")
            return
        
        try:
            # Prepare paths
            pdf_path = Path("input") / self.current_filename
            md_path = Path("ocr-output") / f"{Path(self.current_filename).stem}.md"
            output_dir = Path("renamed")
            
            if not pdf_path.exists():
                messagebox.showerror("File Not Found", f"PDF file not found:\n{pdf_path}")
                return
            
            if not md_path.exists():
                messagebox.showerror("File Not Found", f"OCR file not found:\n{md_path}")
                return
            
            # Update extracted data with current GUI values
            self.update_extracted_data()
            
            # Create database manager
            db_manager = DatabaseManager()
            
            # Call rename function
            success, original, new_path, message = rename_file(
                pdf_path=pdf_path,
                md_path=md_path,
                output_dir=output_dir,
                template=None,
                dry_run=dry_run,
                interactive=False,
                db_manager=db_manager,
                doc_id=self.current_doc_id
            )
            
            db_manager.close()
            
            if success:
                if dry_run:
                    messagebox.showinfo("Dry Run Result", message)
                else:
                    self.status_label.config(text=f"Renamed: {message}", foreground="#90ee90")
                    messagebox.showinfo("Success", f"File renamed successfully:\n{message}")
            else:
                messagebox.showerror("Rename Error", f"Failed to rename file:\n{message}")
                
        except Exception as e:
            messagebox.showerror("Rename Error", f"Error during rename:\n{str(e)}")
    
    def clear_form(self):
        """Clear the form."""
        self.current_doc_id = None
        self.current_extraction_id = None
        self.current_filename = None
        
        for field, entry in self.entries.items():
            if field != 'original_filename':
                entry.delete(0, tk.END)
            else:
                entry.config(state='normal')
                entry.delete(0, tk.END)
                entry.config(state='readonly')
        
        self.is_waiver_var.set(False)
        self.is_corporate_var.set(False)
        self.confidence_label.config(text="0.0")
        self.filename_preview.config(text="")
        self.ocr_text.delete(1.0, tk.END)
        self.status_label.config(text="Form cleared", foreground="#66aaff")

def main():
    """Main entry point."""
    root = tk.Tk()
    app = ValidationGUI(root)
    
    # Handle window close
    def on_closing():
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()