import sqlite3
import os

if os.environ.get("VERCEL"):
    DATABASE = "/tmp/warehouse.db"
else:
    DATABASE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "warehouse.db"
    )

def get_connection():

    connection = sqlite3.connect(DATABASE)

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():

    connection = get_connection()

    cursor = connection.cursor()

    # PRODUCTS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            product_id TEXT UNIQUE,

            name TEXT,

            category TEXT,

            location TEXT,

            current_stock INTEGER,

            reserved_stock INTEGER,

            damaged_stock INTEGER,

            reorder_level INTEGER,

            average_daily_demand INTEGER,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # ORDERS TABLE - Complete workflow tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            order_id TEXT UNIQUE,

            customer TEXT,

            product_id TEXT,

            quantity INTEGER,

            priority TEXT,

            hours_to_deadline INTEGER,

            priority_score INTEGER,

            priority_level TEXT,

            status TEXT,

            allocated_quantity INTEGER DEFAULT 0,

            fulfilled_quantity INTEGER DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # PICKING TABLE - Track picking operations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS picking (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            picking_id TEXT UNIQUE,

            order_id TEXT,

            product_id TEXT,

            quantity_to_pick INTEGER,

            quantity_picked INTEGER DEFAULT 0,

            assigned_picker TEXT,

            status TEXT,

            started_at TIMESTAMP,

            completed_at TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # PACKING TABLE - Track packing operations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS packing (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            packing_id TEXT UNIQUE,

            order_id TEXT,

            quantity_packed INTEGER DEFAULT 0,

            assigned_packer TEXT,

            status TEXT,

            weight REAL,

            dimensions TEXT,

            started_at TIMESTAMP,

            completed_at TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # QUALITY_CHECK TABLE - Track QC operations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quality_check (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            qc_id TEXT UNIQUE,

            order_id TEXT,

            packing_id TEXT,

            quantity_inspected INTEGER,

            defects_found INTEGER DEFAULT 0,

            status TEXT,

            inspector TEXT,

            notes TEXT,

            started_at TIMESTAMP,

            completed_at TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # SHIPMENT TABLE - Track dispatch
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            shipment_id TEXT UNIQUE,

            order_id TEXT,

            tracking_number TEXT,

            carrier TEXT,

            status TEXT,

            shipped_at TIMESTAMP,

            estimated_delivery TIMESTAMP,

            actual_delivery TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # EXCEPTIONS TABLE - Enhanced exception tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exceptions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            exception_id TEXT UNIQUE,

            exception_type TEXT,

            order_id TEXT,

            product_id TEXT,

            description TEXT,

            severity TEXT,

            status TEXT,

            assigned_to TEXT,

            resolution TEXT,

            resolved_at TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # ALLOCATION_LOG TABLE - Track allocation decisions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS allocation_log (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            log_id TEXT UNIQUE,

            order_id TEXT,

            product_id TEXT,

            requested_quantity INTEGER,

            allocated_quantity INTEGER,

            reason TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    connection.commit()

    connection.close()


def insert_sample_data():

    connection = get_connection()

    cursor = connection.cursor()

    # Check whether data already exists
    cursor.execute(
        "SELECT COUNT(*) FROM products"
    )

    product_count = cursor.fetchone()[0]

    if product_count == 0:

        products = [

            (
                "P001",
                "Laptop",
                "Electronics",
                "A01",
                7,
                0,
                0,
                5,
                2
            ),

            (
                "P002",
                "Wireless Mouse",
                "Accessories",
                "A02",
                25,
                3,
                1,
                8,
                4
            ),

            (
                "P003",
                "Keyboard",
                "Accessories",
                "A03",
                10,
                2,
                0,
                5,
                2
            ),

            (
                "P004",
                "Monitor",
                "Electronics",
                "B01",
                3,
                1,
                0,
                5,
                2
            ),

            (
                "P005",
                "USB Cable",
                "Accessories",
                "B02",
                0,
                0,
                0,
                10,
                5
            ),

            (
                "P006",
                "Headphones",
                "Accessories",
                "B03",
                18,
                2,
                2,
                6,
                3
            )

        ]

        cursor.executemany("""
            INSERT INTO products
            (
                product_id,
                name,
                category,
                location,
                current_stock,
                reserved_stock,
                damaged_stock,
                reorder_level,
                average_daily_demand
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, products)

    # Sample orders
    cursor.execute(
        "SELECT COUNT(*) FROM orders"
    )

    order_count = cursor.fetchone()[0]

    if order_count == 0:

        orders = [

            (
                "ORD001",
                "Customer A",
                "P001",
                10,
                "URGENT",
                1,
                90,
                "CRITICAL",
                "PENDING",
                0,
                0
            ),

            (
                "ORD002",
                "Customer B",
                "P001",
                5,
                "LOW",
                24,
                15,
                "LOW",
                "PENDING",
                0,
                0
            ),

            (
                "ORD003",
                "Customer C",
                "P002",
                4,
                "HIGH",
                4,
                60,
                "HIGH",
                "PENDING",
                0,
                0
            ),

            (
                "ORD004",
                "Customer D",
                "P004",
                2,
                "MEDIUM",
                10,
                25,
                "MEDIUM",
                "PENDING",
                0,
                0
            )

        ]

        cursor.executemany("""
            INSERT INTO orders
            (
                order_id,
                customer,
                product_id,
                quantity,
                priority,
                hours_to_deadline,
                priority_score,
                priority_level,
                status,
                allocated_quantity,
                fulfilled_quantity
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, orders)

    # Sample exceptions
    cursor.execute(
        "SELECT COUNT(*) FROM exceptions"
    )

    exception_count = cursor.fetchone()[0]

    if exception_count == 0:

        exceptions = [

            (
                "EXC001",
                "STOCKOUT",
                "ORD002",
                "P001",
                "Laptop stock insufficient for pending order",
                "HIGH",
                "OPEN",
                None,
                None,
                None
            ),

            (
                "EXC002",
                "DAMAGED ITEM",
                "ORD003",
                "P002",
                "1 wireless mouse marked as damaged",
                "MEDIUM",
                "OPEN",
                None,
                None,
                None
            ),

            (
                "EXC003",
                "MISSING ITEM",
                "ORD004",
                "P004",
                "1 monitor missing during picking",
                "HIGH",
                "OPEN",
                None,
                None,
                None
            )

        ]

        cursor.executemany("""
            INSERT INTO exceptions
            (
                exception_id,
                exception_type,
                order_id,
                product_id,
                description,
                severity,
                status,
                assigned_to,
                resolution,
                resolved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, exceptions)

    connection.commit()

    connection.close()
