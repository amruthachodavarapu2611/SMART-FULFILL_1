def calculate_available_stock(
    current_stock,
    reserved_stock,
    damaged_stock
):
    """Calculate truly available inventory for allocation"""
    available = (
        current_stock
        - reserved_stock
        - damaged_stock
    )

    return max(available, 0)


def get_stock_status(
    current_stock,
    reorder_level,
    available_stock
):
    """Determine current stock health status"""
    if available_stock == 0:
        return "OUT OF STOCK"
    elif available_stock <= reorder_level:
        return "LOW STOCK"
    else:
        return "HEALTHY"


def get_stock_health_score(available_stock, reorder_level, avg_daily_demand):
    """
    Calculate a health score for inventory (0-100)
    Helps identify products at risk
    """
    if available_stock == 0:
        return 0
    
    # Days of inventory remaining
    if avg_daily_demand > 0:
        days_remaining = available_stock / avg_daily_demand
    else:
        days_remaining = 100
    
    # Score based on days of inventory
    if days_remaining >= 14:
        return 100
    elif days_remaining >= 7:
        return 75
    elif days_remaining >= reorder_level:
        return 50
    else:
        return 25


def allocate_inventory(orders, available_stock):
    """
    Allocate inventory to orders based on priority
    Highest priority first, respecting stock constraints
    """
    # Sort by priority score (highest first)
    sorted_orders = sorted(
        orders,
        key=lambda x: x.get("priority_score", 0),
        reverse=True
    )

    allocation = []
    remaining_stock = available_stock

    for order in sorted_orders:
        requested = order["quantity"]
        allocated = min(requested, remaining_stock)

        remaining_stock -= allocated

        if allocated == requested:
            status = "FULLY ALLOCATED"
        elif allocated > 0:
            status = "PARTIALLY ALLOCATED"
        else:
            status = "BACKORDERED"

        allocation.append({
            "order_id": order["order_id"],
            "requested": requested,
            "allocated": allocated,
            "unmet": requested - allocated,
            "remaining": requested - allocated,
            "status": status,
            "priority_score": order.get("priority_score", 0),
            "priority_level": order.get("priority_level", "LOW")
        })

    return allocation


def reorder_recommendation(
    current_stock,
    reorder_level,
    average_daily_demand
):
    """
    Generate smart reorder recommendations
    Based on current stock and consumption patterns
    """
    if current_stock <= reorder_level:
        # Order enough for 2 weeks of demand
        recommended_quantity = max(
            (average_daily_demand * 14) - current_stock,
            0
        )

        return {
            "reorder_required": True,
            "recommended_quantity": recommended_quantity,
            "urgency": "HIGH" if current_stock == 0 else "MEDIUM",
            "days_until_stockout": (
                current_stock / average_daily_demand
                if average_daily_demand > 0 else 999
            )
        }

    return {
        "reorder_required": False,
        "recommended_quantity": 0,
        "urgency": "LOW",
        "days_until_stockout": (
            current_stock / average_daily_demand
            if average_daily_demand > 0 else 999
        )
    }


def detect_bottlenecks(order_stages):
    """
    Analyze order stages to identify bottlenecks
    Helps with workflow optimization
    
    order_stages: dict with counts for each stage
    {
        "PENDING": 5,
        "ALLOCATED": 3,
        "PICKING": 2,
        "PACKING": 1,
        "QUALITY_CHECK": 1
    }
    """
    if not order_stages or len(order_stages) == 0:
        return {}
    
    total_orders = sum(order_stages.values())
    bottleneck_threshold = total_orders * 0.4  # 40% threshold
    
    bottlenecks = {}
    
    for stage, count in order_stages.items():
        if count >= bottleneck_threshold:
            severity = "CRITICAL" if count >= (total_orders * 0.6) else "HIGH"
            bottlenecks[stage] = {
                "count": count,
                "percentage": round((count / total_orders) * 100, 1),
                "severity": severity,
                "recommendation": get_bottleneck_recommendation(stage)
            }
    
    return bottlenecks


def get_bottleneck_recommendation(stage):
    """Get recommendations for each bottleneck stage"""
    recommendations = {
        "PENDING": "Increase order prioritization speed; review allocation logic",
        "ALLOCATED": "Accelerate picking assignments; add more pickers",
        "PICKING": "Optimize warehouse layout; assign additional pickers",
        "PACKING": "Increase packing capacity; streamline packing process",
        "QUALITY_CHECK": "Add QC resources; improve inspection efficiency"
    }
    return recommendations.get(stage, "Review stage workflow")


def calculate_fulfillment_metrics(orders):
    """
    Calculate key fulfillment metrics for analytics
    Returns comprehensive fulfillment statistics
    """
    if not orders:
        return {}
    
    total = len(orders)
    status_counts = {}
    total_time = 0
    completion_times = []
    
    for order in orders:
        status = order.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate order age if available
        if order.get("hours_to_deadline"):
            hours_remaining = order.get("hours_to_deadline", 0)
            total_time += hours_remaining
    
    metrics = {
        "total_orders": total,
        "status_breakdown": status_counts,
        "fulfillment_rate": round(
            (status_counts.get("DELIVERED", 0) / total * 100) if total else 0, 1
        ),
        "pending_rate": round(
            (status_counts.get("PENDING", 0) / total * 100) if total else 0, 1
        ),
        "allocation_rate": round(
            ((status_counts.get("ALLOCATED", 0) + 
              status_counts.get("PARTIALLY ALLOCATED", 0)) / total * 100) 
            if total else 0, 1
        )
    }
    
    return metrics