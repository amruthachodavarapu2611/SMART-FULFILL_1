from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from backend.database import (
    initialize_database,
    insert_sample_data,
    get_connection
)

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


app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static"
)

app.secret_key = "smartfulfill-secret-key"


# --------------------------------
# INITIALIZE DATABASE
# --------------------------------

initialize_database()

insert_sample_data()


# --------------------------------
# DASHBOARD
# --------------------------------

@app.route("/")
def dashboard():

    connection = get_connection()

    cursor = connection.cursor()

    # Products
    cursor.execute(
        "SELECT * FROM products"
    )

    products = cursor.fetchall()

    # Orders
    cursor.execute(
        "SELECT * FROM orders"
    )

    orders = cursor.fetchall()

    # Exceptions
    cursor.execute(
        "SELECT * FROM exceptions"
    )

    exceptions = cursor.fetchall()

    # KPI calculations

    total_products = len(products)

    total_orders = len(orders)

    pending_orders = sum(
        1 for order in orders
        if order["status"] == "PENDING"
    )

    low_stock = 0

    out_of_stock = 0

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

        if status == "LOW STOCK":
            low_stock += 1

        elif status == "OUT OF STOCK":
            out_of_stock += 1

    open_exceptions = sum(
        1 for exception in exceptions
        if exception["status"] == "OPEN"
    )

    active_orders = sum(
        1 for order in orders
        if order["status"] in ["PENDING", "ALLOCATED", "PARTIALLY ALLOCATED"]
    )

    fulfillment_rate = round(
        (total_orders - pending_orders) / total_orders * 100
    ) if total_orders else 0

    health_score = max(
        0,
        100 - (low_stock * 12) - (out_of_stock * 20) - (open_exceptions * 8)
    )

    connection.close()

    return render_template(
        "dashboard.html",

        total_products=total_products,

        total_orders=total_orders,

        pending_orders=pending_orders,

        low_stock=low_stock,

        out_of_stock=out_of_stock,

        open_exceptions=open_exceptions,

        active_orders=active_orders,

        fulfillment_rate=fulfillment_rate,

        health_score=health_score,

        orders=orders
    )


# --------------------------------
# INVENTORY
# --------------------------------

@app.route("/inventory")
def inventory():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM products"
    )

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

        recommendation = reorder_recommendation(
            product["current_stock"],
            product["reorder_level"],
            product["average_daily_demand"]
        )

        inventory_data.append({

            "product": product,

            "available": available,

            "status": status,

            "reorder": recommendation

        })

    connection.close()

    return render_template(
        "inventory.html",
        inventory=inventory_data
    )


# --------------------------------
# ORDERS
# --------------------------------

