# 🏗️ SmartFulfill System Architecture

## High-Level System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACE (Frontend)                 │
│  - HTML Templates (Jinja2)                                   │
│  - CSS Styling (Modern, Responsive)                          │
│  - Dark Mode Support                                         │
│  - Real-time Status Updates                                  │
└────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER (Flask)                  │
│  - 20+ HTTP Routes                                           │
│  - Request/Response Handling                                 │
│  - Session Management                                        │
│  - Form Processing                                           │
└────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    BUSINESS LOGIC LAYER                      │
│  ┌──────────────────────────────────────────────────┐        │
│  │  Decision Engine (decision_engine.py)            │        │
│  │  - Priority scoring                              │        │
│  │  - Conflict resolution                           │        │
│  │  - Exception recommendations                     │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌──────────────────────────────────────────────────┐        │
│  │  Inventory Engine (inventory_engine.py)          │        │
│  │  - Stock calculations                            │        │
│  │  - Health scoring                                │        │
│  │  - Bottleneck detection                          │        │
│  │  - Fulfillment metrics                           │        │
│  └──────────────────────────────────────────────────┘        │
└────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    DATA ACCESS LAYER                         │
│  - SQLite3 Database Operations                               │
│  - Query Building & Execution                                │
│  - Transaction Management                                    │
└────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENT DATA LAYER                     │
│  - SQLite3 Database File (warehouse.db)                      │
│  - 8 Interconnected Tables                                   │
│  - Indexed Queries                                           │
│  - Transaction Support                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Architecture

### Database Design: 8-Table Schema

#### 1. **products** Table
```sql
CREATE TABLE products (
  id INTEGER PRIMARY KEY,
  name TEXT,
  category TEXT,
  current_stock INTEGER,
  reserved_stock INTEGER,
  damaged_stock INTEGER,
  reorder_level INTEGER,
  avg_daily_demand REAL
)
```
**Purpose:** Master inventory data
**Key Fields:** Stock levels, demand tracking
**Relationships:** Referenced by orders & allocation_log

#### 2. **orders** Table
```sql
CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  product_id INTEGER,
  quantity INTEGER,
  priority_level TEXT,
  priority_score REAL,
  deadline TEXT,
  allocated_quantity INTEGER,
  fulfilled_quantity INTEGER,
  status TEXT,
  exception_id INTEGER,
  created_at TIMESTAMP
)
```
**Purpose:** Core order tracking
**Key Fields:** Status tracking, priority scoring, allocation tracking
**Relationships:** Links to products, exceptions, picking, packing, etc.
**Status Flow:** PENDING → ALLOCATED → PICKING → PACKING → QC → READY_TO_SHIP → SHIPPED → DELIVERED

#### 3. **picking** Table
```sql
CREATE TABLE picking (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  assigned_to TEXT,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  status TEXT
)
```
**Purpose:** Picking operation tracking
**Key Fields:** Assignment, timing
**Relationships:** Links to orders
**Status:** PENDING, IN_PROGRESS, COMPLETED

#### 4. **packing** Table
```sql
CREATE TABLE packing (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  assigned_to TEXT,
  weight REAL,
  dimensions TEXT,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  status TEXT
)
```
**Purpose:** Packing operation tracking
**Key Fields:** Package details (weight, dimensions)
**Relationships:** Links to orders

#### 5. **quality_check** Table
```sql
CREATE TABLE quality_check (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  inspector TEXT,
  defects_found INTEGER,
  defect_notes TEXT,
  passed INTEGER,
  checked_at TIMESTAMP,
  status TEXT
)
```
**Purpose:** QC inspection tracking
**Key Fields:** Inspection results, defect documentation
**Relationships:** Links to orders, triggers exception creation on failure

#### 6. **shipments** Table
```sql
CREATE TABLE shipments (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  carrier TEXT,
  tracking_number TEXT,
  shipped_at TIMESTAMP,
  delivered_at TIMESTAMP,
  status TEXT
)
```
**Purpose:** Dispatch and delivery tracking
**Key Fields:** Carrier info, tracking number, delivery status
**Relationships:** Links to orders

