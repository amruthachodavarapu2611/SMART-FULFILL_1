from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from backend.database import get_connection, initialize_database
from backend.inventory_engine import (
    calculate_available_stock,
    get_stock_status,
    reorder_recommendation,
    allocate_inventory,
    detect_bottlenecks,
    calculate_fulfillment_metrics,
    get_stock_health_score
)
from backend.decision_engine import (
    prioritize_order,
    resolve_inventory_conflict,
    recommend_expedited_action
)

app = Flask(__name__)
app.secret_key = "smart_warehouse_secret"

initialize_database()


# ================================
# DASHBOARD & HOME
# ================================

@app.route("/")
def dashboard():
    """Main dashboard with KPIs and order queue"""
    connection = get_connection()
    cursor = connection.cursor()

    # Get KPI data
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM orders WHERE status IN ('PENDING', 'ALLOCATED', 'PICKING', 'PACKING')")
    pending_orders = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM products WHERE current_stock <= reorder_level")
    low_stock = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM products WHERE current_stock = 0")
    out_of_stock = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM exceptions WHERE status = 'OPEN'")
    open_exceptions = cursor.fetchone()[0]

    # Get order status breakdown
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM orders
        GROUP BY status
    """)
    status_breakdown = {row[0]: row[1] for row in cursor.fetchall()}

    # Get priority queue (top 10 urgent orders)
    cursor.execute("""
        SELECT order_id, product_id, quantity, priority_level, status, priority_score
        FROM orders
        ORDER BY priority_score DESC
        LIMIT 10
    """)
    priority_queue = cursor.fetchall()

    # Calculate health score
    cursor.execute(
        "SELECT AVG(current_stock * 1.0 / (reorder_level + 1)) FROM products")
    health_metric = cursor.fetchone()[0] or 0
    health_score = min(100, int(health_metric * 50))

    # Calculate fulfillment rate
    cursor.execute(
        "SELECT COUNT(*) FROM orders WHERE status IN ('SHIPPED', 'DELIVERED')")
    fulfilled = cursor.fetchone()[0]
    fulfillment_rate = int((fulfilled / max(total_orders, 1)) * 100)

    connection.close()

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_orders=total_orders,
        pending_orders=pending_orders,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        open_exceptions=open_exceptions,
        status_breakdown=status_breakdown,
        priority_queue=priority_queue,
        health_score=health_score,
        fulfillment_rate=fulfillment_rate
    )


# ================================
# INVENTORY MANAGEMENT
# ================================

@app.route("/inventory")
def inventory():
    """Display inventory status by product"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    inventory_data = []
    for product in products:
        available = calculate_available_stock(
            product["current_stock"],
            product["reserved_stock"],
            product["damaged_stock"]
        )
        status = get_stock_status(
            product["current_stock"],
            product["reorder_level"],
            available
        )
        health = get_stock_health_score(
            available,
            product["reorder_level"],
            product["average_daily_demand"]
        )

        reorder_data = reorder_recommendation(
            product["current_stock"],
            product["reorder_level"],
            product["average_daily_demand"]
        )

        inventory_data.append({
            "product": product,
            "available": available,
            "status": status,
            "health_score": health,
            "reorder": reorder_data
        })

    connection.close()

    return render_template("inventory.html", inventory=inventory_data)


# ================================
# ORDER MANAGEMENT
# ================================

@app.route("/orders")
def orders():
    """Display all orders with filtering options"""
    connection = get_connection()
    cursor = connection.cursor()

    # Get filter parameters
    status_filter = request.args.get("status", "")
    priority_filter = request.args.get("priority", "")

    query = "SELECT * FROM orders WHERE 1=1"
    params = []

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    if priority_filter:
        query += " AND priority_level = ?"
        params.append(priority_filter)

    query += " ORDER BY priority_score DESC"

    cursor.execute(query, params)
    orders_list = cursor.fetchall()

    connection.close()

    return render_template(
        "orders.html",
        orders=orders_list,
        status_filter=status_filter,
        priority_filter=priority_filter
    )