@app.route("/orders")
def orders():

    connection = get_connection()

    cursor = connection.cursor()

    search = request.args.get("search", "").strip()

    if search:
        cursor.execute("""
            SELECT *
            FROM orders
            WHERE order_id LIKE ?
            OR customer LIKE ?
            OR product_id LIKE ?
            ORDER BY priority_score DESC
        """, (f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""
            SELECT *
            FROM orders
            ORDER BY priority_score DESC
        """)

    orders = cursor.fetchall()

    connection.close()

    return render_template(
        "orders.html",
        orders=orders,
        search=search
    )


@app.route("/place-order", methods=["GET", "POST"])
def place_order():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM products ORDER BY name"
    )
    products = cursor.fetchall()

    if request.method == "POST":

        customer = request.form.get("customer", "").strip()
        product_id = request.form.get("product_id")
        quantity = int(request.form.get("quantity", 0))
        priority = request.form.get("priority", "MEDIUM")
        hours_to_deadline = int(request.form.get("hours_to_deadline", 24))

        if not customer or not product_id or quantity <= 0:
            connection.close()
            flash("Customer, product, and valid quantity are required.")
            return render_template(
                "place_order.html",
                products=products
            )

        cursor.execute(
            "SELECT COUNT(*) FROM orders"
        )
        order_count = cursor.fetchone()[0]
        order_id = f"ORD{order_count + 1:03d}"

        while True:
            cursor.execute(
                "SELECT 1 FROM orders WHERE order_id = ?",
                (order_id,)
            )
            if cursor.fetchone() is None:
                break
            order_count += 1
            order_id = f"ORD{order_count + 1:03d}"

        order_data = {
            "order_id": order_id,
            "customer": customer,
            "product_id": product_id,
            "quantity": quantity,
            "priority": priority,
            "hours_to_deadline": hours_to_deadline
        }

        priority_result = prioritize_order(order_data)

        cursor.execute("""
            INSERT INTO orders (
                order_id,
                customer,
                product_id,
                quantity,
                priority,
                hours_to_deadline,
                priority_score,
                priority_level,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id,
            customer,
            product_id,
            quantity,
            priority,
            hours_to_deadline,
            priority_result["priority_score"],
            priority_result["priority_level"],
            "PENDING"
        ))

        connection.commit()
        connection.close()

        flash(f"Order {order_id} created successfully.")
        return redirect(url_for("orders"))

    connection.close()
    return render_template(
        "place_order.html",
        products=products
    )


# --------------------------------
# ANALYTICS
# --------------------------------

@app.route("/analytics")
def analytics():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM products"
    )

    products = cursor.fetchall()

    total_stock = sum(product["current_stock"] for product in products)
    reserved_stock = sum(product["reserved_stock"] for product in products)
    damaged_stock = sum(product["damaged_stock"] for product in products)

    category_totals = {}
    stock_risk = []

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

        category = product["category"]
        category_totals[category] = category_totals.get(category, 0) + available

        risk_score = (
            max(0, product["reorder_level"] - available) * 3
            + product["damaged_stock"] * 4
            + product["average_daily_demand"]
        )

        stock_risk.append({
            "name": product["name"],
            "category": category,
            "available": available,
            "status": status,
            "risk_score": risk_score
        })

    stock_risk = sorted(
        stock_risk,
        key=lambda item: item["risk_score"],
        reverse=True
    )[:5]

    max_category_total = max((value for _, value in category_totals.items()), default=1)
    category_chart = [
        {
            "label": category,
            "value": value,
            "percent": round((value / max_category_total) * 100) if max_category_total else 0
        }
        for category, value in sorted(category_totals.items())
    ]

    connection.close()

    return render_template(
        "analytics.html",
        total_stock=total_stock,
        reserved_stock=reserved_stock,
        damaged_stock=damaged_stock,
        category_totals=sorted(category_totals.items()),
        category_chart=category_chart,
        stock_risk=stock_risk,
        low_stock_items=sum(
            1 for product in products
            if get_stock_status(
                product["current_stock"],
                product["reorder_level"],
                calculate_available_stock(
                    product["current_stock"],
                    product["reserved_stock"],
                    product["damaged_stock"]
                )
            ) == "LOW STOCK"
        )
    )


# --------------------------------
# SMART ALLOCATION
# --------------------------------

@app.route(
    "/allocate/<order_id>",
    methods=["POST"]
)
def allocate(order_id):

    connection = get_connection()

    cursor = connection.cursor()

    # Get selected order
    cursor.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (order_id,)
    )

    selected_order = cursor.fetchone()

    if not selected_order:

        connection.close()

        flash("Order not found.")

        return redirect(
            url_for("orders")
        )

    # Get product
    cursor.execute(
        "SELECT * FROM products WHERE product_id = ?",
        (selected_order["product_id"],)
    )

    product = cursor.fetchone()

    available_stock = calculate_available_stock(

        product["current_stock"],

        product["reserved_stock"],

        product["damaged_stock"]

    )

    # Get all pending orders for same product

    cursor.execute("""
        SELECT *
        FROM orders
        WHERE product_id = ?
        AND status = 'PENDING'
    """, (selected_order["product_id"],))

    database_orders = cursor.fetchall()

    order_list = []

    for order in database_orders:

        order_list.append({

            "order_id": order["order_id"],

            "quantity": order["quantity"],

            "priority_score": order["priority_score"]

        })

    # Smart allocation

    allocations = allocate_inventory(
        order_list,
        available_stock
    )

    # Update allocations
    for allocation in allocations:

        if allocation["allocated"] > 0:

            cursor.execute("""
                UPDATE orders

                SET status = ?

                WHERE order_id = ?
            """, (

                "ALLOCATED"
                if allocation["allocated"]
                == allocation["requested"]

                else "PARTIALLY ALLOCATED",

                allocation["order_id"]

            ))

            # Reserve allocated stock
            cursor.execute("""
                UPDATE products

                SET reserved_stock =
                    reserved_stock + ?

                WHERE product_id = ?
            """, (

                allocation["allocated"],

                selected_order["product_id"]

            ))

    connection.commit()

    connection.close()

    flash(
        f"Smart allocation completed for {order_id}."
    )

    return redirect(
        url_for("orders")
    )


