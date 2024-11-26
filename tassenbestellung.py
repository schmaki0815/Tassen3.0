import tkinter as tk
from tkinter import ttk, messagebox
import logging
from database import db
from utils.logger import setup_logger
from datetime import datetime
from utils.inventory_sync import InventorySync
from utils.print_manager import PrintManager

logger = setup_logger()

class CupOrderApp:
    def __init__(self, parent_frame=None):
        self.root = parent_frame or tk.Tk()
        if isinstance(self.root, tk.Tk):
            self.root.title("Tassenbestellung")
            self.root.geometry("800x600")

        self.setup_variables()
        self.setup_database()
        self.setup_ui()
        self.load_products()

    def setup_variables(self):
        self.customer_id = tk.StringVar()
        self.first_name = tk.StringVar()
        self.last_name = tk.StringVar()

    def setup_database(self):
        create_tables_query = '''
            CREATE TABLE IF NOT EXISTS cup_orders (
                id BIGSERIAL PRIMARY KEY,
                kundennummer VARCHAR(50) NOT NULL,
                product_name VARCHAR(100) NOT NULL,
                quantity INTEGER NOT NULL,
                color VARCHAR(50),
                size VARCHAR(50),
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute(create_tables_query)
            conn.commit()
        except Exception as e:
            logger.error(f"Error creating table: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def setup_ui(self):
        # Customer Information Frame
        customer_frame = ttk.LabelFrame(self.root, text="Kundendaten")
        customer_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(customer_frame, text="Kundennummer:").grid(row=0, column=0, padx=5, pady=2)
        ttk.Entry(customer_frame, textvariable=self.customer_id).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(customer_frame, text="Vorname:").grid(row=1, column=0, padx=5, pady=2)
        ttk.Entry(customer_frame, textvariable=self.first_name).grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(customer_frame, text="Nachname:").grid(row=2, column=0, padx=5, pady=2)
        ttk.Entry(customer_frame, textvariable=self.last_name).grid(row=2, column=1, padx=5, pady=2)

        # Products Frame
        products_frame = ttk.LabelFrame(self.root, text="Verfügbare Produkte")
        products_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Product List
        columns = ("product_name", "color", "size", "amount")
        self.product_tree = ttk.Treeview(products_frame, columns=columns, show="headings")
        
        self.product_tree.heading("product_name", text="Produkt")
        self.product_tree.heading("color", text="Farbe")
        self.product_tree.heading("size", text="Größe")
        self.product_tree.heading("amount", text="Verfügbar")

        self.product_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(products_frame, orient="vertical", command=self.product_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.product_tree.configure(yscrollcommand=scrollbar.set)

        # Order Table Frame
        order_frame = ttk.LabelFrame(self.root, text="Aktuelle Bestellung")
        order_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Order Table
        columns = ("product_name", "quantity", "color", "size")
        self.order_table = ttk.Treeview(order_frame, columns=columns, show="headings")
        
        self.order_table.heading("product_name", text="Produkt")
        self.order_table.heading("quantity", text="Menge")
        self.order_table.heading("color", text="Farbe")
        self.order_table.heading("size", text="Größe")

        self.order_table.pack(side="left", fill="both", expand=True)
        order_scrollbar = ttk.Scrollbar(order_frame, orient="vertical", command=self.order_table.yview)
        order_scrollbar.pack(side="right", fill="y")
        self.order_table.configure(yscrollcommand=order_scrollbar.set)

        # Buttons Frame
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(button_frame, text="Zur Bestellung Hinzufügen", 
                  command=self.add_to_order).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Von Bestellung Entfernen", 
                  command=self.remove_from_order).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Bestellung Speichern", 
                  command=self.save_order).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Neue Bestellung", 
                  command=self.new_order).pack(side="left", padx=5)

        # Bind double-click event for product selection and history view
        self.product_tree.bind("<Double-1>", self.on_product_double_click)

    def load_products(self):
        """Load available products from database"""
        try:
            query = '''
                SELECT product_name, color, size, amount 
                FROM charges 
                WHERE amount > 0
                ORDER BY product_name, color, size
            '''
            products = db.execute_query(query, fetch=True)
            
            # Clear existing items
            for item in self.product_tree.get_children():
                self.product_tree.delete(item)
            
            # Insert new items
            if products:
                for product in products:
                    self.product_tree.insert("", "end", values=product)
                    
            logger.info(f"Retrieved {len(products) if products else 0} products from database")
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            messagebox.showerror("Fehler", "Fehler beim Laden der Produkte")

    def check_stock(self, product_name, quantity, color, size):
        """Check if enough stock is available"""
        try:
            query = '''
                SELECT amount 
                FROM charges 
                WHERE product_name = %s 
                AND color = %s 
                AND size = %s 
                AND amount >= %s
            '''
            result = db.execute_query(query, (product_name, color, size, quantity), fetch=True)
            return bool(result)
        except Exception as e:
            logger.error(f"Error checking stock: {e}")
            return False

    def update_inventory(self, product_name, quantity, color, size):
        """Update inventory after order"""
        try:
            query = '''
                UPDATE charges 
                SET amount = amount - %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE product_name = %s 
                AND color = %s 
                AND size = %s 
                AND amount >= %s
            '''
            result = db.execute_query(
                query, 
                (quantity, product_name, color, size, quantity)
            )
            return True
        except Exception as e:
            logger.error(f"Error updating inventory: {e}")
            return False

    def save_order(self):
        if not self.customer_id.get():
            messagebox.showwarning("Warnung", "Bitte Kundennummer eingeben")
            return False

        items = self.order_table.get_children()
        if not items:
            messagebox.showwarning("Warnung", "Keine Produkte in der Bestellung")
            return False

        try:
            conn = db.get_connection()
            cur = conn.cursor()
            
            # Begin transaction
            cur.execute("BEGIN")
            
            for item in items:
                values = self.order_table.item(item)["values"]
                product_name, quantity, color, size = values
                
                # Save order
                insert_query = '''
                    INSERT INTO cup_orders 
                    (kundennummer, product_name, quantity, color, size)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                '''
                cur.execute(
                    insert_query, 
                    (self.customer_id.get(), product_name, quantity, color, size)
                )
                
                # Update inventory
                update_query = '''
                    UPDATE charges 
                    SET amount = amount - %s,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE product_name = %s 
                    AND color = %s 
                    AND size = %s
                    AND amount >= %s
                    RETURNING amount
                '''
                cur.execute(
                    update_query,
                    (quantity, product_name, color, size, quantity)
                )
                
                update_result = cur.fetchone()
                if not update_result:
                    cur.execute("ROLLBACK")
                    messagebox.showerror("Fehler", f"Nicht genügend Bestand für {product_name}")
                    return False
            
            # Commit transaction
            conn.commit()
            
            # Refresh product list after successful order
            self.load_products()
            
            messagebox.showinfo("Erfolg", "Bestellung erfolgreich gespeichert")
            return True
            
        except Exception as e:
            if conn:
                try:
                    cur.execute("ROLLBACK")
                    conn.rollback()
                except:
                    pass
            logger.error(f"Error saving order: {e}")
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Bestellung: {str(e)}")
            return False
        finally:
            if conn:
                conn.close()

    def add_to_order(self):
        """Add selected product to order"""
        selected = self.product_tree.selection()
        if not selected:
            messagebox.showwarning("Warnung", "Bitte wählen Sie ein Produkt aus")
            return

        item = selected[0]
        values = self.product_tree.item(item)["values"]
        product_name, color, size, available = values

        # Show quantity dialog
        quantity = self.show_quantity_dialog(int(available))
        if quantity:
            self.order_table.insert("", "end", values=(product_name, quantity, color, size))
            logger.info(f"Added {quantity} of {product_name} to order")

    def show_quantity_dialog(self, max_amount):
        """Show dialog for quantity input"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Menge eingeben")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Menge eingeben:").pack(pady=10)
        quantity_var = tk.StringVar(value="1")
        quantity_entry = ttk.Entry(dialog, textvariable=quantity_var)
        quantity_entry.pack(pady=5)

        def validate_and_close():
            try:
                amount = int(quantity_var.get())
                if 0 < amount <= max_amount:
                    dialog.result = amount
                    dialog.destroy()
                else:
                    messagebox.showwarning("Ungültige Menge", 
                                       f"Bitte geben Sie eine Menge zwischen 1 und {max_amount} ein.")
            except ValueError:
                messagebox.showwarning("Fehler", "Bitte geben Sie eine gültige Zahl ein.")

        ttk.Button(dialog, text="OK", command=validate_and_close).pack(pady=10)
        
        dialog.geometry("+%d+%d" % (self.root.winfo_x() + 100, 
                                self.root.winfo_y() + 100))
        
        dialog.result = None
        dialog.wait_window()
        return dialog.result

    def remove_from_order(self):
        """Remove selected product from order"""
        selected = self.order_table.selection()
        if not selected:
            messagebox.showwarning("Warnung", "Bitte wählen Sie ein Produkt aus der Bestellung aus")
            return
            
        for item in selected:
            self.order_table.delete(item)

    def new_order(self):
        """Clear all fields for new order"""
        self.customer_id.set("")
        self.first_name.set("")
        self.last_name.set("")
        
        for item in self.order_table.get_children():
            self.order_table.delete(item)
            
        self.load_products()
        logger.info("New order initialized")

    def show_product_history(self, product_name, color, size):
        """Display order history for a specific product"""
        history_window = tk.Toplevel(self.root)
        history_window.title(f"Bestellhistorie: {product_name}")
        history_window.geometry("600x400")

        # Create history view
        columns = ("order_date", "kundennummer", "quantity")
        history_tree = ttk.Treeview(history_window, columns=columns, show="headings")
        
        history_tree.heading("order_date", text="Bestelldatum")
        history_tree.heading("kundennummer", text="Kundennummer")
        history_tree.heading("quantity", text="Menge")

        history_tree.column("order_date", width=150)
        history_tree.column("kundennummer", width=150)
        history_tree.column("quantity", width=100)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(history_window, orient="vertical", command=history_tree.yview)
        history_tree.configure(yscrollcommand=scrollbar.set)

        # Layout
        history_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Fetch and display history
        try:
            query = '''
                SELECT 
                    order_date,
                    kundennummer,
                    quantity
                FROM cup_orders 
                WHERE product_name = %s 
                AND color = %s 
                AND size = %s
                ORDER BY order_date DESC
            '''
            history = db.execute_query(query, (product_name, color, size), fetch=True)
            
            if history:
                for record in history:
                    formatted_date = record[0].strftime('%Y-%m-%d %H:%M') if record[0] else 'N/A'
                    history_tree.insert("", "end", values=(formatted_date, record[1], record[2]))
            else:
                history_tree.insert("", "end", values=("Keine Bestellhistorie verfügbar", "", ""))

        except Exception as e:
            logger.error(f"Error fetching product history: {e}")
            messagebox.showerror("Fehler", "Fehler beim Laden der Bestellhistorie")

    def on_product_double_click(self, event):
        """Handle double click on product - show history or add to order"""
        selected = self.product_tree.selection()
        if not selected:
            return

        item = selected[0]
        values = self.product_tree.item(item)["values"]
        product_name, color, size, _ = values

        # Create a dialog to choose action
        dialog = tk.Toplevel(self.root)
        dialog.title("Aktion auswählen")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Was möchten Sie tun?").pack(pady=10)

        ttk.Button(dialog, text="Zur Bestellung hinzufügen", 
                  command=lambda: [dialog.destroy(), self.add_to_order()]).pack(pady=5)
        ttk.Button(dialog, text="Bestellhistorie anzeigen", 
                  command=lambda: [dialog.destroy(), self.show_product_history(product_name, color, size)]).pack(pady=5)
        ttk.Button(dialog, text="Abbrechen", 
                  command=dialog.destroy).pack(pady=5)

if __name__ == "__main__":
    app = CupOrderApp()
    app.root.mainloop()