@app.route("/place-order", methods=["GET", "POST"])
def place_order():
    """Create a new order"""
    if request.method == "GET":
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT product_id, name FROM products")
        products = cursor.fetchall()
        connection.close()

        return render_template("place_order.html", products=products)

    # POST request - create order
    product_id = request.form.get("product_id")
    quantity = int(request.form.get("quantity", 1))
    priority = request.form.get("priority", "MEDIUM")
    hours = int(request.form.get("hours", 24))

    # Calculate priority score
    order_data = {
        "order_id": order_id,
        "customer": customer,
        "product_id": product_id,
        "quantity": quantity,
        "priority": priority,
        "hours_to_deadline": hours_to_deadline
    }


priority_result = prioritize_order(order_data)
priority_score = priority_result["priority_score"]
priority_level = priority_result["priority_level"]

connection = get_connection()
cursor = connection.cursor()

# Generate order ID
cursor.execute("SELECT COUNT(*) FROM orders")
order_num = cursor.fetchone()[0] + 1
order_id = f"ORD{order_num:05d}"

cursor.execute("""
        INSERT INTO orders
        (order_id, product_id, quantity, priority, hours_to_deadline,
         priority_score, priority_level, status, allocated_quantity)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', 0)
    """, (order_id, product_id, quantity, priority, hours, priority_score, priority_level))

 connection.commit()
connection.close()

    flash(f"Order {order_id} created successfully!", "success")

    return redirect(url_for("orders"))


@app.route("/allocate/<order_id>", methods=["POST"])
def allocate(order_id):
    """Allocate inventory to an order"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()

    cursor.execute("SELECT * FROM products WHERE product_id = ?",
                   (order["product_id"],))
    product = cursor.fetchone()

    available = calculate_available_stock(
        product["current_stock"],
        product["reserved_stock"],
        product["damaged_stock"]
    )

    # Determine allocation
    if available >= order["quantity"]:
        decision = "FULLY_ALLOCATED"
        allocated_qty = order["quantity"]
    elif available > 0:
        decision = "PARTIALLY_ALLOCATED"
        allocated_qty = available
    else:
        decision = "BACKORDERED"
        allocated_qty = 0

    # Update order
    cursor.execute("""
        UPDATE orders
        SET status = ?, allocated_quantity = ?
        WHERE order_id = ?
    """, (decision, allocated_qty, order_id))

    # Log allocation
    cursor.execute("""
        INSERT INTO allocation_log
        (order_id, product_id, quantity_requested, quantity_allocated,
         allocation_decision, reason, allocated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        order_id, order["product_id"], order["quantity"], allocated_qty,
        decision, f"{decision}: {allocated_qty} of {order['quantity']} units"
    ))

    # Update reserved stock
    cursor.execute("""
        UPDATE products
        SET reserved_stock = reserved_stock + ?
        WHERE product_id = ?
    """, (allocated_qty, order["product_id"]))

    connection.commit()
    connection.close()

    flash(f"Order {order_id} allocated: {decision}")
    return redirect(url_for("orders"))