# --------------------------------
# EXCEPTIONS
# --------------------------------

@app.route("/exceptions")
def exceptions():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM exceptions
        ORDER BY
        CASE severity
            WHEN 'HIGH' THEN 1
            WHEN 'MEDIUM' THEN 2
            ELSE 3
        END
    """)

    exceptions = cursor.fetchall()

    connection.close()

    return render_template(
        "exceptions.html",
        exceptions=exceptions
    )


# --------------------------------
# UPDATE ORDER STATUS
# --------------------------------

@app.route(
    "/update-status/<order_id>",
    methods=["POST"]
)
def update_status(order_id):

    new_status = request.form.get(
        "status"
    )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE orders
        SET status = ?
        WHERE order_id = ?
    """, (
        new_status,
        order_id
    ))

    connection.commit()

    connection.close()

    flash(
        f"{order_id} status updated to {new_status}."
    )

    return redirect(
        url_for("orders")
    )


# --------------------------------
# PICKING WORKFLOW
# --------------------------------

@app.route("/picking")
def picking():
    """Display picking queue"""
    connection = get_connection()
    cursor = connection.cursor()

    # Get orders that need picking
    cursor.execute("""
        SELECT o.*, p.location, p.name as product_name
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.status = 'ALLOCATED' OR o.status = 'PARTIALLY ALLOCATED'
        ORDER BY o.priority_score DESC
    """)

    picking_orders = cursor.fetchall()

    connection.close()

    return render_template(
        "picking.html",
        picking_orders=picking_orders
    )


@app.route("/start-picking/<order_id>", methods=["POST"])
def start_picking(order_id):
    """Start picking process for an order"""
    picker_name = request.form.get("picker_name", "Unassigned")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (order_id,)
    )
    order = cursor.fetchone()

    if not order:
        connection.close()
        flash("Order not found")
        return redirect(url_for("picking"))

    # Create picking record
    cursor.execute("SELECT COUNT(*) FROM picking")
    pick_count = cursor.fetchone()[0]
    picking_id = f"PICK{pick_count + 1:04d}"

    cursor.execute("""
        INSERT INTO picking
        (picking_id, order_id, product_id, quantity_to_pick, assigned_picker, status, started_at)
        VALUES (?, ?, ?, ?, ?, 'IN_PROGRESS', CURRENT_TIMESTAMP)
    """, (picking_id, order_id, order["product_id"], order["quantity"], picker_name))

    # Update order status
    cursor.execute("""
        UPDATE orders SET status = 'PICKING'
        WHERE order_id = ?
    """, (order_id,))

    connection.commit()
    connection.close()

    flash(f"Picking started for {order_id} by {picker_name}")
    return redirect(url_for("picking"))


