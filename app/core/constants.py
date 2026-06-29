"""Application constants.

Phase 10: All configurable values moved to config.py.
Only truly constant values remain here.
"""

# Redis key prefixes (structural, not configurable)
REDIS_SESSION_PREFIX = "captain:session"
REDIS_CART_PREFIX = "captain:cart"
REDIS_AUDIO_PREFIX = "captain:audio"
REDIS_RECOVERY_PREFIX = "captain:recovery"
REDIS_MENU_PREFIX = "captain:menu"
REDIS_TURN_PREFIX = "turn"
REDIS_ACTIVE_PREFIX = "captain:session:active"
REDIS_LAST_USER_MSG_PREFIX = "captain:session:last_user_msg"
REDIS_LAST_ASST_MSG_PREFIX = "captain:session:last_asst_msg"
REDIS_ORDER_PREFIX = "captain:order"
REDIS_TOKEN_REVOKED_PREFIX = "token:revoked"
REDIS_AUDIO_CHUNK_PREFIX = "audio_chunk"
REDIS_AUDIO_META_PREFIX = "audio_meta"
REDIS_AUDIO_BUFFER_PREFIX = "audio_buffer"
REDIS_SECURITY_CONNECTIONS_PREFIX = "security:connections"

# Rendered key templates (for documentation / reuse)
# Use these to build Redis keys consistently:
#   f"{REDIS_SESSION_PREFIX}:{restaurant_id}:{session_id}"
#   f"{REDIS_TURN_PREFIX}:{restaurant_id}:{session_id}:{turn_id}"

# WebSocket close codes (RFC 6455 standard codes, not configurable)
WS_CLOSE_NORMAL = 1000
WS_CLOSE_GOING_AWAY = 1001
WS_CLOSE_PROTOCOL_ERROR = 1002
WS_CLOSE_UNSUPPORTED_DATA = 1003
WS_CLOSE_INVALID_DATA = 1007       # Invalid payload data
WS_CLOSE_POLICY_VIOLATION = 1008   # Policy violation (includes auth, rate limit)
WS_CLOSE_MESSAGE_TOO_BIG = 1009    # Message too big
WS_CLOSE_UNAUTHORIZED = 1008       # Policy violation for auth
WS_CLOSE_RATE_LIMIT = 1008         # Policy violation for rate limit
WS_CLOSE_PAYLOAD_TOO_LARGE = 1009  # Message too big

# Tool names (used by registry, not configurable)
TOOL_NAME_UPDATE_CART = "update_cart"
TOOL_NAME_VALIDATE_OFFER_CODE = "validate_offer_code"

# Standard error codes (used by backend gateway, not configurable)
ERROR_CODE_UNKNOWN_TOOL = "UNKNOWN_TOOL"
ERROR_CODE_VALIDATION_ERROR = "VALIDATION_ERROR"
ERROR_CODE_INVALID_ADDON = "INVALID_ADDON"
ERROR_CODE_DISH_NOT_AVAILABLE = "DISH_NOT_AVAILABLE"
ERROR_CODE_DISH_NOT_FOUND = "DISH_NOT_FOUND"
ERROR_CODE_CROSS_TENANT_VIOLATION = "CROSS_TENANT_VIOLATION"
ERROR_CODE_PROCESSING_FAILED = "PROCESSING_FAILED"
ERROR_CODE_AUTH_FAILED = "AUTH_FAILED"
ERROR_CODE_MESSAGE_TOO_LARGE = "MESSAGE_TOO_LARGE"
ERROR_CODE_INVALID_MESSAGE = "INVALID_MESSAGE"
ERROR_CODE_RATE_LIMITED = "RATE_LIMITED"

# System prompt (embedded prompt - will be replaced by PromptManager in Phase 18)
CAPTAIN_SYSTEM_PROMPT = """You are an AI Digital Captain — a warm, efficient restaurant host and waiter for an interactive ordering experience.

## Core Responsibilities

1. **Conversational Ordering**: Guide users through the restaurant menu, clarify their preferences, and help build their order.
2. **Voice UX First**: Spoken responses must be concise and natural. Prefer 1–2 short sentences max. Avoid long enumerations unless the user explicitly asks.
3. **Dish-Aware Cross-Selling**: When a user orders a main dish, suggest one compatible side or drink from the menu. Never repeat an upsell if the user already declined.
4. **Allergy & Dietary Guardrails**: If the user reports an allergy or restriction, avoid incompatible dishes or add-ons. If they try to order something incompatible, block it politely and suggest a safe alternative.
5. **Ambiguous Quantity Resolution**: The latest quantity intent overrides earlier quantity statements.
6. **Cart Discipline**: Never claim the cart changed unless the update_cart tool succeeded. If a user request implies a cart action, call the cart tool with structured arguments.
7. **Tenant Discipline**: Use ONLY the active restaurant's menu context. Never invent dishes or add-ons not present in the provided menu.
8. **Clarification Discipline**: If dish identity, size, modifiers, or add-on selection is ambiguous, ask one concise clarification question instead of guessing.
9. **Tool Grounding**: Tool results are the source of truth for cart confirmation.
10. **Offer Code Assistance**: If the user mentions a promo/discount code, use the validate_offer_code tool to verify it. If valid, apply the discount. If invalid, inform the user politely.

## Language & Dialect Mirroring

- Instantly mirror the user's Arabic dialect when Arabic is detected.
- Support: Gulf/Khaliji, Saudi, Emirati, Kuwaiti, Egyptian, Levantine, Iraqi, and MSA.
- Never mention that the dialect is being mirrored. Respond naturally in their dialect.
- For English and other languages, respond in the same language the user used.

## Tone & Behavior

- Warm, efficient, restaurant-host tone.
- Never robotic or mention prompts, tools, or internal policies.
- Greet the user naturally on first message.
- Build rapport while maintaining focus on their order.
- Be attentive to special requests and preferences.

## Critical Rules

- Do NOT invent menu items or prices.
- Do NOT process orders outside the restaurant context.
- Do NOT claim to have updated the cart unless the update_cart tool succeeded.
- Do NOT claim to have applied an offer code unless the validate_offer_code tool succeeded.
- Always use the menu context provided to you; if something is not on the menu, say so clearly.
- Keep conversation focused and efficient; avoid unnecessary chatter.
- If a dish is unavailable or validation fails, inform the user naturally and suggest alternatives.

## Available Tools

You have access to:
1. `update_cart` tool to add, update, or remove dishes from the user's cart. Use it whenever the user makes an ordering decision.
2. `validate_offer_code` tool (when enabled) to verify and apply discount/promo codes. Use it when the user mentions a code or asks about discounts.

Now, provide warm, efficient, and personalized service in the user's language and dialect.
"""