@app.route("/batch-allocate", methods=["GET", "POST"])
def batch_allocate():
    """Allocate inventory across multiple orders"""
    if request.method == "GET":
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT DISTINCT product_id FROM orders WHERE status = 'PENDING'")
        products = [row[0] for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM products")
        product_data = {row["product_id"]: row for row in cursor.fetchall()}

        connection.close()

        return render_template(
            "batch_allocate.html",
            products=products,
            product_data=product_data
        )

    # POST - Execute batch allocation
    product_id = request.form.get("product_id")

    connection = get_connection()
    cursor = connection.cursor()

    # Get all pending orders for this product
    cursor.execute("""
        SELECT * FROM orders
        WHERE product_id = ? AND status = 'PENDING'
        ORDER BY priority_score DESC
    """, (product_id,))
    pending_orders = cursor.fetchall()

    # Get available stock
    cursor.execute(
        "SELECT * FROM products WHERE product_id = ?", (product_id,))
    product = cursor.fetchone()

    available = calculate_available_stock(
        product["current_stock"],
        product["reserved_stock"],
        product["damaged_stock"]
    )

    # Allocate by priority
    remaining = available
    for order in pending_orders:
        if remaining >= order["quantity"]:
            decision = "FULLY_ALLOCATED"
            allocated = order["quantity"]
        elif remaining > 0:
            decision = "PARTIALLY_ALLOCATED"
            allocated = remaining
        else:
            decision = "BACKORDERED"
            allocated = 0

        cursor.execute("""
            UPDATE orders SET status = ?, allocated_quantity = ?
            WHERE order_id = ?
        """, (decision, allocated, order["order_id"]))

        cursor.execute("""
            INSERT INTO allocation_log
            (order_id, product_id, quantity_requested, quantity_allocated,
             allocation_decision, reason, allocated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            order["order_id"], product_id, order["quantity"], allocated,
            decision, f"{decision}: {allocated} units allocated"
        ))

        remaining -= allocated

    connection.commit()
    connection.close()

    flash(f"Batch allocation completed for product {product_id}")
    return redirect(url_for("batch_allocate"))


# ================================
# PICKING WORKFLOW
# ================================

@app.route("/picking")
def picking():
    """Display picking queue"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT o.*, p.location, p.name as product_name
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.status IN ('FULLY_ALLOCATED', 'PARTIALLY_ALLOCATED')
        ORDER BY o.priority_score DESC
    """)

    picking_orders = cursor.fetchall()
    connection.close()

    return render_template("picking.html", picking_orders=picking_orders)


@app.route("/picking/<order_id>/start", methods=["POST"])
def start_picking(order_id):
    """Start picking operation"""
    picker_name = request.form.get("picker_name", "Unassigned")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO picking (order_id, assigned_to, status, started_at)
        VALUES (?, ?, 'IN_PROGRESS', CURRENT_TIMESTAMP)
    """, (order_id, picker_name))

    cursor.execute(
        "UPDATE orders SET status = 'PICKING' WHERE order_id = ?", (order_id,))

    connection.commit()
    connection.close()

    flash(f"Picking started for {order_id} by {picker_name}")
    return redirect(url_for("picking"))


@app.route("/picking/<order_id>/complete", methods=["POST"])
def complete_picking(order_id):
    """Complete picking operation"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE picking SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (order_id,))

    cursor.execute(
        "UPDATE orders SET status = 'PACKING' WHERE order_id = ?", (order_id,))

    connection.commit()
    connection.close()

    flash(f"Picking completed for {order_id}")
    return redirect(url_for("picking"))


# ================================
# PACKING WORKFLOW
# ================================

@app.route("/packing")
def packing():
    """Display packing queue"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT o.*, p.name as product_name
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.status = 'PICKING'
        ORDER BY o.priority_score DESC
    """)

    packing_orders = cursor.fetchall()
    connection.close()

    return render_template("packing.html", packing_orders=packing_orders)


@app.route("/packing/<order_id>/start", methods=["POST"])
def start_packing(order_id):
    """Start packing operation"""
    packer_name = request.form.get("packer_name", "Unassigned")
    weight = float(request.form.get("weight", 0))
    dimensions = request.form.get("dimensions", "")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO packing (order_id, assigned_to, weight, dimensions, status, started_at)
        VALUES (?, ?, ?, ?, 'IN_PROGRESS', CURRENT_TIMESTAMP)
    """, (order_id, packer_name, weight, dimensions))

    cursor.execute(
        "UPDATE orders SET status = 'PACKING' WHERE order_id = ?", (order_id,))

    connection.commit()
    connection.close()

    flash(f"Packing started for {order_id}")
    return redirect(url_for("packing"))