@app.route("/complete-picking/<order_id>", methods=["POST"])
def complete_picking(order_id):
    """Mark picking as complete"""
    quantity_picked = int(request.form.get("quantity_picked", 0))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (order_id,)
    )
    order = cursor.fetchone()

    # Update picking record
    cursor.execute("""
        UPDATE picking
        SET quantity_picked = ?, status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (quantity_picked, order_id))

    # Update order status to PACKING
    cursor.execute("""
        UPDATE orders SET status = 'PACKING'
        WHERE order_id = ?
    """, (order_id,))

    connection.commit()
    connection.close()

    flash(f"Picking completed for {order_id}")
    return redirect(url_for("packing"))


# --------------------------------
# PACKING WORKFLOW
# --------------------------------

@app.route("/packing")
def packing():
    """Display packing queue"""
    connection = get_connection()
    cursor = connection.cursor()

    # Get orders in packing stage
    cursor.execute("""
        SELECT o.*, p.name as product_name
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.status = 'PACKING'
        ORDER BY o.priority_score DESC
    """)

    packing_orders = cursor.fetchall()

    connection.close()

    return render_template(
        "packing.html",
        packing_orders=packing_orders
    )


@app.route("/start-packing/<order_id>", methods=["POST"])
def start_packing(order_id):
    """Start packing an order"""
    packer_name = request.form.get("packer_name", "Unassigned")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (order_id,)
    )
    order = cursor.fetchone()

    # Create packing record
    cursor.execute("SELECT COUNT(*) FROM packing")
    pack_count = cursor.fetchone()[0]
    packing_id = f"PACK{pack_count + 1:04d}"

    cursor.execute("""
        INSERT INTO packing
        (packing_id, order_id, assigned_packer, status, started_at)
        VALUES (?, ?, ?, 'IN_PROGRESS', CURRENT_TIMESTAMP)
    """, (packing_id, order_id, packer_name))

    connection.commit()
    connection.close()

    flash(f"Packing started for {order_id}")
    return redirect(url_for("packing"))


@app.route("/complete-packing/<order_id>", methods=["POST"])
def complete_packing(order_id):
    """Complete packing and move to QC"""
    weight = request.form.get("weight", "0")
    dimensions = request.form.get("dimensions", "")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT quantity FROM orders WHERE order_id = ?",
        (order_id,)
    )
    order = cursor.fetchone()

    # Update packing
    cursor.execute("""
        UPDATE packing
        SET quantity_packed = ?, weight = ?, dimensions = ?, status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (order["quantity"], weight, dimensions, order_id))

    # Update order status to QUALITY_CHECK
    cursor.execute("""
        UPDATE orders SET status = 'QUALITY_CHECK'
        WHERE order_id = ?
    """, (order_id,))

    connection.commit()
    connection.close()

    flash(f"Packing completed for {order_id}")
    return redirect(url_for("quality_check"))


# --------------------------------
# QUALITY CHECK WORKFLOW
# --------------------------------

@app.route("/quality-check")
def quality_check():
    """Display QC queue"""
    connection = get_connection()
    cursor = connection.cursor()

    # Get orders in QC stage
    cursor.execute("""
        SELECT o.*, p.name as product_name
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.status = 'QUALITY_CHECK'
        ORDER BY o.priority_score DESC
    """)

    qc_orders = cursor.fetchall()

    connection.close()

    return render_template(
        "quality_check.html",
        qc_orders=qc_orders
    )


@app.route("/start-qc/<order_id>", methods=["POST"])
def start_qc(order_id):
    """Start quality check"""
    inspector = request.form.get("inspector", "Unassigned")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT quantity FROM orders WHERE order_id = ?",
        (order_id,)
    )
    order = cursor.fetchone()

    # Create QC record
    cursor.execute("SELECT COUNT(*) FROM quality_check")
    qc_count = cursor.fetchone()[0]
    qc_id = f"QC{qc_count + 1:04d}"

    cursor.execute("""
        INSERT INTO quality_check
        (qc_id, order_id, quantity_inspected, inspector, status, started_at)
        VALUES (?, ?, ?, ?, 'IN_PROGRESS', CURRENT_TIMESTAMP)
    """, (qc_id, order_id, order["quantity"], inspector))

    connection.commit()
    connection.close()

    flash(f"Quality check started for {order_id}")
    return redirect(url_for("quality_check"))


@app.route("/complete-qc/<order_id>", methods=["POST"])
def complete_qc(order_id):
    """Complete QC and move to shipping"""
    defects = int(request.form.get("defects", 0))
    notes = request.form.get("notes", "")
    qc_status = request.form.get("qc_status", "PASSED")

    connection = get_connection()
    cursor = connection.cursor()

    # Update QC
    cursor.execute("""
        UPDATE quality_check
        SET defects_found = ?, notes = ?, status = ?, completed_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    """, (defects, notes, qc_status, order_id))

    if qc_status == "PASSED":
        # Move to shipping
        cursor.execute("""
            UPDATE orders SET status = 'READY_TO_SHIP'
            WHERE order_id = ?
        """, (order_id,))
    else:
        # Create exception for failed QC
        cursor.execute("SELECT COUNT(*) FROM exceptions")
        exc_count = cursor.fetchone()[0]
        exc_id = f"EXC{exc_count + 1:04d}"

        cursor.execute("""
            SELECT product_id FROM orders WHERE order_id = ?
        """, (order_id,))
        product = cursor.fetchone()

        cursor.execute("""
            INSERT INTO exceptions
            (exception_id, exception_type, order_id, product_id, description, severity, status)
            VALUES (?, 'QC_FAILED', ?, ?, ?, 'HIGH', 'OPEN')
        """, (exc_id, order_id, product["product_id"], f"QC failed: {notes}"))

        cursor.execute("""
            UPDATE orders SET status = 'EXCEPTION'
            WHERE order_id = ?
        """, (order_id,))

    connection.commit()
    connection.close()

    if qc_status == "PASSED":
        flash(f"Quality check passed for {order_id}")
        return redirect(url_for("shipments"))
    else:
        flash(f"Quality check failed for {order_id} - Exception created")
        return redirect(url_for("exceptions"))


