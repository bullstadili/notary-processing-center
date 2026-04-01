#!/usr/bin/env python3
"""
Main GUI for Notary Processing Center.
Provides access to all agents: OCR, Parse, Rename, Database, and Validation.
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import sys
import threading
from pathlib import Path
import queue
import shutil
import os

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent))

# Try to import agent modules for direct function calls
try:
    from ocr_processor import process_pdf, check_dependencies
    from document_parser import parse_markdown_file
    from rename_agent import rename_file, get_extracted_info
    from database_manager import DatabaseManager
    from database_admin import cmd_init, cmd_import, cmd_stats, cmd_backup, cmd_query, cmd_repair
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")
    MODULES_AVAILABLE = False

class NotaryProcessingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Notary Processing Center - Main GUI")
        self.root.geometry("1400x800")
        # Initialize theme state
        self.current_theme = 'dark'
        
        # Configure dark theme
        self.configure_dark_theme()
        
        # Create menu bar
        self.setup_menu()
        
        # Output queue for thread-safe communication
        self.output_queue = queue.Queue()
        
        # Create main notebook (tabbed interface)
        self.setup_tabs()
        
        # Start output monitor
        self.monitor_output_queue()
    
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
        style.configure('TNotebook', background=bg_color, foreground=fg_color)
        style.configure('TNotebook.Tab', background=button_bg, foreground=fg_color)
        
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
        
        # Configure menu colors
        self.root.option_add('*Menu*background', bg_color)
        self.root.option_add('*Menu*foreground', fg_color)
        self.root.option_add('*Menu*selectColor', select_bg)
    
    def configure_light_theme(self):
        """Configure light theme colors for the GUI."""
        # Configure root window
        self.root.configure(bg='#f0f0f0')
        
        # Configure ttk style
        style = ttk.Style()
        style.theme_use('clam')  # 'clam' theme works well with custom colors
        
        # Configure colors
        bg_color = '#f0f0f0'
        fg_color = '#000000'
        entry_bg = '#ffffff'
        entry_fg = '#000000'
        select_bg = '#4a90e2'
        select_fg = '#ffffff'
        button_bg = '#e0e0e0'
        button_fg = '#000000'
        listbox_bg = '#ffffff'
        listbox_fg = '#000000'
        text_bg = '#ffffff'
        text_fg = '#000000'
        
        # Configure ttk widget styles
        style.configure('TFrame', background=bg_color)
        style.configure('TLabelFrame', background=bg_color, foreground=fg_color)
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        style.configure('TEntry', fieldbackground=entry_bg, foreground=entry_fg, insertcolor=fg_color)
        style.configure('TButton', background=button_bg, foreground=button_fg)
        style.configure('TCheckbutton', background=bg_color, foreground=fg_color)
        style.configure('TScrollbar', background=button_bg, troughcolor=bg_color)
        style.configure('TNotebook', background=bg_color, foreground=fg_color)
        style.configure('TNotebook.Tab', background=button_bg, foreground=fg_color)
        
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
        
        # Configure menu colors
        self.root.option_add('*Menu*background', bg_color)
        self.root.option_add('*Menu*foreground', fg_color)
        self.root.option_add('*Menu*selectColor', select_bg)
    
    
    def setup_menu(self):
        """Create the main menu bar."""
        # Remove existing menu if any
        if hasattr(self, 'menubar') and self.menubar:
            self.root.config(menu=None)
            self.menubar.destroy()
        
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)
        
        # View menu
        view_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Theme", command=self.toggle_theme)

    def toggle_theme(self):
        """Toggle between dark and light themes."""
        if self.current_theme == 'dark':
            self.current_theme = 'light'
            self.configure_light_theme()
        else:
            self.current_theme = 'dark'
            self.configure_dark_theme()
        
        self.append_output(f"Switched to {self.current_theme} theme\n", "info")
        # Recreate menu to apply new colors
        self.setup_menu()

    
    def setup_tabs(self):
        """Setup the tabbed interface."""
        # Create notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.ocr_tab = ttk.Frame(self.notebook)
        self.parse_tab = ttk.Frame(self.notebook)
        self.rename_tab = ttk.Frame(self.notebook)
        self.database_tab = ttk.Frame(self.notebook)
        self.validation_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.ocr_tab, text="OCR Processing")
        self.notebook.add(self.parse_tab, text="Document Parsing")
        self.notebook.add(self.rename_tab, text="File Renaming")
        self.notebook.add(self.database_tab, text="Database Tools")
        self.notebook.add(self.validation_tab, text="Validation")
        
        # Setup each tab
        self.setup_ocr_tab()
        self.setup_parse_tab()
        self.setup_rename_tab()
        self.setup_database_tab()
        self.setup_validation_tab()
        
        # Create output frame at bottom (shared across all tabs)
        self.setup_output_frame()
    
    def setup_ocr_tab(self):
        """Setup OCR Processing tab."""
        # Main frame
        main_frame = ttk.Frame(self.ocr_tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="OCR Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Grid configuration
        for i in range(4):
            settings_frame.columnconfigure(i, weight=1)
        
        # Input directory
        ttk.Label(settings_frame, text="Input Directory:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ocr_input_var = tk.StringVar(value="input")
        ttk.Entry(settings_frame, textvariable=self.ocr_input_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        
        # Output directory
        ttk.Label(settings_frame, text="Output Directory:").grid(row=0, column=2, sticky=tk.W, pady=5)
        self.ocr_output_var = tk.StringVar(value="ocr-output")
        ttk.Entry(settings_frame, textvariable=self.ocr_output_var, width=30).grid(row=0, column=3, sticky=tk.W, pady=5, padx=(5, 0))
        
        # DPI setting
        ttk.Label(settings_frame, text="DPI:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ocr_dpi_var = tk.StringVar(value="150")
        ttk.Entry(settings_frame, textvariable=self.ocr_dpi_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        
        # Timeout
        ttk.Label(settings_frame, text="Timeout (seconds):").grid(row=1, column=2, sticky=tk.W, pady=5)
        self.ocr_timeout_var = tk.StringVar(value="500")
        ttk.Entry(settings_frame, textvariable=self.ocr_timeout_var, width=10).grid(row=1, column=3, sticky=tk.W, pady=5, padx=(5, 0))
        
        # Max retries
        ttk.Label(settings_frame, text="Max Retries:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.ocr_retries_var = tk.StringVar(value="3")
        ttk.Entry(settings_frame, textvariable=self.ocr_retries_var, width=10).grid(row=2, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        
        # Force checkbox
        self.ocr_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Force overwrite existing files", 
                       variable=self.ocr_force_var).grid(row=2, column=2, columnspan=2, sticky=tk.W, pady=5)
        
        # Single file mode
        ttk.Label(settings_frame, text="Single File (optional):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.ocr_single_var = tk.StringVar(value="")
        ttk.Entry(settings_frame, textvariable=self.ocr_single_var, width=30).grid(row=3, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        ttk.Button(settings_frame, text="Browse...", 
                  command=self.browse_ocr_file).grid(row=3, column=2, sticky=tk.W, pady=5)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Check Dependencies", 
                  command=self.check_ocr_dependencies).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Process All PDFs", 
                  command=self.process_all_pdfs).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Process Single PDF", 
                  command=self.process_single_pdf).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Output", 
                  command=self.clear_output).pack(side=tk.RIGHT, padx=5)
    
    def setup_parse_tab(self):
        """Setup Document Parsing tab."""
        # Main frame
        main_frame = ttk.Frame(self.parse_tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Parsing Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Input directory
        ttk.Label(settings_frame, text="Input Directory:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.parse_input_var = tk.StringVar(value="ocr-output")
        ttk.Entry(settings_frame, textvariable=self.parse_input_var, width=40).grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        
        # Single file mode
        ttk.Label(settings_frame, text="Single File (optional):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.parse_single_var = tk.StringVar(value="")
        ttk.Entry(settings_frame, textvariable=self.parse_single_var, width=40).grid(row=1, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        ttk.Button(settings_frame, text="Browse...", 
                  command=self.browse_parse_file).grid(row=1, column=2, sticky=tk.W, pady=5)
        
        # Database logging
        self.parse_db_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Enable database logging", 
                       variable=self.parse_db_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Parse All Files", 
                  command=self.parse_all_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Parse Single File", 
                  command=self.parse_single_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Output", 
                  command=self.clear_output).pack(side=tk.RIGHT, padx=5)
    
    def setup_rename_tab(self):
        """Setup File Renaming tab."""
        # Main frame
        main_frame = ttk.Frame(self.rename_tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Renaming Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Grid configuration
        for i in range(4):
            settings_frame.columnconfigure(i, weight=1)
        
        # Input directory
        ttk.Label(settings_frame, text="Input Directory:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.rename_input_var = tk.StringVar(value="input")
        ttk.Entry(settings_frame, textvariable=self.rename_input_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        
        # OCR directory
        ttk.Label(settings_frame, text="OCR Directory:").grid(row=0, column=2, sticky=tk.W, pady=5)
        self.rename_ocr_var = tk.StringVar(value="ocr-output")
        ttk.Entry(settings_frame, textvariable=self.rename_ocr_var, width=30).grid(row=0, column=3, sticky=tk.W, pady=5, padx=(5, 0))
        
        # Output directory
        ttk.Label(settings_frame, text="Output Directory:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.rename_output_var = tk.StringVar(value="renamed")
        ttk.Entry(settings_frame, textvariable=self.rename_output_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        
        # Template
        ttk.Label(settings_frame, text="Template (optional):").grid(row=1, column=2, sticky=tk.W, pady=5)
        self.rename_template_var = tk.StringVar(value="")
        ttk.Entry(settings_frame, textvariable=self.rename_template_var, width=30).grid(row=1, column=3, sticky=tk.W, pady=5, padx=(5, 0))
        
        # Single file mode
        ttk.Label(settings_frame, text="Single File (optional):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.rename_single_var = tk.StringVar(value="")
        ttk.Entry(settings_frame, textvariable=self.rename_single_var, width=30).grid(row=2, column=1, sticky=tk.W, pady=5, padx=(5, 20))
        
        # Options checkboxes
        self.rename_dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Dry run (preview only)", 
                       variable=self.rename_dry_run_var).grid(row=2, column=2, sticky=tk.W, pady=5)
        
        self.rename_interactive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Interactive mode", 
                       variable=self.rename_interactive_var).grid(row=2, column=3, sticky=tk.W, pady=5)
        
        self.rename_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Force overwrite", 
                       variable=self.rename_force_var).grid(row=3, column=0, sticky=tk.W, pady=5)
        
        self.rename_skip_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Skip existing files", 
                       variable=self.rename_skip_var).grid(row=3, column=1, sticky=tk.W, pady=5)
        
        self.rename_nodb_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings_frame, text="Disable database logging", 
                       variable=self.rename_nodb_var).grid(row=3, column=2, sticky=tk.W, pady=5)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Rename All Files", 
                  command=self.rename_all_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Rename Single File", 
                  command=self.rename_single_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Dry Run All Files", 
                  command=lambda: self.rename_all_files(dry_run=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Output", 
                  command=self.clear_output).pack(side=tk.RIGHT, padx=5)
    
    def setup_database_tab(self):
        """Setup Database Tools tab."""
        # Main frame
        main_frame = ttk.Frame(self.database_tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Database file
        db_frame = ttk.LabelFrame(main_frame, text="Database File", padding="10")
        db_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(db_frame, text="Database Path:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.db_path_var = tk.StringVar(value="notary_processing.db")
        ttk.Entry(db_frame, textvariable=self.db_path_var, width=50).grid(row=0, column=1, sticky=tk.W, pady=5, padx=(5, 10))
        ttk.Button(db_frame, text="Browse...", 
                  command=self.browse_database_file).grid(row=0, column=2, sticky=tk.W, pady=5)
        
        # Database operations
        ops_frame = ttk.LabelFrame(main_frame, text="Database Operations", padding="10")
        ops_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create buttons in a grid
        ttk.Button(ops_frame, text="Initialize Database", 
                  command=self.db_init).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Button(ops_frame, text="Import Existing Documents", 
                  command=self.db_import).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Button(ops_frame, text="Show Statistics", 
                  command=self.db_stats).grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        ttk.Button(ops_frame, text="Backup Database", 
                  command=self.db_backup).grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Button(ops_frame, text="Execute Query", 
                  command=self.db_query).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Button(ops_frame, text="Repair Database", 
                  command=self.db_repair).grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        
        # Cleanup operations
        cleanup_frame = ttk.LabelFrame(main_frame, text="Cleanup Operations (Dangerous)", padding="10")
        cleanup_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(cleanup_frame, text="WARNING: These operations delete data permanently!", foreground="red").grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        
        # Create buttons in a grid
        ttk.Button(cleanup_frame, text="Clear Database Contents", 
                  command=self.clear_database_contents).grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Button(cleanup_frame, text="Clear OCR Output Folder", 
                  command=self.clear_ocr_output_folder).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Button(cleanup_frame, text="Clear Renamed Folder", 
                  command=self.clear_renamed_folder).grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        
        # Configure grid columns
        for i in range(3):
            cleanup_frame.columnconfigure(i, weight=1)
        
        # Query input (hidden by default, shown when Execute Query is clicked)
        self.query_frame = ttk.Frame(main_frame)
        
        ttk.Label(self.query_frame, text="SQL Query:").pack(anchor=tk.W, pady=(5, 0))
        self.query_text = scrolledtext.ScrolledText(self.query_frame, height=5, width=80)
        self.query_text.pack(fill=tk.X, pady=(0, 5))
        
        query_button_frame = ttk.Frame(self.query_frame)
        query_button_frame.pack(fill=tk.X)
        
        ttk.Button(query_button_frame, text="Execute", 
                  command=self.execute_query).pack(side=tk.LEFT, padx=5)
        ttk.Button(query_button_frame, text="Cancel", 
                  command=self.hide_query_frame).pack(side=tk.LEFT, padx=5)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Clear Output", 
                  command=self.clear_output).pack(side=tk.RIGHT, padx=5)
    
    def setup_validation_tab(self):
        """Setup Validation tab."""
        # Main frame
        main_frame = ttk.Frame(self.validation_tab, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info frame
        info_frame = ttk.LabelFrame(main_frame, text="Validation GUI", padding="20")
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        # Description
        description = """The Validation GUI provides a detailed interface for reviewing and correcting 