#### 7. **exceptions** Table
```sql
CREATE TABLE exceptions (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  product_id INTEGER,
  exception_type TEXT,
  severity TEXT,
  description TEXT,
  status TEXT,
  assigned_to TEXT,
  resolution TEXT,
  resolved_at TIMESTAMP,
  created_at TIMESTAMP
)
```
**Purpose:** Exception/issue tracking
**Key Fields:** Type, severity, resolution tracking
**Relationships:** Links to orders & products
**Types:** STOCKOUT, DAMAGED_ITEM, MISSING_ITEM, QC_FAILED
**Status:** OPEN, RESOLVED

#### 8. **allocation_log** Table
```sql
CREATE TABLE allocation_log (
  id INTEGER PRIMARY KEY,
  order_id INTEGER,
  product_id INTEGER,
  quantity_requested INTEGER,
  quantity_allocated INTEGER,
  allocation_decision TEXT,
  reason TEXT,
  allocated_at TIMESTAMP
)
```
**Purpose:** Allocation decision audit trail
**Key Fields:** Allocation details with reasoning
**Relationships:** Links to orders & products
**Decisions:** FULL, PARTIAL, BACKORDER

### Database Relationships

```
products
    ├── orders
    │   ├── picking
    │   ├── packing
    │   ├── quality_check
    │   ├── shipments
    │   └── exceptions
    ├── exceptions
    └── allocation_log

orders
    ├── picking
    ├── packing
    ├── quality_check
    ├── shipments
    └── exceptions

exceptions
    └── allocation_log
```

---

## Backend Architecture

### Module 1: app.py (Main Flask Application)

**Purpose:** HTTP request handling, route definitions, workflow orchestration

**Key Routes:**

| Route | Method | Purpose |
|-------|--------|---------|
| / | GET | Dashboard with KPIs |
| /inventory | GET | Stock status by product |
| /orders | GET/POST | Order listing & search |
| /place-order | GET/POST | Create new order |
| /allocate/<order_id> | POST | Manual allocation |
| /batch-allocate | GET/POST | Multi-order allocation |
| /picking | GET | Picking queue |
| /picking/<order_id>/start | POST | Start picking operation |
| /picking/<order_id>/complete | POST | Complete picking |
| /packing | GET | Packing queue |
| /packing/<order_id>/start | POST | Start packing |
| /packing/<order_id>/complete | POST | Complete packing |
| /quality-check | GET | QC queue |
| /quality-check/<order_id>/start | POST | Start QC |
| /quality-check/<order_id>/complete | POST | Complete QC |
| /shipments | GET | Shipment tracking |
| /shipments/<order_id>/dispatch | POST | Dispatch order |
| /shipments/<order_id>/deliver | POST | Mark delivered |
| /exceptions | GET | Exception list |
| /exceptions/<exc_id>/resolve | POST | Resolve exception |
| /exceptions/<exc_id>/recommendations | GET | Get recommendations |
| /analytics | GET | Analytics & insights |

**Request Flow:**
1. HTTP Request arrives
2. Flask routes to appropriate handler
3. Handler calls business logic (decision_engine, inventory_engine)
4. Business logic queries database
5. Results passed to template
6. HTML response sent to browser

### Module 2: decision_engine.py

**Purpose:** Intelligent business logic for decision-making

**Key Functions:**

```python
def calculate_priority(order):
    """
    Calculate priority score for an order
    
    Input: Order dict with priority_level, deadline
    Output: priority_score (float)
    
    Algorithm:
    - Base score from priority level (URGENT=100, HIGH=60, etc.)
    - Add urgency factor based on time to deadline
    - Higher score = higher priority
    """

def prioritize_order(order):
    """
    Get complete priority information
    
    Returns: dict with priority_score and priority_level
    """

def resolve_inventory_conflict(available_stock, pending_orders):
    """
    Intelligent allocation when stock is insufficient
    
    Input: 
    - available_stock: Total units available
    - pending_orders: List of orders with quantities and priorities
    
    Output: Allocation strategy with decision for each order
    
    Algorithm:
    1. Sort orders by priority_score (descending)
    2. For each order in priority order:
       - If stock >= quantity: Allocate FULL
       - Else if stock > 0: Allocate PARTIAL
       - Else: Allocate BACKORDER
    3. Return list with decision + reason for each
    """

def recommend_expedited_action(exception_type, order_data, inventory_data):
    """
    Generate recommended actions for an exception
    
    Input: Exception type, order info, inventory info
    Output: List of 4-5 recommended actions
    
    Examples:
    - STOCKOUT → "Emergency PO", "Substitute", "Partial shipment"
    - QC_FAILED → "Rework", "Replace", "Refund"
    - DAMAGED → "Quarantine", "Claim", "Reorder"
    """

def generate_allocation_reason(allocated, requested, decision):
    """
    Create human-readable explanation of allocation
    
    Output: String explaining why decision was made
    Example: "5 of 10 units allocated (partial due to insufficient stock)"
    """
```

