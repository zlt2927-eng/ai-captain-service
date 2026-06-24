# Laravel Backend Requirements for AI Captain Service

This document specifies the required Laravel backend changes to support the AI Captain Service. **This is documentation only - no PHP code should be implemented by the AI Captain team.**

---

## Overview

The AI Captain Service requires specific Laravel endpoints for:
1. Menu data retrieval with ratings and availability
2. Cart operations with strict validation
3. Offer/promo code validation
4. Session-order linking
5. Abandoned cart webhooks

---

## Database Changes Required

### Migration: Add session_id to orders table

```php
// database/migrations/YYYY_MM_DD_HHMMSS_add_session_id_to_orders_table.php

Schema::table('orders', function (Blueprint $table) {
    $table->string('session_id')->nullable()->index()->after('id');
    $table->string('restaurant_id')->nullable()->index()->after('session_id');
});
```

**Purpose**: Link AI Captain sessions to Laravel orders for tracking and recovery.

---

## Required API Endpoints

### 1. GET /api/v1/restaurants/{restaurant_id}/menu

**Purpose**: Provide menu data to AI Captain with ratings and availability.

**Authentication**: Required (Sanctum token or API key)

**Response Format**:
```json
{
  "restaurant_id": "rest_1",
  "categories": [
    {
      "id": 10,
      "name": "البرجر",
      "description": "برجر طازج",
      "sort_order": 1,
      "dishes": [
        {
          "id": 101,
          "name": "برجر لحم",
          "description": "برجر لحم مشوي",
          "category_id": 10,
          "price": 32.0,
          "external_price": 32.0,
          "currency": "SAR",
          "ingredients": ["beef", "bun", "cheese"],
          "allergens": ["gluten", "dairy"],
          "calories": 650,
          "preparation_time": 15,
          "is_available": true,
          "is_featured": true,
          "average_rating": 4.5,
          "review_count": 128,
          "addons": [
            {
              "id": 501,
              "name": "جبنة إضافية",
              "price": 4.0,
              "is_active": true
            }
          ]
        }
      ]
    }
  ]
}
```

**Critical Fields**:
- `external_price`: MUST be present (fallback to `price` if not set)
- `is_available`: MUST be checked (only return available dishes)
- `average_rating`: Calculated from reviews table
- `review_count`: Count of reviews with food_rating
- `addons`: Only active addons for the dish

**Implementation Notes**:
- Filter by `restaurant_id`, `is_active = true`, `deleted_at IS NULL`
- Join with reviews table to calculate ratings
- Cache response for 5 minutes (Redis recommended)
- Return 404 if restaurant not found

---

### 2. POST /api/v1/cart/update

**Purpose**: Update cart with strict validation and idempotency.

**Authentication**: Required

**Headers**:
```
X-Idempotency-Key: cart_mutation:abc123...
X-Session-Id: sess_123
X-Turn-Id: turn_xxx
```

**Request Body**:
```json
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "action": "add",
  "dish_id": 101,
  "quantity": 2,
  "notes": "بدون بصل",
  "addons": [
    {"addon_id": 501, "quantity": 1}
  ],
  "source": "ai_captain",
  "turn_id": "turn_xxx",
  "idempotency_key": "cart_mutation:abc123...",
  "price_type": "external"
}
```

**Validation Rules** (CRITICAL - Security):

1. **Cross-tenant dish validation**:
   ```php
   $dish = Dish::where('id', $dish_id)
       ->where('restaurant_id', $restaurant_id)
       ->where('is_available', true)
       ->whereNull('deleted_at')
       ->first();
   
   if (!$dish) {
       return error('DISH_NOT_AVAILABLE', 422);
   }
   ```

2. **Addon validation**:
   ```php
   foreach ($addons as $addon) {
       $addonModel = DishAddon::where('id', $addon['addon_id'])
           ->where('dish_id', $dish_id)
           ->where('restaurant_id', $restaurant_id)
           ->where('is_active', true)
           ->whereNull('deleted_at')
           ->first();
       
       if (!$addonModel) {
           return error('INVALID_ADDON', 422);
       }
   }
   ```

3. **Idempotency**: Use `X-Idempotency-Key` header to prevent duplicate mutations