@app.route("/packing/<order_id>/complete", methods=["POST"])
def complete_packing(order_id):
    """Complete packing operation"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE packing SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (order_id,))

    cursor.execute(
        "UPDATE orders SET status = 'QUALITY_CHECK' WHERE order_id = ?", (order_id,))

    connection.commit()
    connection.close()

    flash(f"Packing completed for {order_id}")
    return redirect(url_for("packing"))


# ================================
# QUALITY CONTROL
# ================================

@app.route("/quality-check")
def quality_check():
    """Display QC queue"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT o.*, p.name as product_name
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.status = 'PACKING'
        ORDER BY o.priority_score DESC
    """)

    qc_orders = cursor.fetchall()
    connection.close()

    return render_template("quality_check.html", qc_orders=qc_orders)


@app.route("/quality-check/<order_id>/start", methods=["POST"])
def start_qc(order_id):
    """Start QC inspection"""
    inspector = request.form.get("inspector", "Unassigned")
    defects = int(request.form.get("defects", 0))
    notes = request.form.get("notes", "")
    passed = request.form.get("passed") == "1"

    connection = get_connection()
    cursor = connection.cursor()

    # Create QC record
    cursor.execute("""
        INSERT INTO quality_check
        (order_id, inspector, defects_found, defect_notes, passed, checked_at, status)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'COMPLETED')
    """, (order_id, inspector, defects, notes, 1 if passed else 0))

    if passed:
        # Pass - move to ready to ship
        cursor.execute(
            "UPDATE orders SET status = 'READY_TO_SHIP' WHERE order_id = ?", (order_id,))
        flash(f"QC passed for {order_id}")
    else:
        # Fail - create exception
        cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        order = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) FROM exceptions")
        exc_num = cursor.fetchone()[0] + 1
        exc_id = f"EXC{exc_num:05d}"

        cursor.execute("""
            INSERT INTO exceptions
            (exception_id, order_id, product_id, exception_type, severity, description,
             status, created_at)
            VALUES (?, ?, ?, 'QC_FAILED', 'HIGH', ?, 'OPEN', CURRENT_TIMESTAMP)
        """, (exc_id, order_id, order["product_id"],
              f"QC inspection found {defects} defects: {notes}"))

        cursor.execute(
            "UPDATE orders SET status = 'QC_FAILED', exception_id = ? WHERE order_id = ?",
            (exc_id,
             order_id))

        flash(f"QC failed for {order_id} - Exception {exc_id} created")

    connection.commit()
    connection.close()

    return redirect(url_for("quality_check"))


# ================================
# EXCEPTIONS
# ================================

@app.route("/exceptions")
def exceptions():
    """Display exceptions"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM exceptions WHERE status = 'OPEN' ORDER BY severity DESC")
    open_exc = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM exceptions WHERE status = 'RESOLVED' ORDER BY resolved_at DESC LIMIT 20")
    resolved_exc = cursor.fetchall()

    connection.close()

    return render_template(
        "exceptions.html",
        open_exceptions=open_exc,
        resolved_exceptions=resolved_exc
    )


@app.route("/exceptions/<exc_id>/resolve", methods=["POST"])
def resolve_exception(exc_id):
    """Resolve an exception"""
    assigned_to = request.form.get("assigned_to", "")
    resolution = request.form.get("resolution", "")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE exceptions
        SET status = 'RESOLVED', assigned_to = ?, resolution = ?, resolved_at = CURRENT_TIMESTAMP
        WHERE exception_id = ?
    """, (assigned_to, resolution, exc_id))

    connection.commit()
    connection.close()

    flash(f"Exception {exc_id} resolved")
    return redirect(url_for("exceptions"))


# ================================
# ANALYTICS
# ================================

@app.route("/analytics")
def analytics():
    """Display analytics and insights"""
    connection = get_connection()
    cursor = connection.cursor()

    # Stock metrics
    cursor.execute("SELECT SUM(current_stock) FROM products")
    total_stock = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(reserved_stock) FROM products")
    reserved_stock = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(damaged_stock) FROM products")
    damaged_stock = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT COUNT(*) FROM products WHERE current_stock <= reorder_level")
    low_stock_items = cursor.fetchone()[0]

    # Fulfillment metrics
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM orders WHERE status IN ('SHIPPED', 'DELIVERED')")
    fulfilled_orders = cursor.fetchone()[0]

    fulfillment_rate = int((fulfilled_orders / max(total_orders, 1)) * 100)

    # Get order status breakdown
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM orders
        GROUP BY status
        ORDER BY count DESC
    """)
    status_breakdown = cursor.fetchall()

    # Get risk products
    cursor.execute("""
        SELECT product_id, name, current_stock, reorder_level
        FROM products
        WHERE current_stock < reorder_level * 0.5
        ORDER BY current_stock ASC
        LIMIT 5
    """)
    risk_products = cursor.fetchall()

    connection.close()

    return render_template(
        "analytics.html",
        total_stock=total_stock,
        reserved_stock=reserved_stock,
        damaged_stock=damaged_stock,
        low_stock_items=low_stock_items,
        total_orders=total_orders,
        fulfilled_orders=fulfilled_orders,
        fulfillment_rate=fulfillment_rate,
        status_breakdown=status_breakdown,
        risk_products=risk_products
    )


# ================================
# ERROR HANDLERS
# ================================

@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404


@app.errorhandler(500)
def server_error(error):
    return f"Server error: {error}", 500


if __name__ == "__main__":
    app.run(debug=True)