### Module 3: inventory_engine.py

**Purpose:** Stock calculations, analytics, and recommendations

**Key Functions:**

```python
def calculate_available_stock(current, reserved, damaged):
    """Calculate usable inventory"""
    return current - reserved - damaged

def get_stock_status(available, reorder_level):
    """Return status: HEALTHY, LOW, OUT_OF_STOCK"""

def get_stock_health_score(available, reorder_level, avg_daily_demand):
    """
    Calculate health score (0-100)
    
    Formula: (Available / TargetLevel) × 100
    Accounts for days of inventory remaining
    """

def allocate_inventory(orders, available_stock):
    """
    Smart multi-order allocation
    
    Considers:
    - Order priority scores
    - Available inventory
    - Demand distribution
    
    Returns allocation for each order:
    - FULLY_ALLOCATED
    - PARTIALLY_ALLOCATED
    - BACKORDERED
    """

def reorder_recommendation(current_stock, reorder_level, avg_daily_demand):
    """
    Generate reorder suggestion
    
    Returns:
    - reorder_required (bool)
    - recommended_quantity
    - urgency_level
    - days_until_stockout
    """

def detect_bottlenecks(order_stages):
    """
    Identify workflow stage congestion
    
    Algorithm:
    1. Count orders at each stage
    2. Calculate % at each stage
    3. Flag stages with >40% of orders
    4. Return severity + recommendations
    
    Example:
    - Packing has 45% of orders → Bottleneck!
    - Recommendation: "Add more packers"
    """

def calculate_fulfillment_metrics(orders):
    """
    Compute operational KPIs
    
    Returns:
    - total_orders
    - status_breakdown (by stage)
    - fulfillment_rate (%)
    - pending_rate (%)
    - allocation_rate (%)
    """
```

### Module 4: database.py

**Purpose:** Database initialization and sample data management

**Key Functions:**

```python
def initialize_database():
    """
    Create all 8 tables with proper schema
    
    Ensures:
    - Table creation
    - Indexes on frequently queried fields
    - Foreign key relationships
    - Transaction support
    """

def insert_sample_data():
    """
    Populate database with sample data
    
    Includes:
    - 6 products (various categories)
    - 4 orders (different statuses & priorities)
    - 3 exceptions (different types)
    - Realistic stock levels
    - Valid timestamps
    """

def get_db_connection():
    """Return SQLite3 connection for queries"""
```

---

## Frontend Architecture

### Template Hierarchy

```
base.html (Master Template)
├── dashboard.html
├── inventory.html
├── orders.html
├── place_order.html
├── picking.html
├── packing.html
├── quality_check.html
├── shipments.html
├── batch_allocate.html
├── exceptions.html
├── analytics.html
└── order_details.html
```

### CSS Architecture (style.css)

**Key Components:**
- **Layout System:** Sidebar navigation + main content area
- **Color Scheme:** Teal/blue accents, status colors
- **Card System:** Reusable card layouts
- **Badge System:** Status indicators (color-coded)
- **Responsive Grids:** Mobile, tablet, desktop layouts
- **Dark Mode:** CSS variables for theme switching
- **Typography:** Professional font hierarchy
- **Effects:** Shadows, gradients, transitions

---

## Data Flow Examples

### Example 1: Order Creation Flow

```
User Input (Place Order)
    ↓
POST /place-order handler
    ↓
Extract form data (product, qty, priority, deadline)
    ↓
Call decision_engine.calculate_priority()
    ↓
Insert order record with priority_score
    ↓
Redirect to /orders
    ↓
Display dashboard with new order
```

### Example 2: Conflict Resolution Flow

