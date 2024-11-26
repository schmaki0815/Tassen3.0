import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from datetime import datetime
import logging
from database import db
from utils.logger import setup_logger
from utils.barcode_handler import BarcodeHandler
from utils.pdf_generator import PDFGenerator
from config import WINDOW_SIZES, NAS_BASE_PATH

logger = setup_logger()
barcode_handler = BarcodeHandler()

class OrderApp:
    def __init__(self, parent_frame=None):
        self.root = parent_frame or tk.Tk()
        if isinstance(self.root, tk.Tk):
            self.root.title("Bestellverwaltung - Kundendaten")
            self.root.geometry(WINDOW_SIZES['bestellprogramm'])

        try:
            # Überprüfe ob Tabelle existiert
            test_query = """
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public' 
                    AND tablename = 'customers'
                );
            """
            result = db.execute_query(test_query, fetch=True)
            if not result or not result[0][0]:  # Tabelle existiert nicht
                # Erstelle Tabelle falls nicht vorhanden
                create_table_query = '''
                    CREATE TABLE IF NOT EXISTS customers (
                        kundennummer VARCHAR PRIMARY KEY,
                        vorname VARCHAR,
                        nachname VARCHAR,
                        bestellnummer VARCHAR UNIQUE,
                        quadratmeter NUMERIC,
                        dateien INTEGER,
                        barcode VARCHAR
                    )
                '''
                db.execute_query(create_table_query)
            logger.info("Database initialization successful")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            messagebox.showerror("Fehler", "Datenbankfehler: Tabelle 'customers' konnte nicht erstellt werden")
            return

        # Initialize variables
        self.customer_id = tk.StringVar()
        self.first_name = tk.StringVar()
        self.last_name = tk.StringVar()
        self.order_number = tk.StringVar(value=self.generate_order_number())
        self.total_square_meters = tk.DoubleVar(value=0.0)
        self.file_list = []
        self.file_dimensions = {}

        self.setup_ui()
        self.create_order_details_window()

    def setup_ui(self):
        # Configure root window grid
        if isinstance(self.root, tk.Tk):  # Check if root is main window
            self.root.minsize(600, 400)
        
        # Customer Information Frame
        customer_frame = ttk.LabelFrame(self.root, text="Kundendaten", padding=10)
        customer_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Configure grid weights
        for i in range(4):  # For all rows
            customer_frame.grid_rowconfigure(i, weight=1)
        customer_frame.grid_columnconfigure(1, weight=1)

        # Customer ID
        ttk.Label(customer_frame, text="Kundennummer:").grid(row=0, column=0, sticky="w")
        customer_id_entry = ttk.Entry(customer_frame, textvariable=self.customer_id)
        customer_id_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        customer_id_entry.bind("<FocusOut>", self.auto_fill_customer)

        # First Name
        ttk.Label(customer_frame, text="Vorname:").grid(row=1, column=0, sticky="w")
        ttk.Entry(customer_frame, textvariable=self.first_name).grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        # Last Name
        ttk.Label(customer_frame, text="Nachname:").grid(row=2, column=0, sticky="w")
        ttk.Entry(customer_frame, textvariable=self.last_name).grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        # Order Number
        ttk.Label(customer_frame, text="Bestellnummer:").grid(row=3, column=0, sticky="w")
        ttk.Label(customer_frame, textvariable=self.order_number).grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # Buttons Frame
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(button_frame, text="Kundendaten Speichern", command=self.save_customer).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Kundendaten Laden", command=self.load_customer).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Kundenordner Erstellen", command=self.create_customer_folder).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Neue Bestellung", command=self.new_order).pack(side="left", padx=5)

    def create_order_details_window(self):
        self.order_window = tk.Toplevel(self.root)
        self.order_window.title("Bestellverwaltung - Bestelldetails")
        self.order_window.geometry("800x600")

        # Order Details Frame
        details_frame = ttk.LabelFrame(self.order_window, text="Bestellungsdetails", padding=10)
        details_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Total Square Meters
        ttk.Label(details_frame, text="Gesamt-Quadratmeter (QM):").pack(anchor="w")
        ttk.Label(details_frame, textvariable=self.total_square_meters).pack(anchor="w")

        # File Upload Section
        ttk.Button(details_frame, text="Dateien Hochladen", command=self.upload_files).pack(pady=10)
        
        # File List Frame
        self.file_list_frame = ttk.Frame(details_frame)
        self.file_list_frame.pack(fill="both", expand=True)

        # Buttons
        ttk.Button(self.order_window, text="Gesamtquadratmeter Berechnen", 
                  command=self.calculate_total).pack(fill="x", padx=10, pady=5)
        ttk.Button(self.order_window, text="Barcode & PDF Erstellen", 
                  command=self.generate_documents).pack(fill="x", padx=10, pady=5)

    def generate_order_number(self):
        year = datetime.now().year
        try:
            query = "SELECT COUNT(*) FROM customers WHERE bestellnummer ILIKE %s"
            result = db.execute_query(query, (f"PRFX-{year}%",), fetch=True)
            if result and len(result) > 0 and result[0]:
                count = result[0][0]
            else:
                count = 0
            return f"PRFX-{year}{count+1:03d}"
        except Exception as e:
            logger.error(f"Error generating order number: {e}")
            return f"PRFX-{year}001"  # Fallback

    def auto_fill_customer(self, event=None):
        if self.customer_id.get():
            self.load_customer()

    def save_customer(self):
        try:
            query = """
                INSERT INTO customers 
                (kundennummer, vorname, nachname, bestellnummer, quadratmeter)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (kundennummer) DO UPDATE
                SET vorname = %s, nachname = %s, bestellnummer = %s, quadratmeter = %s
            """
            # Values needed twice for INSERT and UPDATE parts
            params = (
                self.customer_id.get(),
                self.first_name.get(),
                self.last_name.get(),
                self.order_number.get(),
                self.total_square_meters.get(),
                # Repeat values for UPDATE part
                self.first_name.get(),
                self.last_name.get(),
                self.order_number.get(),
                self.total_square_meters.get()
            )
            db.execute_query(query, params)
            logger.info(f"Customer saved: {self.customer_id.get()}")
            messagebox.showinfo("Erfolg", "Kundendaten gespeichert")
        except Exception as e:
            logger.error(f"Error saving customer: {e}")
            messagebox.showerror("Fehler", "Fehler beim Speichern der Kundendaten")

    def load_customer(self):
        try:
            query = "SELECT * FROM customers WHERE kundennummer = %s"
            result = db.execute_query(query, (self.customer_id.get(),), fetch=True)
            if result:
                customer = result[0]
                self.first_name.set(customer[1])
                self.last_name.set(customer[2])
                self.order_number.set(customer[3])
                self.total_square_meters.set(customer[4] or 0.0)
                logger.info(f"Customer loaded: {self.customer_id.get()}")
            else:
                logger.warning(f"Customer not found: {self.customer_id.get()}")
                messagebox.showwarning("Warnung", "Kunde nicht gefunden")
        except Exception as e:
            logger.error(f"Error loading customer: {e}")
            messagebox.showerror("Fehler", "Fehler beim Laden der Kundendaten")

    def create_customer_folder(self):
        try:
            folder_path = os.path.join(NAS_BASE_PATH, self.customer_id.get())
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                logger.info(f"Customer folder created: {folder_path}")
                messagebox.showinfo("Erfolg", "Kundenordner erstellt")
            else:
                logger.info(f"Customer folder already exists: {folder_path}")
                messagebox.showinfo("Info", "Kundenordner existiert bereits")
        except Exception as e:
            logger.error(f"Error creating customer folder: {e}")
            messagebox.showerror("Fehler", "Fehler beim Erstellen des Kundenordners")

    def upload_files(self):
        files = filedialog.askopenfilenames(
            title="Dateien auswählen",
            filetypes=(("Alle Dateien", "*.*"),)
        )
        for file in files:
            self.add_file_to_list(file)

    def add_file_to_list(self, file):
        file_frame = ttk.Frame(self.file_list_frame)
        file_frame.pack(fill="x", pady=2)

        ttk.Label(file_frame, text=os.path.basename(file)).pack(side="left")
        
        width_var = tk.StringVar()
        height_var = tk.StringVar()
        quantity_var = tk.StringVar(value="1")

        ttk.Entry(file_frame, textvariable=width_var, width=10).pack(side="left", padx=5)
        ttk.Entry(file_frame, textvariable=height_var, width=10).pack(side="left", padx=5)
        ttk.Entry(file_frame, textvariable=quantity_var, width=5).pack(side="left", padx=5)

        self.file_dimensions[file] = (width_var, height_var, quantity_var)
        self.file_list.append(file)

    def calculate_total(self):
        total = 0.0
        for file, (width_var, height_var, quantity_var) in self.file_dimensions.items():
            try:
                width = float(width_var.get().replace(",", "."))
                height = float(height_var.get().replace(",", "."))
                quantity = int(quantity_var.get())
                area = (width * height / 10000) * quantity
                total += area
            except ValueError:
                logger.warning(f"Invalid dimensions for file: {file}")
                messagebox.showwarning("Warnung", f"Ungültige Maße für {os.path.basename(file)}")
                return

        self.total_square_meters.set(round(total, 3))
        self.save_customer()

    def generate_documents(self):
        try:
            from utils.print_manager import PrintManager
            
            save_dir = filedialog.askdirectory(title="Speicherort auswählen")
            if not save_dir:
                return

            customer_data = {
                'kundennummer': self.customer_id.get(),
                'vorname': self.first_name.get(),
                'nachname': self.last_name.get(),
                'bestellnummer': self.order_number.get(),
                'quadratmeter': self.total_square_meters.get()
            }
            
            order_data = [{'beschreibung': f"{width_var.get()}x{height_var.get()} ({quantity_var.get()}x)"} 
                         for file, (width_var, height_var, quantity_var) in self.file_dimensions.items()]

            # Generate PDF using PrintManager
            filename = PrintManager.print_order(order_data, customer_data)
            
            # Generate barcode
            barcode_data = f"{self.order_number.get()} QM:{self.total_square_meters.get()}"
            barcode_path = os.path.join(save_dir, f"{self.order_number.get()}_barcode.png")
            if barcode_handler.generate_barcode(barcode_data, barcode_path):
                logger.info(f"Documents generated for order: {self.order_number.get()}")
                messagebox.showinfo("Erfolg", "Dokumente wurden erstellt")
            else:
                raise Exception("Barcode generation failed")
        except Exception as e:
            logger.error(f"Error generating documents: {e}")
            messagebox.showerror("Fehler", "Fehler beim Erstellen der Dokumente")

    def new_order(self):
        self.customer_id.set("")
        self.first_name.set("")
        self.last_name.set("")
        self.order_number.set(self.generate_order_number())
        self.total_square_meters.set(0.0)
        self.file_list = []
        self.file_dimensions = {}
        for widget in self.file_list_frame.winfo_children():
            widget.destroy()

if __name__ == "__main__":
    app = OrderApp()
    app.root.mainloop()