**Response Format**:
```json
{
  "success": true,
  "message": "Cart updated successfully",
  "cart": {
    "items": [...],
    "subtotal": 64.0,
    "currency": "SAR"
  },
  "cart_event": {
    "restaurant_id": "rest_1",
    "session_id": "sess_123",
    "action": "add",
    "dish_id": 101,
    "quantity": 2,
    "unit_price": 32.0,
    "subtotal": 64.0,
    "price_type": "external"
  }
}
```

**Error Responses**:
```json
// Dish not available
{
  "error": "DISH_NOT_AVAILABLE",
  "dish_id": 101,
  "message": "This dish is not available or does not belong to this restaurant"
}

// Invalid addon
{
  "error": "INVALID_ADDON",
  "addon_id": 501,
  "message": "This addon is not available for the selected dish"
}

// Validation error
{
  "error": "VALIDATION_ERROR",
  "message": "Invalid request data",
  "errors": {...}
}
```

**Implementation Notes**:
- ALWAYS use `external_price` for cart calculations
- Store snapshots in cart table/Redis
- Implement idempotency using the `X-Idempotency-Key` header
- Log all mutations with turn_id for debugging

---

### 3. POST /api/v1/cart/validate-offer

**Purpose**: Validate promo/offer codes against cart subtotal.

**Authentication**: Required

**Request Body**:
```json
{
  "restaurant_id": "rest_1",
  "code": "SAVE20",
  "subtotal": 150.0
}
```

**Response Format (Success)**:
```json
{
  "valid": true,
  "code": "SAVE20",
  "discount_type": "percentage",
  "discount_value": 20,
  "discount_amount": 30.0,
  "message": "Offer code applied successfully"
}
```

**Response Format (Failure)**:
```json
{
  "valid": false,
  "error": "OFFER_CODE_NOT_FOUND",
  "message": "Invalid or expired offer code"
}
```

**Validation Logic**:
1. Find active offer code by `restaurant_id` and `code` (case-insensitive)
2. Check `is_active = true`
3. Check date range (`starts_at <= now <= expires_at`)
4. Check minimum order amount if set
5. Calculate discount:
   - Percentage: `subtotal * (discount_value / 100)`, capped at `max_discount_amount`
   - Fixed: `discount_value`

**Implementation Notes**:
- Normalize code to uppercase before lookup
- Return 422 for validation errors
- Include `min_order_amount` in error if requirement not met

---

### 4. GET /api/v1/sessions/{session_id}/order

**Purpose**: Retrieve order linked to AI Captain session.

**Authentication**: Required

**Response Format (Success)**:
```json
{
  "success": true,
  "order": {
    "id": 123,
    "order_number": "ORD-001",
    "restaurant_id": "rest_1",
    "restaurant_name": "Captain Burger",
    "type": "dine_in",
    "subtotal": 150.0,
    "discount_amount": 30.0,
    "total": 120.0,
    "payment_method": "cash",
    "payment_status": "pending",
    "status": "confirmed",
    "items": [
      {
        "dish_id": 101,
        "dish_name": "برجر لحم",
        "dish_price": 32.0,
        "quantity": 2,
        "notes": "بدون بصل",
        "total": 64.0,
        "addons": [
          {
            "addon_id": 501,
            "addon_name": "جبنة إضافية",
            "addon_price": 4.0,
            "quantity": 1,
            "total": 4.0
          }
        ]
      }
    ],
    "created_at": "2024-01-01T12:00:00Z"
  }
}
```

**Response Format (Not Found)**:
```json
{
  "success": false,
  "message": "No order found for this session"
}
```

**Implementation Notes**:
- Join with `order_items` and `order_item_addons`
- Use snapshots (`dish_name`, `dish_price`) - never JOIN to dishes table
- Return 404 if no order found

---

### 5. POST /api/v1/cart/abandoned (Webhook)

**Purpose**: Receive abandoned cart recovery webhooks from AI Captain.

**Authentication**: Webhook signature verification (implement middleware)

**Request Body**:
```json
{
  "event_id": "uuid-here",
  "session_id": "sess_123",
  "restaurant_id": "rest_1",
  "occurred_at": "2024-01-01T12:15:00Z",
  "disconnected_at": "2024-01-01T12:00:00Z",
  "last_user_message": "أبغى برجر",
  "last_assistant_message": "تم، أضفت البرجر",
  "cart_snapshot": {
    "items": [...],
    "subtotal": 64.0
  },
  "schema_version": "1.0"
}
```

**Implementation Notes**:
- Verify webhook signature (shared secret)
- Store recovery event in database
- Trigger notification to restaurant staff
- Return 200 OK immediately (async processing recommended)