```
User clicks "Batch Allocate"
    ↓
GET /batch-allocate handler
    ↓
Query: Get all unallocated orders for product
    ↓
Call decision_engine.resolve_inventory_conflict()
    ↓
Algorithm ranks orders by priority_score
    ↓
Distributes available stock
    ↓
Returns allocation_strategy with decisions
    ↓
Template displays:
  - Available stock
  - Pending orders
  - Proposed allocation
    ↓
User clicks "Confirm"
    ↓
POST /batch-allocate handler
    ↓
Create allocation_log entries
    ↓
Update order status: ALLOCATED/PARTIALLY_ALLOCATED/BACKORDERED
    ↓
Redirect to /orders
```

### Example 3: Exception Resolution Flow

```
QC Fails on Order
    ↓
POST /quality-check/<order_id>/complete handler
    ↓
If failed=true:
  - Call decision_engine.recommend_expedited_action("QC_FAILED", ...)
  - Create exception with recommended actions
  - Update order status to QC_FAILED
    ↓
User visits /exceptions
    ↓
See exception with type, severity, recommendations
    ↓
Click "Resolve"
    ↓
Modal opens
    ↓
Enter assigned_to and resolution action
    ↓
POST /exceptions/<exc_id>/resolve handler
    ↓
Update exception status: RESOLVED
    ↓
Update order status: RESOLVED
    ↓
Redirect to /exceptions
```

---

## Data Consistency & Integrity

### Order Status Consistency

Order moves through fixed lifecycle with automatic transitions:
```
PENDING → ALLOCATED → PICKING → PACKING → QUALITY_CHECK → READY_TO_SHIP → SHIPPED → DELIVERED
```

Each transition:
- Validated in backend
- Recorded with timestamp
- Cannot go backwards
- Triggers dependent updates

### Allocation Audit Trail

Every allocation decision recorded with:
- Order ID & Product ID
- Quantity requested vs. allocated
- Decision type (FULL/PARTIAL/BACKORDER)
- Reason explanation
- Timestamp

Enables:
- Full audit trail
- Exception investigation
- Performance analysis

### Exception Lifecycle

```
Detection
    ↓
Auto-Recommendation
    ↓
Resolution
    ↓
Closure
```

Preserves all data at each stage for analysis

---

## Performance Considerations

### Database Optimization
- Indexes on frequently queried fields
- Query optimization for filtering
- Connection pooling support
- Transaction batching

### Frontend Optimization
- Table pagination for large datasets
- Form validation before submission
- Modal dialogs reduce page reloads
- CSS minification

### Scalability Considerations
- SQLite suitable for single-warehouse (~10,000 orders)
- For multi-warehouse: Migrate to PostgreSQL
- Add caching layer for analytics
- Background jobs for batch processing

---

## Deployment Architecture

### Development
- Local Flask server: `python app.py`
- SQLite database: `warehouse.db`
- Static files served by Flask

### Production Recommendations
- Deploy with Gunicorn/uWSGI
- Reverse proxy with Nginx
- PostgreSQL for database (instead of SQLite)
- Redis for session/cache management
- Monitoring & logging systems
- Backup strategy for database

---

## Error Handling & Recovery

### Input Validation
- Form validation in frontend
- Backend validation before database
- Type checking on all inputs
- Range validation for quantities

### Database Error Handling
- Connection error handling
- Transaction rollback on failure
- Constraint violation handling
- Graceful degradation

### User-Facing Errors
- Flash messages for errors
- HTTP status codes
- Redirect to safe state
- Error logging

---

## Security Considerations

### Current Implementation
- Input sanitization via Jinja2 auto-escaping
- SQLite no network exposure
- Session management via Flask

### Production Enhancements Needed
- SQL injection prevention (parameterized queries)
- CSRF protection tokens
- Authentication & authorization
- HTTPS enforcement
- Rate limiting
- Audit logging of all changes

---

## Testing Architecture

### Unit Tests Needed
- decision_engine functions
- inventory_engine calculations
- Database query accuracy

### Integration Tests Needed
- Complete order workflow
- Exception handling
- Batch allocation scenarios

### End-to-End Tests Needed
- Full order lifecycle
- User interactions
- Data consistency

---

## Summary

SmartFulfill architecture is built on:
1. **Clear separation of concerns** (UI / Business Logic / Data)
2. **Intelligent algorithms** in decision & inventory engines
3. **Normalized database** for data integrity
4. **Responsive frontend** for user experience
5. **Audit trail** for compliance & analysis

This design enables:
- Easy maintenance & debugging
- Feature additions without refactoring
- Scaling from small to large operations
- Complete audit trail for decisions