# --------------------------------
# --------------------------------
# EXCEPTION RESOLUTION
# --------------------------------

@app.route("/exceptions/<exc_id>/resolve", methods=["POST"])
def resolve_exception(exc_id):
    """Resolve an exception"""
    resolution = request.form.get("resolution", "")
    assigned_to = request.form.get("assigned_to", "")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE exceptions
        SET status = 'RESOLVED', resolution = ?, assigned_to = ?, resolved_at = CURRENT_TIMESTAMP
        WHERE exception_id = ?
    """, (resolution, assigned_to, exc_id))

    connection.commit()
    connection.close()

    flash("Exception resolved successfully")
    return redirect(url_for("exceptions"))


@app.route("/exceptions/<exc_id>/recommendations")
def exception_recommendations(exc_id):
    """Get recommendations for exception resolution"""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM exceptions WHERE exception_id = ?",
        (exc_id,)
    )
    exception = cursor.fetchone()

    if not exception:
        connection.close()
        return {"error": "Exception not found"}, 404

    recommendations = recommend_expedited_action(
        exception["exception_type"],
        {},
        {}
    )

    connection.close()

    return {
        "exception_id": exc_id,
        "exception_type": exception["exception_type"],
        "recommendations": recommendations["actions"],
        "urgency": recommendations["urgency"]
    }


# --------------------------------
# BATCH ALLOCATION
# --------------------------------

@app.route("/batch-allocate", methods=["GET", "POST"])
def batch_allocate():
    """Allocate inventory to multiple orders at once"""
    connection = get_connection()
    cursor = connection.cursor()

    if request.method == "POST":
        product_id = request.form.get("product_id")

        cursor.execute(
            "SELECT * FROM products WHERE product_id = ?",
            (product_id,)
        )
        product = cursor.fetchone()

        available_stock = calculate_available_stock(
            product["current_stock"],
            product["reserved_stock"],
            product["damaged_stock"]
        )

        # Get all pending orders for this product
        cursor.execute("""
            SELECT *
            FROM orders
            WHERE product_id = ? AND status = 'PENDING'
            ORDER BY priority_score DESC
        """, (product_id,))

        pending_orders = cursor.fetchall()

        # Resolve conflicts with smart allocation
        allocation_strategy = resolve_inventory_conflict(
            available_stock,
            [dict(o) for o in pending_orders]
        )

        # Apply allocations
        for allocation in allocation_strategy:
            if allocation["allocated"] > 0:
                # Reserve stock
                cursor.execute("""
                    UPDATE products
                    SET reserved_stock = reserved_stock + ?
                    WHERE product_id = ?
                """, (allocation["allocated"], product_id))

                # Update order
                status = "ALLOCATED" if allocation["allocated"] == allocation["requested"] else "PARTIALLY ALLOCATED"
                cursor.execute("""
                    UPDATE orders
                    SET status = ?, allocated_quantity = ?
                    WHERE order_id = ?
                """, (status, allocation["allocated"], allocation["order_id"]))

                # Log allocation
                cursor.execute("SELECT COUNT(*) FROM allocation_log")
                log_count = cursor.fetchone()[0]
                log_id = f"LOG{log_count + 1:05d}"

                cursor.execute("""
                    INSERT INTO allocation_log
                    (log_id, order_id, product_id, requested_quantity, allocated_quantity, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (log_id, allocation["order_id"], product_id, allocation["requested"], 
                     allocation["allocated"], allocation["reason"]))

        connection.commit()
        connection.close()

        flash(f"Batch allocation completed for {product_id}")
        return redirect(url_for("orders"))

    # GET request - show products for selection
    cursor.execute("SELECT * FROM products ORDER BY name")
    products = cursor.fetchall()

    connection.close()

    return render_template(
        "batch_allocate.html",
        products=products
    )


# --------------------------------
# RUN APPLICATION
# --------------------------------

if __name__ == "__main__":

    app.run(
        debug=True
    )