---

## Required Models

### OfferCode Model

```php
Schema::create('offer_codes', function (Blueprint $table) {
    $table->id();
    $table->foreignId('restaurant_id')->constrained()->cascadeOnDelete();
    $table->string('code')->unique();
    $table->string('discount_type'); // 'percentage' or 'fixed'
    $table->decimal('discount_value', 10, 2);
    $table->decimal('min_order_amount', 10, 2)->nullable();
    $table->decimal('max_discount_amount', 10, 2)->nullable();
    $table->boolean('is_active')->default(true);
    $table->timestamp('starts_at')->nullable();
    $table->timestamp('expires_at')->nullable();
    $table->timestamps();
    $table->softDeletes();
});
```

---

## Critical Security Requirements

### 1. Cross-Tenant Validation (MANDATORY)

**Every cart mutation MUST validate**:
```php
// dish belongs to restaurant
Dish::where('id', $dish_id)
    ->where('restaurant_id', $restaurant_id)
    ->where('is_available', true)
    ->whereNull('deleted_at')
    ->exists();
```

**Why**: Prevents malicious users from ordering dishes from other restaurants using a different restaurant's token.

### 2. Addon Validation (MANDATORY)

**Every addon MUST be validated**:
```php
DishAddon::where('id', $addon_id)
    ->where('dish_id', $dish_id)
    ->where('restaurant_id', $restaurant_id)
    ->where('is_active', true)
    ->whereNull('deleted_at')
    ->exists();
```

**Why**: Prevents addon injection attacks and cross-tenant addon usage.

### 3. Price Integrity (MANDATORY)

**Always use `external_price` for customer-facing prices**:
```php
$price = $dish->external_price ?? $dish->price;
```

**Why**: Ensures consistent pricing between AI Captain and customer-facing interfaces.

### 4. Snapshot Discipline (MANDATORY)

**Order items MUST store snapshots at creation time**:
```php
$orderItem->dish_name = $dish->name; // snapshot
$orderItem->dish_price = $dish->external_price; // snapshot
$orderItem->addon_name = $addon->name; // snapshot
$orderItem->addon_price = $addon->price; // snapshot
```

**Why**: Historical orders must not change if dish prices are updated later.

---

## Testing Checklist

### Security Tests
- [ ] Attempt to order dish from restaurant A using restaurant B token → MUST FAIL with 422
- [ ] Attempt to use addon from dish X on dish Y → MUST FAIL with 422
- [ ] Attempt to use inactive addon → MUST FAIL with 422
- [ ] Attempt to use expired offer code → MUST FAIL with 422
- [ ] Attempt to use offer code below minimum order → MUST FAIL with 422

### Functional Tests
- [ ] Valid cart update → MUST SUCCEED with 200
- [ ] Valid offer code → MUST RETURN discount calculation
- [ ] Menu endpoint → MUST include external_price, ratings, addons
- [ ] Session order lookup → MUST return order with snapshots
- [ ] Idempotency: Same idempotency key twice → MUST NOT duplicate cart

### Data Integrity Tests
- [ ] Order items have correct snapshots
- [ ] Cart uses external_price (not internal_price)
- [ ] Session_id stored in orders table
- [ ] Recovery webhook received and processed

---

## Performance Recommendations

1. **Menu Caching**: Cache menu response for 5 minutes (Redis)
2. **Database Indexes**: Add indexes on `restaurant_id`, `session_id`, `is_active`
3. **Eager Loading**: Use `with()` to avoid N+1 queries
4. **Rate Limiting**: Implement rate limiting on all AI Captain endpoints

---

## Monitoring

Log these events:
- All cart mutations with `turn_id` and `session_id`
- All validation failures with error codes
- Offer code validation attempts
- Session-order linking events
- Recovery webhook deliveries

---

## Summary

The Laravel backend MUST implement:
1. ✅ Cross-tenant dish validation
2. ✅ Addon-to-dish validation
3. ✅ Session-order linking (database + API)
4. ✅ Offer code validation endpoint
5. ✅ Menu endpoint with external_price and ratings
6. ✅ Snapshot discipline for order items
7. ✅ Idempotency support for cart mutations
8. ✅ Abandoned cart webhook receiver

**Security is critical**: Never skip validation. The AI Captain service trusts the Laravel backend to enforce all business rules.