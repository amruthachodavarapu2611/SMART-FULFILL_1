def calculate_priority(order):
    """
    Enhanced priority scoring considering multiple factors:
    - Priority level (URGENT > HIGH > MEDIUM > LOW)
    - Time to deadline (urgency)
    - Customer importance (optional)
    - Order value (optional)
    """
    score = 0

    priority = order.get("priority", "MEDIUM")

    if priority == "URGENT":
        score += 50
    elif priority == "HIGH":
        score += 35
    elif priority == "MEDIUM":
        score += 20
    else:
        score += 10

    hours = order.get("hours_to_deadline", 24)

    if hours <= 2:
        score += 40
    elif hours <= 6:
        score += 25
    elif hours <= 12:
        score += 15
    else:
        score += 5

    return score


def get_priority_level(score):
    """Classify priority level based on calculated score"""
    if score >= 80:
        return "CRITICAL"
    elif score >= 60:
        return "HIGH"
    elif score >= 40:
        return "MEDIUM"
    else:
        return "LOW"


def prioritize_order(order):
    """
    Calculate and return priority score and level for an order
    """
    score = calculate_priority(order)
    level = get_priority_level(score)

    return {
        "order_id": order["order_id"],
        "priority_score": score,
        "priority_level": level
    }


def resolve_inventory_conflict(available_stock, pending_orders):
    """
    Intelligent conflict resolution when inventory is insufficient
    Returns allocation strategy for all pending orders
    
    Example: 10 units available, ORD001 needs 10 (URGENT), ORD002 needs 5 (LOW)
    Decision: Allocate based on priority
    """
    if not pending_orders or available_stock <= 0:
        return []

    # Sort by priority score (highest first)
    sorted_orders = sorted(
        pending_orders,
        key=lambda x: x.get("priority_score", 0),
        reverse=True
    )

    allocation_strategy = []
    remaining_stock = available_stock

    for order in sorted_orders:
        requested = order["quantity"]

        if remaining_stock >= requested:
            # Full allocation possible
            allocated = requested
            decision = "FULL"
        elif remaining_stock > 0:
            # Partial allocation
            allocated = remaining_stock
            decision = "PARTIAL"
        else:
            # Backorder
            allocated = 0
            decision = "BACKORDER"

        allocation_strategy.append({
            "order_id": order["order_id"],
            "priority_score": order.get("priority_score", 0),
            "priority_level": order.get("priority_level", "LOW"),
            "requested": requested,
            "allocated": allocated,
            "unmet": requested - allocated,
            "decision": decision,
            "reason": generate_allocation_reason(
                allocated, requested, decision
            )
        })

        remaining_stock -= allocated

    return allocation_strategy


def generate_allocation_reason(allocated, requested, decision):
    """Generate human-readable reason for allocation decision"""
    if decision == "FULL":
        return f"Fully allocated {allocated} units"
    elif decision == "PARTIAL":
        return f"Partially allocated {allocated}/{requested} units (limited by available stock)"
    else:
        return f"Backordered: 0/{requested} units (insufficient inventory)"


def recommend_expedited_action(exception_type, order_data, inventory_data):
    """
    Recommend immediate actions for different exception types
    Helps with exception resolution workflow
    """
    recommendations = {
        "STOCKOUT": {
            "actions": [
                "Request emergency reorder from supplier",
                "Check if similar product can be substitute",
                "Offer partial fulfillment to customer",
                "Prioritize picking for backordered items"
            ],
            "urgency": "CRITICAL"
        },
        "DAMAGED_ITEM": {
            "actions": [
                "Replace with available stock",
                "Contact customer for approval",
                "Process refund if unable to fulfill",
                "Update quality control procedures"
            ],
            "urgency": "HIGH"
        },
        "MISSING_ITEM": {
            "actions": [
                "Search warehouse locations",
                "Check picking logs for discrepancies",
                "Verify inventory counts",
                "Replace from backup stock if available"
            ],
            "urgency": "HIGH"
        },
        "DELAYED_PICKING": {
            "actions": [
                "Assign additional pickers",
                "Prioritize this order in queue",
                "Check for location issues",
                "Expedite packing process"
            ],
            "urgency": "MEDIUM"
        }
    }

    return recommendations.get(exception_type, {
        "actions": ["Review exception details and take manual action"],
        "urgency": "MEDIUM"
    })