OCR-extracted document information.

Features:
• List of documents needing validation (color-coded by confidence score)
• Field-level editing of all extracted data (date, document number, type, lastname, etc.)
• Real-time filename preview as you edit fields
• OCR text preview for reference
• Save validated data to database
• Rename files directly using validated data
• Audit trail of all corrections"""
        
        ttk.Label(info_frame, text=description, justify=tk.LEFT).pack(anchor=tk.W, pady=10)
        
        # Launch button
        button_frame = ttk.Frame(info_frame)
        button_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(button_frame, text="Launch Validation GUI", 
                  command=self.launch_validation_gui, 
                  style="Accent.TButton").pack(pady=10)
        
        # Status
        self.validation_status_var = tk.StringVar(value="Ready")
        ttk.Label(info_frame, textvariable=self.validation_status_var).pack(pady=5)
    
    def setup_output_frame(self):
        """Setup output display frame (shared across all tabs)."""
        # Create frame at bottom of notebook
        output_frame = ttk.LabelFrame(self.root, text="Output", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=(0, 5))
        
        # Output text widget
        self.output_text = scrolledtext.ScrolledText(output_frame, height=15, wrap=tk.WORD)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure tags for colored output
        self.output_text.tag_config("error", foreground="#ff6666")
        self.output_text.tag_config("success", foreground="#90ee90")
        self.output_text.tag_config("warning", foreground="#ffff66")
        self.output_text.tag_config("info", foreground="#66aaff")
        
        # Clear button
        ttk.Button(output_frame, text="Clear Output", 
                  command=self.clear_output).pack(anchor=tk.E, pady=(5, 0))
    
    def browse_ocr_file(self):
        """Browse for a PDF file for OCR processing."""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(
            title="Select PDF file",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if filename:
            self.ocr_single_var.set(filename)
    
    def browse_parse_file(self):
        """Browse for a markdown file for parsing."""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(
            title="Select markdown file",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")]
        )
        if filename:
            self.parse_single_var.set(filename)
    
    def browse_database_file(self):
        """Browse for a database file."""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(
            title="Select database file",
            filetypes=[("Database files", "*.db"), ("SQLite files", "*.sqlite"), ("All files", "*.*")]
        )
        if filename:
            self.db_path_var.set(filename)
    
    def check_ocr_dependencies(self):
        """Check OCR dependencies."""
        self.append_output("Checking OCR dependencies...\n", "info")
        
        def run_check():
            try:
                from ocr_processor import check_dependencies
                check_dependencies()
                self.append_output("Dependencies check completed.\n", "success")
            except Exception as e:
                self.append_output(f"Error checking dependencies: {str(e)}\n", "error")
        
        threading.Thread(target=run_check, daemon=True).start()
    
    def process_all_pdfs(self):
        """Process all PDFs in the input directory."""
        input_dir = Path(self.ocr_input_var.get())
        output_dir = Path(self.ocr_output_var.get())
        dpi = int(self.ocr_dpi_var.get())
        timeout = int(self.ocr_timeout_var.get())
        max_retries = int(self.ocr_retries_var.get())
        force = self.ocr_force_var.get()
        
        self.append_output(f"Starting OCR processing for all PDFs in {input_dir}...\n", "info")
        
        def run_processing():
            try:
                # Get list of PDF files
                pdf_files = list(input_dir.glob("*.pdf"))
                if not pdf_files:
                    self.append_output(f"No PDF files found in {input_dir}\n", "warning")
                    return
                
                self.append_output(f"Found {len(pdf_files)} PDF files.\n", "info")
                
                # Process each file
                success_count = 0
                for pdf in pdf_files:
                    self.append_output(f"Processing {pdf.name}...\n", "info")
                    try:
                        from ocr_processor import process_pdf
                        process_pdf(pdf, output_dir, dpi, timeout, max_retries, force)
                        success_count += 1
                        self.append_output(f"  Successfully processed {pdf.name}\n", "success")
                    except Exception as e:
                        self.append_output(f"  Error processing {pdf.name}: {str(e)}\n", "error")
                
                self.append_output(f"\nProcessing complete: {success_count}/{len(pdf_files)} successful\n", 
                                  "success" if success_count == len(pdf_files) else "warning")
                
            except Exception as e:
                self.append_output(f"Error during OCR processing: {str(e)}\n", "error")
        
        threading.Thread(target=run_processing, daemon=True).start()
    
    def process_single_pdf(self):
        """Process a single PDF file."""
        pdf_path = Path(self.ocr_single_var.get())
        if not pdf_path.exists():
            messagebox.showerror("Error", f"PDF file not found: {pdf_path}")
            return
        
        output_dir = Path(self.ocr_output_var.get())
        dpi = int(self.ocr_dpi_var.get())
        timeout = int(self.ocr_timeout_var.get())
        max_retries = int(self.ocr_retries_var.get())
        force = self.ocr_force_var.get()
        
        self.append_output(f"Processing single PDF: {pdf_path.name}...\n", "info")
        
        def run_processing():
            try:
                from ocr_processor import process_pdf
                process_pdf(pdf_path, output_dir, dpi, timeout, max_retries, force)
                self.append_output(f"Successfully processed {pdf_path.name}\n", "success")
            except Exception as e:
                self.append_output(f"Error processing {pdf_path.name}: {str(e)}\n", "error")
        
        threading.Thread(target=run_processing, daemon=True).start()
    
    def parse_all_files(self):
        """Parse all markdown files."""
        input_dir = Path(self.parse_input_var.get())
        use_db = self.parse_db_var.get()
        
        self.append_output(f"Starting parsing of all markdown files in {input_dir}...\n", "info")
        
        def run_parsing():
            try:
                # Get list of markdown files
                md_files = list(input_dir.glob("*.md"))
                if not md_files:
                    self.append_output(f"No markdown files found in {input_dir}\n", "warning")
                    return
                
                self.append_output(f"Found {len(md_files)} markdown files.\n", "info")
                
                # Initialize database manager if needed
                db_manager = None
                if use_db and MODULES_AVAILABLE:
                    try:
                        db_manager = DatabaseManager()
                        self.append_output("Database logging enabled\n", "info")
                    except Exception as e:
                        self.append_output(f"Warning: Database initialization failed: {str(e)}\n", "warning")
                
                # Parse each file
                success_count = 0
                for md_file in md_files:
                    self.append_output(f"Parsing {md_file.name}...\n", "info")
                    try:
                        # Try to find document in database
                        doc_id = None
                        if db_manager:
                            original_filename = md_file.stem + ".pdf"
                            document = db_manager.get_document(original_filename=original_filename)
                            if document:
                                doc_id = document['id']
                                self.append_output(f"  Document ID: {doc_id}\n", "info")
                        
                        # Parse the file
                        from document_parser import parse_markdown_file
                        info = parse_markdown_file(md_file, db_manager, doc_id)
                        
                        # Display results
                        self.append_output(f"  Date: {info['date_of_notarization'] or 'Not found'}\n", "info")
                        self.append_output(f"  Doc No: {info['document_number'] or 'Not found'}\n", "info")
                        self.append_output(f"  Type: {info['document_type'] or 'Not found'}\n", "info")
                        self.append_output(f"  Lastname: {info['lastname'] or 'Not found'}\n", "info")
                        
                        success_count += 1
                        self.append_output(f"  Successfully parsed {md_file.name}\n", "success")
                    except Exception as e:
                        self.append_output(f"  Error parsing {md_file.name}: {str(e)}\n", "error")
                
                self.append_output(f"\nParsing complete: {success_count}/{len(md_files)} successful\n", 
                                  "success" if success_count == len(md_files) else "warning")
                
                # Close database connection
                if db_manager:
                    db_manager.close()
                
            except Exception as e:
                self.append_output(f"Error during parsing: {str(e)}\n", "error")
        
        threading.Thread(target=run_parsing, daemon=True).start()
    
    def parse_single_file(self):
        """Parse a single markdown file."""
        md_path = Path(self.parse_single_var.get())
        if not md_path.exists():
            messagebox.showerror("Error", f"Markdown file not found: {md_path}")
            return
        
        use_db = self.parse_db_var.get()
        
        self.append_output(f"Parsing single file: {md_path.name}...\n", "info")
        
        def run_parsing():
            try:
                # Initialize database manager if needed
                db_manager = None
                doc_id = None
                
                if use_db and MODULES_AVAILABLE:
                    try:
                        db_manager = DatabaseManager()
                        self.append_output("Database logging enabled\n", "info")
                        
                        # Try to find document in database
                        original_filename = md_path.stem + ".pdf"
                        document = db_manager.get_document(original_filename=original_filename)
                        if document:
                            doc_id = document['id']
                            self.append_output(f"Document ID: {doc_id}\n", "info")
                    except Exception as e:
                        self.append_output(f"Warning: Database initialization failed: {str(e)}\n", "warning")
                
                # Parse the file
                from document_parser import parse_markdown_file
                info = parse_markdown_file(md_path, db_manager, doc_id)
                
                # Display results
                self.append_output(f"Date of Notarization: {info['date_of_notarization'] or 'Not found'}\n", "info")
                self.append_output(f"Document Number: {info['document_number'] or 'Not found'}\n", "info")
                self.append_output(f"Document Type: {info['document_type'] or 'Not found'}\n", "info")
                self.append_output(f"Last Name: {info['lastname'] or 'Not found'}\n", "info")
                self.append_output(f"Page Number: {info['page_number'] or 'Not found'}\n", "info")
                self.append_output(f"Book Number: {info['book_number'] or 'Not found'}\n", "info")
                self.append_output(f"Series Year: {info['series_year'] or 'Not found'}\n", "info")
                
                self.append_output(f"Successfully parsed {md_path.name}\n", "success")
                
                # Close database connection
                if db_manager:
                    db_manager.close()
                
            except Exception as e:
                self.append_output(f"Error parsing {md_path.name}: {str(e)}\n", "error")
        
        threading.Thread(target=run_parsing, daemon=True).start()
    
    def rename_all_files(self, dry_run=False):
        """Rename all PDF files."""
        input_dir = Path(self.rename_input_var.get())
        ocr_dir = Path(self.rename_ocr_var.get())
        output_dir = Path(self.rename_output_var.get())
        template = self.rename_template_var.get() or None
        interactive = self.rename_interactive_var.get()
        force = self.rename_force_var.get()
        skip_existing = self.rename_skip_var.get()
        no_db = self.rename_nodb_var.get()
        
        if dry_run:
            self.append_output("DRY RUN MODE: No files will be renamed.\n", "warning")
        
        self.append_output(f"Starting rename operation for all PDFs in {input_dir}...\n", "info")
        
        def run_renaming():
            try:
                # Get list of PDF files
                pdf_files = list(input_dir.glob("*.pdf"))
                if not pdf_files:
                    self.append_output(f"No PDF files found in {input_dir}\n", "warning")
                    return
                
                self.append_output(f"Found {len(pdf_files)} PDF files.\n", "info")
                
                # Initialize database manager if needed
                db_manager = None
                if not no_db and MODULES_AVAILABLE:
                    try:
                        db_manager = DatabaseManager()
                        self.append_output("Database logging enabled\n", "info")
                    except Exception as e:
                        self.append_output(f"Warning: Database initialization failed: {str(e)}\n", "warning")
                
                # Process each file
                success_count = 0
                skip_count = 0
                for pdf_path in pdf_files:
                    self.append_output(f"Processing {pdf_path.name}...\n", "info")
                    
                    # Check if OCR file exists
                    md_path = ocr_dir / f"{pdf_path.stem}.md"
                    if not md_path.exists():
                        self.append_output(f"  Warning: No OCR file found for {pdf_path.name}, skipping\n", "warning")
                        skip_count += 1
                        continue
                    
                    # Try to find document in database
                    doc_id = None
                    if db_manager:
                        try:
                            document = db_manager.get_document(original_filename=pdf_path.name)
                            if document:
                                doc_id = document['id']
                                self.append_output(f"  Document ID: {doc_id}\n", "info")
                        except Exception as e:
                            self.append_output(f"  Warning: Database lookup failed: {str(e)}\n", "warning")
                    
                    try:
                        from rename_agent import rename_file
                        success, original, new_path, message = rename_file(
                            pdf_path=pdf_path,
                            md_path=md_path,
                            output_dir=output_dir,
                            template=template,
                            dry_run=dry_run or self.rename_dry_run_var.get(),
                            interactive=interactive,
                            db_manager=db_manager,
                            doc_id=doc_id
                        )
                        
                        if success:
                            success_count += 1
                            self.append_output(f"  {message}\n", "success")
                        else:
                            self.append_output(f"  Error: {message}\n", "error")
                            
                    except Exception as e:
                        self.append_output(f"  Error renaming {pdf_path.name}: {str(e)}\n", "error")
                
                # Summary
                if dry_run or self.rename_dry_run_var.get():
                    self.append_output(f"\nDry run complete: {success_count} files would be renamed, {skip_count} skipped\n", "info")
                else:
                    self.append_output(f"\nRenaming complete: {success_count} files renamed, {skip_count} skipped\n", 
                                      "success" if success_count > 0 else "warning")
                
                # Close database connection
                if db_manager:
                    db_manager.close()
                
            except Exception as e:
                self.append_output(f"Error during renaming: {str(e)}\n", "error")
        
        threading.Thread(target=run_renaming, daemon=True).start()
    
    def rename_single_file(self):
        """Rename a single PDF file."""
        pdf_stem = Path(self.rename_single_var.get()).stem
        input_dir = Path(self.rename_input_var.get())
        ocr_dir = Path(self.rename_ocr_var.get())
        output_dir = Path(self.rename_output_var.get())
        template = self.rename_template_var.get() or None
        dry_run = self.rename_dry_run_var.get()
        interactive = self.rename_interactive_var.get()
        no_db = self.rename_nodb_var.get()
        
        # Find the PDF file
        pdf_files = list(input_dir.glob(f"{pdf_stem}.pdf"))
        if not pdf_files:
            messagebox.showerror("Error", f"PDF file not found: {pdf_stem}")
            return
        
        pdf_path = pdf_files[0]
        md_path = ocr_dir / f"{pdf_path.stem}.md"
        
        if not md_path.exists():
            messagebox.showerror("Error", f"OCR file not found: {md_path}")
            return
        
        self.append_output(f"Renaming single file: {pdf_path.name}...\n", "info")
        
        def run_renaming():
            try:
                # Initialize database manager if needed
                db_manager = None
                doc_id = None
                
                if not no_db and MODULES_AVAILABLE:
                    try:
                        db_manager = DatabaseManager()
                        self.append_output("Database logging enabled\n", "info")
                        
                        # Try to find document in database
                        document = db_manager.get_document(original_filename=pdf_path.name)
                        if document:
                            doc_id = document['id']
                            self.append_output(f"Document ID: {doc_id}\n", "info")
                    except Exception as e:
                        self.append_output(f"Warning: Database initialization failed: {str(e)}\n", "warning")
                
                # Rename the file
                from rename_agent import rename_file
                success, original, new_path, message = rename_file(
                    pdf_path=pdf_path,
                    md_path=md_path,
                    output_dir=output_dir,
                    template=template,
                    dry_run=dry_run,
                    interactive=interactive,
                    db_manager=db_manager,
                    doc_id=doc_id
                )
                
                if success:
                    if dry_run:
                        self.append_output(f"Dry run: {message}\n", "info")
                    else:
                        self.append_output(f"Success: {message}\n", "success")
                else:
                    self.append_output(f"Error: {message}\n", "error")
                
                # Close database connection
                if db_manager:
                    db_manager.close()
                
            except Exception as e:
                self.append_output(f"Error renaming {pdf_path.name}: {str(e)}\n", "error")
        
        threading.Thread(target=run_renaming, daemon=True).start()
    
    def db_init(self):
        """Initialize database."""
        self.append_output("Initializing database...\n", "info")
        
        def run_init():
            try:
                # Run via subprocess to capture output
                cmd = [sys.executable, "database_admin.py", "init", "--force"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                self.append_output(result.stdout, "info")
                if result.stderr:
                    self.append_output(result.stderr, "error")
                
                if result.returncode == 0:
                    self.append_output("Database initialized successfully\n", "success")
                else:
                    self.append_output(f"Database initialization failed with code {result.returncode}\n", "error")
                    
            except Exception as e:
                self.append_output(f"Error initializing database: {str(e)}\n", "error")
        
        threading.Thread(target=run_init, daemon=True).start()
    
    def db_import(self):
        """Import existing documents."""
        self.append_output("Importing existing documents...\n", "info")
        
        def run_import():
            try:
                # Run via subprocess
                cmd = [sys.executable, "database_admin.py", "import"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                self.append_output(result.stdout, "info")
                if result.stderr:
                    self.append_output(result.stderr, "error")
                
                if result.returncode == 0:
                    self.append_output("Import completed successfully\n", "success")
                else:
                    self.append_output(f"Import failed with code {result.returncode}\n", "error")
                    
            except Exception as e:
                self.append_output(f"Error importing documents: {str(e)}\n", "error")
        
        threading.Thread(target=run_import, daemon=True).start()
    
    def db_stats(self):
        """Show database statistics."""
        self.append_output("Getting database statistics...\n", "info")
        
        def run_stats():
            try:
                # Run via subprocess
                cmd = [sys.executable, "database_admin.py", "stats"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                self.append_output(result.stdout, "info")
                if result.stderr:
                    self.append_output(result.stderr, "error")
                
                if result.returncode == 0:
                    self.append_output("Statistics retrieved successfully\n", "success")
                else:
                    self.append_output(f"Failed to get statistics with code {result.returncode}\n", "error")
                    
            except Exception as e:
                self.append_output(f"Error getting statistics: {str(e)}\n", "error")
        
        threading.Thread(target=run_stats, daemon=True).start()
    
    def db_backup(self):
        """Backup database."""
        self.append_output("Backing up database...\n", "info")
        
        def run_backup():
            try:
                # Run via subprocess
                cmd = [sys.executable, "database_admin.py", "backup", "--compress"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                self.append_output(result.stdout, "info")
                if result.stderr:
                    self.append_output(result.stderr, "error")
                
                if result.returncode == 0:
                    self.append_output("Database backup completed successfully\n", "success")
                else:
                    self.append_output(f"Backup failed with code {result.returncode}\n", "error")
                    
            except Exception as e:
                self.append_output(f"Error backing up database: {str(e)}\n", "error")
        
        threading.Thread(target=run_backup, daemon=True).start()
    
    def db_query(self):
        """Show query input frame."""
        self.query_frame.pack(fill=tk.X, pady=(10, 0))
        self.query_text.focus()
    
    def execute_query(self):
        """Execute custom SQL query."""
        query = self.query_text.get("1.0", tk.END).strip()
        if not query:
            messagebox.showwarning("Warning", "Please enter a SQL query")
            return
        
        self.append_output(f"Executing query: {query[:50]}...\n", "info")
        
        def run_query():
            try:
                # Run via subprocess
                cmd = [sys.executable, "database_admin.py", "query", f'"{query}"']
                result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                
                self.append_output(result.stdout, "info")
                if result.stderr:
                    self.append_output(result.stderr, "error")
                
                if result.returncode == 0:
                    self.append_output("Query executed successfully\n", "success")
                else:
                    self.append_output(f"Query failed with code {result.returncode}\n", "error")
                
                # Hide query frame
                self.root.after(0, self.hide_query_frame)
                    
            except Exception as e:
                self.append_output(f"Error executing query: {str(e)}\n", "error")
        
        threading.Thread(target=run_query, daemon=True).start()
    
    def hide_query_frame(self):
        """Hide query input frame."""
        self.query_frame.pack_forget()
    
    def db_repair(self):
        """Repair database."""
        self.append_output("Repairing database...\n", "info")
        
        def run_repair():
            try:
                # Run via subprocess
                cmd = [sys.executable, "database_admin.py", "repair"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                self.append_output(result.stdout, "info")
                if result.stderr:
                    self.append_output(result.stderr, "error")
                
                if result.returncode == 0:
                    self.append_output("Database repair completed successfully\n", "success")
                else:
                    self.append_output(f"Repair failed with code {result.returncode}\n", "error")
                    
            except Exception as e:
                self.append_output(f"Error repairing database: {str(e)}\n", "error")
        
        threading.Thread(target=run_repair, daemon=True).start()
    
    def clear_database_contents(self):
        """Clear all data from database tables."""
        if not messagebox.askyesno("Confirm", "This will delete ALL data from the database. Continue?"):
            return
        
        self.append_output("Clearing database contents...\n", "warning")
        
        def run_clear():
            try:
                db_path = self.db_path_var.get()
                if not MODULES_AVAILABLE:
                    self.append_output("Database module not available\n", "error")
                    return
                
                db = DatabaseManager(db_path)
                db.connect()
                
                if db.conn is None or db.cursor is None:
                    self.append_output("Failed to connect to database\n", "error")
                    return
                
                cursor = db.cursor
                
                # List of tables to clear (excluding sqlite_sequence)
                tables = [
                    'documents', 'ocr_results', 'extracted_data', 
                    'rename_operations', 'processing_logs', 'error_logs', 'audit_log'
                ]
                
                # Disable foreign keys to allow deletion in any order
                cursor.execute("PRAGMA foreign_keys = OFF")
                
                for table in tables:
                    try:
                        cursor.execute(f"DELETE FROM {table}")
                        self.append_output(f"  Cleared {table} table\n", "info")
                    except Exception as e:
                        self.append_output(f"  Warning: Could not clear {table}: {str(e)}\n", "warning")
                
                # Reset autoincrement sequences
                try:
                    cursor.execute("DELETE FROM sqlite_sequence")
                except:
                    pass  # sqlite_sequence may not exist
                
                # Re-enable foreign keys
                cursor.execute("PRAGMA foreign_keys = ON")
                
                db.conn.commit()
                db.close()
                
                self.append_output("Database contents cleared successfully\n", "success")
                
            except Exception as e:
                self.append_output(f"Error clearing database: {str(e)}\n", "error")
        
        threading.Thread(target=run_clear, daemon=True).start()
    
    def clear_ocr_output_folder(self):
        """Delete all files in the OCR output folder."""
        if not messagebox.askyesno("Confirm", "This will delete ALL files in the OCR output folder. Continue?"):
            return
        
        self.append_output("Clearing OCR output folder...\n", "warning")
        
        def run_clear():
            try:
                folder = Path("ocr-output")
                if folder.exists():
                    # Delete all files and subdirectories
                    for item in folder.iterdir():
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    self.append_output(f"Cleared OCR output folder: {folder}\n", "success")
                else:
                    self.append_output(f"OCR output folder does not exist: {folder}\n", "warning")
                    
            except Exception as e:
                self.append_output(f"Error clearing OCR output folder: {str(e)}\n", "error")
        
        threading.Thread(target=run_clear, daemon=True).start()
    
    def clear_renamed_folder(self):
        """Delete all files in the renamed folder."""
        if not messagebox.askyesno("Confirm", "This will delete ALL files in the renamed folder. Continue?"):
            return
        
        self.append_output("Clearing renamed folder...\n", "warning")
        
        def run_clear():
            try:
                folder = Path("renamed")
                if folder.exists():
                    # Delete all files and subdirectories
                    for item in folder.iterdir():
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    self.append_output(f"Cleared renamed folder: {folder}\n", "success")
                else:
                    self.append_output(f"Renamed folder does not exist: {folder}\n", "warning")
                    
            except Exception as e:
                self.append_output(f"Error clearing renamed folder: {str(e)}\n", "error")
        
        threading.Thread(target=run_clear, daemon=True).start()
    
    def launch_validation_gui(self):
        """Launch the validation GUI."""
        self.append_output("Launching Validation GUI...\n", "info")
        self.validation_status_var.set("Launching Validation GUI...")
        
        def run_validation():
            try:
                # Import and run validation GUI
                from validation_gui import main as validation_main
                import sys
                
                # We need to run validation GUI in a separate process
                # because tkinter doesn't support multiple mainloops in same process
                cmd = [sys.executable, "validation_gui.py"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.append_output("Validation GUI closed\n", "info")
                else:
                    if result.stderr:
                        self.append_output(f"Validation GUI error: {result.stderr}\n", "error")
                
                self.validation_status_var.set("Validation GUI closed")
                
            except Exception as e:
                self.append_output(f"Error launching Validation GUI: {str(e)}\n", "error")
                self.validation_status_var.set(f"Error: {str(e)}")
        
        threading.Thread(target=run_validation, daemon=True).start()
    
    def append_output(self, text, tag=None):
        """Append text to output area in a thread-safe way."""
        self.output_queue.put((text, tag))
    
    def monitor_output_queue(self):
        """Monitor output queue and update text widget."""
        try:
            while True:
                text, tag = self.output_queue.get_nowait()
                self.output_text.insert(tk.END, text, tag)
                self.output_text.see(tk.END)
                self.output_text.update_idletasks()
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.monitor_output_queue)
    
    def clear_output(self):
        """Clear the output text area."""
        self.output_text.delete("1.0", tk.END)

def main():
    """Main entry point."""
    root = tk.Tk()
    app = NotaryProcessingGUI(root)
    
    # Handle window close
    def on_closing():
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()