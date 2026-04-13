"""Seed injection layer: data-level mutations applied during session creation.

This is the most powerful degradation layer because it changes *what the agent
reads and reasons about*, not just how it's presented. The agent sees a
realistic inbox — but the information landscape is adversarially shaped to
stress a specific cognitive primitive.

Targets all primitives, especially:
- Grounding: near-identical subjects, similar sender names, misleading content
- State Tracking: information split across many emails, contradictory updates
- Planning: hidden prerequisites in email content, conflicting constraints
- Backtracking: plausible-but-wrong first-found answer, correction elsewhere
- Verification: partial success data, inconsistent confirmation signals
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import random as _random


def apply_seed_injection(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Mutate seeded state to create data-level degraded conditions.

    Called after normal seeding but before the session starts. The state
    is a fully populated GmailState / RobinhoodState (or equivalent BaseEnvState).
    """
    params = _render_seed_templates(params, state)
    action = params.get("action", "")

    # Gmail seed actions
    if action == "add_confusing_decoys":
        _add_confusing_decoys(state, params, rng=rng)
    elif action == "split_information":
        _split_information(state, params, rng=rng)
    elif action == "add_contradictory_update":
        _add_contradictory_update(state, params, rng=rng)
    elif action == "plant_wrong_answer":
        _plant_wrong_answer(state, params, rng=rng)
    elif action == "increase_distractors":
        _increase_distractors(state, params, rng=rng)
    elif action == "alias_entities":
        _alias_entities(state, params, rng=rng)
    elif action == "hide_in_non_obvious_location":
        _hide_in_non_obvious_location(state, params, rng=rng)
    # Robinhood seed actions
    elif action == "add_decoy_notifications":
        _rh_add_decoy_notifications(state, params, rng=rng)
    elif action == "add_noise_orders":
        _rh_add_noise_orders(state, params, rng=rng)
    elif action == "add_misleading_alert":
        _rh_add_misleading_alert(state, params, rng=rng)
    elif action == "add_confusing_positions":
        _rh_add_confusing_positions(state, params, rng=rng)
    elif action == "add_confusing_stocks":
        _rh_add_confusing_stocks(state, params, rng=rng)


def _entity_rng(rng: Any, seed: int) -> Any:
    return rng or _random.Random(seed)


def _render_seed_templates(value: Any, state: Any) -> Any:
    targets = getattr(state, "resolved_targets", {}) or {}
    if isinstance(value, str):
        rendered = value
        for key, target_value in targets.items():
            rendered = rendered.replace(f"{{target.{key}}}", str(target_value))
        return rendered
    if isinstance(value, list):
        return [_render_seed_templates(item, state) for item in value]
    if isinstance(value, dict):
        return {key: _render_seed_templates(item, state) for key, item in value.items()}
    return value


def _state_next_id(state: Any, prefix: str, *, rng: Any, fallback_seed: int) -> str:
    if hasattr(state, "_next_id"):
        try:
            return state._next_id(prefix)
        except TypeError:
            pass
    if hasattr(state, "_gen_id"):
        return state._gen_id(prefix)
    local_rng = _entity_rng(rng, fallback_seed)
    return f"{prefix}_{local_rng.randint(10000, 99999)}"


def _score_label(score: float) -> str:
    if score >= 9.0:
        return "Superb"
    if score >= 8.0:
        return "Very Good"
    if score >= 7.0:
        return "Good"
    if score >= 6.0:
        return "Pleasant"
    return "Review score"


def _coerce_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _latest_state_timestamp(state: Any, fallback: datetime) -> datetime:
    if not hasattr(state, "emails"):
        return fallback

    latest = fallback
    for email in getattr(state, "emails", []):
        timestamp = _coerce_timestamp(getattr(email, "timestamp", None))
        if timestamp is not None and timestamp > latest:
            latest = timestamp
    return latest


def _add_confusing_decoys(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add emails with near-identical subjects/senders to stress Grounding.

    The agent must distinguish the real task-relevant email from decoys
    that look almost identical but contain wrong or outdated information.
    """
    decoys = params.get("decoys", [])
    if not decoys:
        return

    _rng = _entity_rng(rng, 99)

    if hasattr(state, "emails"):
        from webagentbench.backend.models.gmail import Email, Label

        template = state.emails[0] if state.emails else None
        base_time = template.timestamp if template else "2026-01-15T10:00:00Z"
        for i, decoy_spec in enumerate(decoys):
            if isinstance(decoy_spec, str):
                decoy_spec = {
                    "subject": template.subject if template else f"Re: Update {i + 1}",
                    "body": decoy_spec,
                }
            elif not isinstance(decoy_spec, dict):
                continue
            elif str(decoy_spec.get("type", "email")).lower() == "label":
                if not hasattr(state, "labels"):
                    continue
                state.labels.append(
                    Label(
                        id=decoy_spec.get("id", f"label_{_rng.randint(10000, 99999)}"),
                        name=decoy_spec.get("name", f"Project/Archive {i + 1}"),
                        color=decoy_spec.get("color", "#5f6368"),
                        system=bool(decoy_spec.get("system", False)),
                        show_in_label_list=decoy_spec.get("show_in_label_list", "show"),
                        show_in_message_list=decoy_spec.get("show_in_message_list", "show"),
                        show_in_imap=bool(decoy_spec.get("show_in_imap", True)),
                    )
                )
                continue

            email = Email(
                id=f"email_{_rng.randint(10000, 99999)}",
                thread_id=f"thread_{_rng.randint(10000, 99999)}",
                from_name=decoy_spec.get("from_name", template.from_name if template else ""),
                from_addr=decoy_spec.get("from", template.from_addr if template else "noreply@thornton.com"),
                to=decoy_spec.get(
                    "to",
                    [template.to[0]] if template and template.to else ["me@thornton.com"],
                ),
                subject=decoy_spec.get("subject", template.subject if template else ""),
                body=decoy_spec.get("body", ""),
                timestamp=decoy_spec.get("timestamp", base_time),
                labels=decoy_spec.get("labels", ["inbox"]),
                is_read=False,
                deleted=bool(decoy_spec.get("deleted", False)),
                pre_delete_labels=list(decoy_spec.get("pre_delete_labels", ["inbox"])),
            )
            if email.deleted or "trash" in {label.lower() for label in email.labels}:
                email.deleted = True
                state.deleted.insert(0, email)
            else:
                state.emails.insert(0, email)
        return

    if hasattr(state, "products"):
        from webagentbench.backend.models.amazon import (
            Address,
            CartItem,
            Order,
            OrderItem,
            PaymentMethod,
            ProductVariant,
        )

        product_template = state.products[0] if state.products else None
        order_template = state.orders[0] if getattr(state, "orders", None) else None
        address_template = state.addresses[0] if getattr(state, "addresses", None) else None
        payment_template = state.payment_methods[0] if getattr(state, "payment_methods", None) else None
        cart_template = state.cart_items[0] if getattr(state, "cart_items", None) else None
        if all(
            template is None
            for template in (
                product_template,
                order_template,
                address_template,
                payment_template,
                cart_template,
            )
        ):
            return
        for spec in decoys:
            if not isinstance(spec, dict):
                continue
            dtype = str(spec.get("type", "product")).lower()
            if dtype == "address":
                if address_template is not None:
                    address = address_template.model_copy(deep=True)
                    address.id = _state_next_id(state, "addr", rng=_rng, fallback_seed=110)
                    address.full_name = spec.get("full_name", address.full_name)
                    address.street_address = spec.get("street_address", address.street_address)
                    address.apt_suite = spec.get("apt_suite", address.apt_suite)
                    address.city = spec.get("city", address.city)
                    address.state = spec.get("state", address.state)
                    address.zip_code = str(spec.get("zip_code", address.zip_code))
                    address.country = spec.get("country", address.country)
                    address.phone = spec.get("phone", address.phone)
                    address.is_default = bool(spec.get("is_default", False))
                else:
                    address = Address(
                        id=_state_next_id(state, "addr", rng=_rng, fallback_seed=110),
                        full_name=spec.get("full_name", "Jordan Parker"),
                        street_address=spec.get("street_address", "1 Market St"),
                        apt_suite=spec.get("apt_suite", ""),
                        city=spec.get("city", "San Francisco"),
                        state=spec.get("state", "CA"),
                        zip_code=str(spec.get("zip_code", "94105")),
                        country=spec.get("country", "United States"),
                        phone=spec.get("phone", ""),
                        is_default=bool(spec.get("is_default", False)),
                    )
                state.addresses.insert(0, address)
                continue
            if dtype == "payment_method":
                if payment_template is not None:
                    payment_method = payment_template.model_copy(deep=True)
                    payment_method.id = _state_next_id(state, "pm", rng=_rng, fallback_seed=111)
                    payment_method.card_type = spec.get("card_type", payment_method.card_type)
                    payment_method.last_four = str(spec.get("last_four", payment_method.last_four))
                    payment_method.expiry = spec.get("expiry", payment_method.expiry)
                    payment_method.holder_name = spec.get(
                        "holder_name",
                        getattr(state, "owner_name", payment_method.holder_name),
                    )
                    payment_method.is_default = bool(spec.get("is_default", False))
                else:
                    payment_method = PaymentMethod(
                        id=_state_next_id(state, "pm", rng=_rng, fallback_seed=111),
                        card_type=spec.get("card_type", "Visa"),
                        last_four=str(spec.get("last_four", "1111")),
                        expiry=spec.get("expiry", "12/29"),
                        holder_name=spec.get("holder_name", getattr(state, "owner_name", "Jordan Parker")),
                        is_default=bool(spec.get("is_default", False)),
                    )
                state.payment_methods.insert(0, payment_method)
                continue
            if dtype == "cart_item":
                product = None
                product_id = spec.get("product_id")
                product_name = spec.get("product_name", "")
                if product_id and hasattr(state, "get_product"):
                    product = state.get_product(product_id)
                if product is None and product_name:
                    product = next(
                        (candidate for candidate in state.products if candidate.name == product_name),
                        None,
                    )
                    if product is not None:
                        product_id = product.id
                if product is None and product_template is not None:
                    product = product_template.model_copy(deep=True)
                    product.id = _state_next_id(state, "prod", rng=_rng, fallback_seed=112)
                    product.name = product_name or product.name
                    product.brand = spec.get("brand", product.brand)
                    product.category = spec.get("category", product.category)
                    product.price = float(spec.get("unit_price", spec.get("price", product.price)))
                    state.products.insert(0, product)
                    product_id = product.id
                if product is None:
                    continue
                if cart_template is not None:
                    cart_item = cart_template.model_copy(deep=True)
                    cart_item.id = _state_next_id(state, "cart", rng=_rng, fallback_seed=113)
                    cart_item.product_id = product_id or product.id
                    cart_item.product_name = product_name or product.name
                    cart_item.quantity = int(spec.get("quantity", cart_item.quantity))
                    cart_item.unit_price = float(spec.get("unit_price", getattr(product, "price", cart_item.unit_price)))
                    cart_item.variant_selections = dict(spec.get("variant_selections", cart_item.variant_selections))
                    cart_item.added_at = _coerce_timestamp(spec.get("added_at")) or datetime.now(timezone.utc)
                else:
                    cart_item = CartItem(
                        id=_state_next_id(state, "cart", rng=_rng, fallback_seed=113),
                        product_id=product_id or product.id,
                        product_name=product_name or product.name,
                        quantity=int(spec.get("quantity", 1)),
                        unit_price=float(spec.get("unit_price", getattr(product, "price", 0.0))),
                        variant_selections=dict(spec.get("variant_selections", {})),
                        added_at=_coerce_timestamp(spec.get("added_at")) or datetime.now(timezone.utc),
                    )
                state.cart_items.insert(0, cart_item)
                continue
            if dtype == "order":
                if order_template is not None:
                    order = order_template.model_copy(deep=True)
                else:
                    order = Order(
                        id=_state_next_id(state, "order", rng=_rng, fallback_seed=111),
                        items=[],
                        shipping_address_id=state.addresses[0].id if getattr(state, "addresses", None) else "",
                        payment_method_id=state.payment_methods[0].id if getattr(state, "payment_methods", None) else "",
                        subtotal=0.0,
                        tax=0.0,
                        total=0.0,
                    )
                order.id = spec.get(
                    "id",
                    _state_next_id(state, "order", rng=_rng, fallback_seed=111),
                )
                item_specs = spec.get("items")
                if not item_specs:
                    item_specs = [{
                        "product_id": spec.get("product_id"),
                        "product_name": spec.get("product_name"),
                        "quantity": spec.get("quantity", 1),
                        "unit_price": spec.get("unit_price"),
                        "variant_selections": spec.get("variant_selections", {}),
                    }]
                items: list[OrderItem] = []
                for item_spec in item_specs:
                    if not isinstance(item_spec, dict):
                        continue
                    product_id = item_spec.get("product_id")
                    product_name = item_spec.get("product_name", "")
                    product = None
                    if product_id and hasattr(state, "get_product"):
                        product = state.get_product(product_id)
                    if product is None and product_name:
                        product = next(
                            (candidate for candidate in state.products if candidate.name == product_name),
                            None,
                        )
                        if product is not None:
                            product_id = product.id
                    if product_name == "" and product is not None:
                        product_name = product.name
                    unit_price = float(
                        item_spec.get(
                            "unit_price",
                            getattr(product, "price", spec.get("unit_price", 0.0)),
                        )
                    )
                    items.append(OrderItem(
                        product_id=product_id or _state_next_id(state, "prod", rng=_rng, fallback_seed=112),
                        product_name=product_name or "Decoy product",
                        quantity=int(item_spec.get("quantity", 1)),
                        unit_price=unit_price,
                        variant_selections=dict(item_spec.get("variant_selections", {})),
                    ))
                if items:
                    order.items = items
                subtotal = float(spec.get(
                    "subtotal",
                    sum(item.quantity * item.unit_price for item in order.items),
                ))
                shipping_cost = float(spec.get("shipping_cost", getattr(order, "shipping_cost", 0.0)))
                tax = float(spec.get("tax", round(subtotal * 0.08, 2)))
                discount = float(spec.get("discount", getattr(order, "discount", 0.0)))
                order.shipping_address_id = spec.get(
                    "shipping_address_id",
                    order.shipping_address_id or (state.addresses[0].id if getattr(state, "addresses", None) else ""),
                )
                order.payment_method_id = spec.get(
                    "payment_method_id",
                    order.payment_method_id or (state.payment_methods[0].id if getattr(state, "payment_methods", None) else ""),
                )
                order.subtotal = subtotal
                order.shipping_cost = shipping_cost
                order.tax = tax
                order.discount = discount
                order.total = float(spec.get("total", subtotal + shipping_cost + tax - discount))
                order.status = spec.get("status", order.status)
                placed_at = _coerce_timestamp(spec.get("placed_at"))
                if placed_at is None:
                    hours_ago = int(spec.get("placed_hours_ago", 12))
                    placed_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
                order.placed_at = placed_at
                order.estimated_delivery = spec.get("estimated_delivery", order.estimated_delivery)
                order.promo_code = spec.get("promo_code", order.promo_code)
                state.orders.insert(0, order)
                continue

            if product_template is None:
                continue
            product = product_template.model_copy(deep=True)
            product.id = _state_next_id(state, "prod", rng=_rng, fallback_seed=100)
            product.name = spec.get("name", product.name)
            product.brand = spec.get("brand", product.brand)
            product.category = spec.get("category", product.category)
            product.subcategory = spec.get("subcategory", product.subcategory or product.category)
            product.description = spec.get("description", product.description)
            product.price = float(spec.get("price", product.price))
            product.list_price = (
                float(spec["list_price"])
                if spec.get("list_price") is not None
                else product.list_price
            )
            product.currency = spec.get("currency", product.currency)
            product.rating = float(spec.get("rating", product.rating))
            product.review_count = int(spec.get("review_count", max(product.review_count // 2, 50)))
            product.in_stock = bool(spec.get("in_stock", product.in_stock))
            product.stock_quantity = int(spec.get("stock_quantity", product.stock_quantity))
            product.features = list(spec.get("features", product.features))
            product.seller = spec.get("seller", product.seller)
            product.prime_eligible = bool(spec.get("prime_eligible", product.prime_eligible))
            product.delivery_estimate = spec.get("delivery_estimate", product.delivery_estimate)
            if "variants" in spec:
                product.variants = [
                    ProductVariant(**variant) if isinstance(variant, dict) else variant
                    for variant in spec.get("variants", [])
                ]
            state.products.insert(0, product)
        if hasattr(state, "touch"):
            state.touch()
        return

    if hasattr(state, "properties"):
        from webagentbench.backend.models.booking import (
            Message as BookingMessage,
            PaymentMethod,
            Reservation,
            ReservationGuest,
            SavedList,
        )

        property_template = state.properties[0] if state.properties else None
        reservation_template = state.reservations[0] if getattr(state, "reservations", None) else None
        saved_list_template = state.saved_lists[0] if getattr(state, "saved_lists", None) else None
        payment_template = state.payment_methods[0] if getattr(state, "payment_methods", None) else None
        message_template = state.messages[0] if getattr(state, "messages", None) else None
        if all(
            template is None
            for template in (
                property_template,
                reservation_template,
                saved_list_template,
                payment_template,
                message_template,
            )
        ):
            return
        for spec in decoys:
            if not isinstance(spec, dict):
                continue
            dtype = str(spec.get("type", "property")).lower()
            if dtype == "saved_list":
                created_at = _coerce_timestamp(spec.get("created_at")) or datetime.now(timezone.utc)
                updated_at = _coerce_timestamp(spec.get("updated_at")) or created_at
                if saved_list_template is not None:
                    saved_list = saved_list_template.model_copy(deep=True)
                    saved_list.id = _state_next_id(state, "list", rng=_rng, fallback_seed=114)
                    saved_list.name = spec.get("name", saved_list.name)
                    saved_list.property_ids = list(spec.get("property_ids", saved_list.property_ids))
                    saved_list.created_at = created_at
                    saved_list.updated_at = updated_at
                else:
                    saved_list = SavedList(
                        id=_state_next_id(state, "list", rng=_rng, fallback_seed=114),
                        name=spec.get("name", "Decoy list"),
                        property_ids=list(spec.get("property_ids", [])),
                        created_at=created_at,
                        updated_at=updated_at,
                    )
                state.saved_lists.insert(0, saved_list)
                continue
            if dtype == "payment_method":
                if payment_template is not None:
                    payment_method = payment_template.model_copy(deep=True)
                    payment_method.id = _state_next_id(state, "pm", rng=_rng, fallback_seed=115)
                    payment_method.card_type = spec.get("card_type", payment_method.card_type)
                    payment_method.last_four = str(spec.get("last_four", payment_method.last_four))
                    payment_method.expiry = spec.get("expiry", payment_method.expiry)
                    payment_method.holder_name = spec.get(
                        "holder_name",
                        getattr(state, "owner_name", payment_method.holder_name),
                    )
                    payment_method.is_default = bool(spec.get("is_default", False))
                else:
                    payment_method = PaymentMethod(
                        id=_state_next_id(state, "pm", rng=_rng, fallback_seed=115),
                        card_type=spec.get("card_type", "Visa"),
                        last_four=str(spec.get("last_four", "1111")),
                        expiry=spec.get("expiry", "12/29"),
                        holder_name=spec.get("holder_name", getattr(state, "owner_name", "Jordan Parker")),
                        is_default=bool(spec.get("is_default", False)),
                    )
                state.payment_methods.insert(0, payment_method)
                continue
            if dtype == "message":
                prop = None
                property_id = spec.get("property_id")
                property_name = spec.get("property_name")
                if property_id and hasattr(state, "get_property"):
                    prop = state.get_property(property_id)
                if prop is None and property_name:
                    prop = next(
                        (candidate for candidate in state.properties if candidate.name == property_name),
                        None,
                    )
                if prop is None:
                    if property_template is None:
                        continue
                    prop = property_template.model_copy(deep=True)
                    prop.id = _state_next_id(state, "prop", rng=_rng, fallback_seed=116)
                    prop.name = property_name or prop.name
                    prop.city = spec.get("city", prop.city)
                    prop.country = spec.get("country", prop.country)
                    state.properties.insert(0, prop)
                created_at = _coerce_timestamp(spec.get("created_at")) or datetime.now(timezone.utc)
                if message_template is not None:
                    message = message_template.model_copy(deep=True)
                    message.id = _state_next_id(state, "msg", rng=_rng, fallback_seed=117)
                    message.property_id = prop.id
                    message.property_name = spec.get("property_name", prop.name)
                    message.reservation_id = spec.get("reservation_id", message.reservation_id)
                    message.subject = spec.get("subject", message.subject)
                    message.body = spec.get("body", message.body)
                    message.sender = spec.get("sender", message.sender)
                    message.read = bool(spec.get("read", False))
                    message.created_at = created_at
                else:
                    message = BookingMessage(
                        id=_state_next_id(state, "msg", rng=_rng, fallback_seed=117),
                        property_id=prop.id,
                        property_name=spec.get("property_name", prop.name),
                        reservation_id=spec.get("reservation_id", ""),
                        subject=spec.get("subject", ""),
                        body=spec.get("body", ""),
                        sender=spec.get("sender", "property"),
                        read=bool(spec.get("read", False)),
                        created_at=created_at,
                    )
                state.messages.insert(0, message)
                continue
            if dtype == "reservation":
                prop = None
                property_id = spec.get("property_id")
                property_name = spec.get("property_name")
                if property_id and hasattr(state, "get_property"):
                    prop = state.get_property(property_id)
                if prop is None and property_name:
                    prop = next(
                        (candidate for candidate in state.properties if candidate.name == property_name),
                        None,
                    )
                if prop is None:
                    prop = property_template
                if prop is None:
                    continue
                base_room = prop.room_types[0] if prop.room_types else None
                if reservation_template is not None:
                    reservation = reservation_template.model_copy(deep=True)
                else:
                    if base_room is None:
                        continue
                    reservation = Reservation(
                        id=_state_next_id(state, "res", rng=_rng, fallback_seed=113),
                        property_id=prop.id,
                        property_name=prop.name,
                        room_type_id=base_room.id,
                        room_type_name=base_room.name,
                        check_in="2026-06-01",
                        check_out="2026-06-03",
                        nights=2,
                        guests=2,
                        rooms=1,
                        price_per_night=base_room.price_per_night,
                        total_price=base_room.price_per_night * 2,
                        booked_at=datetime.now(timezone.utc),
                        guest_info=ReservationGuest(
                            full_name=getattr(state, "owner_name", "Jordan Parker"),
                            email=getattr(state, "owner_email", "guest@example.com"),
                        ),
                        payment_method_id=state.payment_methods[0].id if getattr(state, "payment_methods", None) else "",
                    )
                check_in = str(spec.get("check_in", reservation.check_in))
                check_out = str(spec.get("check_out", reservation.check_out))
                if spec.get("room_type_name"):
                    room = next(
                        (candidate for candidate in prop.room_types if candidate.name == spec.get("room_type_name")),
                        base_room,
                    )
                else:
                    room = base_room
                reservation.id = spec.get(
                    "id",
                    _state_next_id(state, "res", rng=_rng, fallback_seed=113),
                )
                reservation.property_id = prop.id
                reservation.property_name = spec.get("property_name", prop.name)
                reservation.room_type_id = spec.get("room_type_id", room.id if room is not None else reservation.room_type_id)
                reservation.room_type_name = spec.get("room_type_name", room.name if room is not None else reservation.room_type_name)
                reservation.check_in = check_in
                reservation.check_out = check_out
                reservation.nights = int(spec.get(
                    "nights",
                    max(1, (datetime.fromisoformat(check_out) - datetime.fromisoformat(check_in)).days),
                ))
                reservation.guests = int(spec.get("guests", reservation.guests))
                reservation.rooms = int(spec.get("rooms", reservation.rooms))
                reservation.price_per_night = float(spec.get(
                    "price_per_night",
                    room.price_per_night if room is not None else reservation.price_per_night,
                ))
                reservation.taxes_and_fees = float(spec.get("taxes_and_fees", reservation.taxes_and_fees))
                reservation.total_price = float(spec.get(
                    "total_price",
                    reservation.price_per_night * reservation.nights + reservation.taxes_and_fees,
                ))
                reservation.currency = spec.get("currency", reservation.currency)
                reservation.status = spec.get("status", reservation.status)
                booked_at = _coerce_timestamp(spec.get("booked_at"))
                if booked_at is None:
                    booked_days_ago = int(spec.get("booked_days_ago", 10))
                    booked_at = datetime.now(timezone.utc) - timedelta(days=booked_days_ago)
                reservation.booked_at = booked_at
                if room is not None:
                    reservation.cancellation_policy = room.cancellation_policy.model_copy(deep=True)
                    reservation.meals_included = room.meals_included
                reservation.payment_method_id = spec.get(
                    "payment_method_id",
                    reservation.payment_method_id or (state.payment_methods[0].id if getattr(state, "payment_methods", None) else ""),
                )
                reservation.confirmation_number = spec.get(
                    "confirmation_number",
                    reservation.confirmation_number or f"BKG{_rng.randint(100000, 999999)}",
                )
                if reservation_template is None:
                    reservation.guest_info = ReservationGuest(
                        full_name=getattr(state, "owner_name", "Jordan Parker"),
                        email=getattr(state, "owner_email", "guest@example.com"),
                        phone=getattr(state, "owner_phone", ""),
                        country=getattr(state, "owner_nationality", ""),
                    )
                state.reservations.insert(0, reservation)
                continue

            if property_template is None:
                continue
            prop = property_template.model_copy(deep=True)
            prop.id = _state_next_id(state, "prop", rng=_rng, fallback_seed=101)
            prop.name = spec.get("name", prop.name)
            prop.property_type = spec.get("property_type", prop.property_type)
            prop.star_rating = int(spec.get("star_rating", prop.star_rating))
            prop.city = spec.get("city", prop.city)
            prop.country = spec.get("country", prop.country)
            prop.neighborhood = spec.get("neighborhood", prop.neighborhood)
            prop.address = spec.get("address", prop.address)
            prop.description = spec.get("description", prop.description)
            prop.short_description = spec.get("short_description", prop.short_description)
            prop.review_score = float(spec.get("review_score", prop.review_score))
            prop.review_score_label = spec.get("review_score_label", _score_label(prop.review_score))
            prop.review_count = int(spec.get("review_count", max(prop.review_count // 2, 100)))
            prop.amenities = list(spec.get("amenities", prop.amenities))
            prop.popular_facilities = list(spec.get("popular_facilities", prop.popular_facilities))
            prop.is_genius_property = bool(spec.get("is_genius_property", prop.is_genius_property))
            prop.genius_discount_pct = int(spec.get("genius_discount_pct", prop.genius_discount_pct))
            prop.currency = spec.get("currency", prop.currency)

            base_rooms = property_template.room_types or []
            if base_rooms:
                if spec.get("rooms"):
                    new_rooms = []
                    for room_spec in spec.get("rooms", []):
                        room = base_rooms[0].model_copy(deep=True)
                        room.id = _state_next_id(state, "room", rng=_rng, fallback_seed=102)
                        room.property_id = prop.id
                        room.name = room_spec.get("name", room.name)
                        room.description = room_spec.get("description", room.description)
                        room.max_occupancy = int(room_spec.get("max_occupancy", room.max_occupancy))
                        room.bed_type = room_spec.get("bed_type", room.bed_type)
                        room.bed_count = int(room_spec.get("bed_count", room.bed_count))
                        room.room_size_sqm = float(room_spec.get("room_size_sqm", room.room_size_sqm))
                        room.price_per_night = float(room_spec.get("price", room.price_per_night))
                        room.original_price = (
                            float(room_spec["original_price"])
                            if room_spec.get("original_price") is not None
                            else room.original_price
                        )
                        room.amenities = list(room_spec.get("amenities", room.amenities))
                        room.meals_included = room_spec.get("meals_included", room.meals_included)
                        room.is_available = bool(room_spec.get("is_available", room.is_available))
                        room.rooms_left = int(room_spec.get("rooms_left", room.rooms_left))
                        room.view_type = room_spec.get("view_type", room.view_type)
                        cancel_type = room_spec.get("cancel_type") or room_spec.get("cancellation_policy")
                        if cancel_type:
                            policy = room.cancellation_policy.model_copy(deep=True)
                            policy.type = cancel_type
                            policy.description = (
                                "Non-refundable rate"
                                if cancel_type == "non_refundable"
                                else policy.description
                            )
                            room.cancellation_policy = policy
                        new_rooms.append(room)
                    prop.room_types = new_rooms
                else:
                    room = base_rooms[0].model_copy(deep=True)
                    room.id = _state_next_id(state, "room", rng=_rng, fallback_seed=103)
                    room.property_id = prop.id
                    room.name = spec.get("room_name", room.name)
                    room.price_per_night = float(spec.get("price", room.price_per_night))
                    if spec.get("cancellation_policy") or spec.get("refundable") is False:
                        policy = room.cancellation_policy.model_copy(deep=True)
                        policy.type = "non_refundable"
                        policy.description = "Non-refundable rate"
                        room.cancellation_policy = policy
                    prop.room_types = [room]

            state.properties.insert(0, prop)
        if hasattr(state, "touch"):
            state.touch()
        return

    if hasattr(state, "posts") and hasattr(state, "subreddits"):
        from webagentbench.backend.models.base import utc_now
        from webagentbench.backend.models.reddit import Comment, Message, Notification, Post, Subreddit

        subreddit_template = state.subreddits[0] if state.subreddits else None
        post_template = state.posts[0] if state.posts else None
        comment_template = state.comments[0] if getattr(state, "comments", None) else None
        message_template = state.messages[0] if getattr(state, "messages", None) else None
        notification_template = state.notifications[0] if getattr(state, "notifications", None) else None

        def ensure_subreddit(name: str, spec: dict[str, Any]) -> Any:
            existing = state.get_subreddit_by_name(name)
            if existing is not None:
                return existing
            created_at = _coerce_timestamp(spec.get("created_at")) or utc_now()
            if subreddit_template is not None:
                sub = subreddit_template.model_copy(deep=True)
                sub.id = _state_next_id(state, "sub", rng=_rng, fallback_seed=104)
                sub.name = name
                sub.display_name = spec.get("display_name", f"r/{name}")
                sub.description = spec.get("description", sub.description)
                sub.public_description = spec.get("public_description", sub.public_description)
                sub.subscriber_count = int(spec.get("subscribers", spec.get("subscriber_count", sub.subscriber_count)))
                sub.active_users = int(spec.get("active_users", sub.active_users))
                sub.created_at = created_at
            else:
                sub = Subreddit(
                    id=_state_next_id(state, "sub", rng=_rng, fallback_seed=104),
                    name=name,
                    display_name=spec.get("display_name", f"r/{name}"),
                    description=spec.get("description", ""),
                    public_description=spec.get("public_description", ""),
                    subscriber_count=int(spec.get("subscribers", spec.get("subscriber_count", 1000))),
                    active_users=int(spec.get("active_users", 100)),
                    created_at=created_at,
                )
            state.subreddits.append(sub)
            return sub

        def find_post(spec: dict[str, Any]) -> Any:
            post_id = spec.get("post_id")
            if post_id:
                return state.get_post(post_id)
            post_title = spec.get("post_title") or spec.get("title")
            if post_title:
                for post in state.posts:
                    if post.title == post_title:
                        return post
            return post_template

        for spec in decoys:
            if not isinstance(spec, dict):
                continue
            dtype = spec.get("type", "post")
            if dtype == "subreddit":
                ensure_subreddit(spec.get("name", f"sub_{_rng.randint(100, 999)}"), spec)
                continue
            if dtype == "post":
                sub_name = spec.get("subreddit", post_template.subreddit_name if post_template else "all")
                sub = ensure_subreddit(sub_name, spec)
                created_at = _coerce_timestamp(spec.get("created_at")) or utc_now()
                if post_template is not None:
                    post = post_template.model_copy(deep=True)
                    post.id = _state_next_id(state, "post", rng=_rng, fallback_seed=105)
                    post.subreddit_id = sub.id
                    post.subreddit_name = sub.name
                    post.author_name = spec.get("author", post.author_name)
                    post.title = spec.get("title", post.title)
                    post.body = spec.get("body", post.body)
                    post.score = int(spec.get("score", post.score))
                    post.comment_count = int(spec.get("comments", spec.get("comment_count", post.comment_count)))
                    post.created_at = created_at
                    post.flair_text = spec.get("flair_text", post.flair_text)
                    post.is_saved = bool(spec.get("is_saved", post.is_saved))
                    post.is_hidden = bool(spec.get("is_hidden", post.is_hidden))
                    post.vote_direction = int(spec.get("vote_direction", post.vote_direction))
                    post.permalink = spec.get("permalink", f"/r/{sub.name}/comments/{post.id}")
                else:
                    post = Post(
                        id=_state_next_id(state, "post", rng=_rng, fallback_seed=105),
                        subreddit_id=sub.id,
                        subreddit_name=sub.name,
                        author_name=spec.get("author", "decoy_user"),
                        title=spec.get("title", "Decoy post"),
                        body=spec.get("body", ""),
                        score=int(spec.get("score", 1)),
                        upvote_ratio=float(spec.get("upvote_ratio", 0.8)),
                        comment_count=int(spec.get("comments", spec.get("comment_count", 0))),
                        created_at=created_at,
                        flair_text=spec.get("flair_text"),
                        is_saved=bool(spec.get("is_saved", False)),
                        is_hidden=bool(spec.get("is_hidden", False)),
                        vote_direction=int(spec.get("vote_direction", 0)),
                        permalink=spec.get("permalink", ""),
                    )
                state.posts.insert(0, post)
                if post.is_saved and post.id not in state.saved_post_ids:
                    state.saved_post_ids.append(post.id)
                if post.is_hidden and post.id not in state.hidden_post_ids:
                    state.hidden_post_ids.append(post.id)
                continue
            if dtype == "comment":
                parent_post = find_post(spec)
                if parent_post is None:
                    continue
                created_at = _coerce_timestamp(spec.get("created_at")) or utc_now()
                if comment_template is not None:
                    comment = comment_template.model_copy(deep=True)
                    comment.id = _state_next_id(state, "comment", rng=_rng, fallback_seed=106)
                    comment.post_id = parent_post.id
                    comment.parent_id = spec.get("parent_id", comment.parent_id)
                    comment.author_name = spec.get("author", comment.author_name)
                    comment.body = spec.get("body", comment.body)
                    comment.score = int(spec.get("score", comment.score))
                    comment.created_at = created_at
                    comment.depth = int(spec.get("depth", comment.depth))
                    comment.is_saved = bool(spec.get("is_saved", comment.is_saved))
                    comment.vote_direction = int(spec.get("vote_direction", comment.vote_direction))
                else:
                    comment = Comment(
                        id=_state_next_id(state, "comment", rng=_rng, fallback_seed=106),
                        post_id=parent_post.id,
                        parent_id=spec.get("parent_id"),
                        author_name=spec.get("author", "decoy_user"),
                        body=spec.get("body", ""),
                        score=int(spec.get("score", 1)),
                        created_at=created_at,
                        depth=int(spec.get("depth", 0)),
                        is_saved=bool(spec.get("is_saved", False)),
                        vote_direction=int(spec.get("vote_direction", 0)),
                    )
                state.comments.append(comment)
                if comment.is_saved and comment.id not in state.saved_comment_ids:
                    state.saved_comment_ids.append(comment.id)
                continue
            if dtype == "message":
                created_at = _coerce_timestamp(spec.get("created_at")) or utc_now()
                if message_template is not None:
                    message = message_template.model_copy(deep=True)
                    message.id = _state_next_id(state, "msg", rng=_rng, fallback_seed=107)
                    message.from_user = spec.get("from_user", message.from_user)
                    message.to_user = spec.get("to_user", state.owner_username)
                    message.subject = spec.get("subject", message.subject)
                    message.body = spec.get("body", message.body)
                    message.created_at = created_at
                    message.is_read = bool(spec.get("is_read", message.is_read))
                else:
                    message = Message(
                        id=_state_next_id(state, "msg", rng=_rng, fallback_seed=107),
                        from_user=spec.get("from_user", "decoy_user"),
                        to_user=spec.get("to_user", state.owner_username),
                        subject=spec.get("subject", ""),
                        body=spec.get("body", ""),
                        created_at=created_at,
                        is_read=bool(spec.get("is_read", False)),
                    )
                state.messages.insert(0, message)
                continue
            if dtype == "notification":
                created_at = _coerce_timestamp(spec.get("created_at")) or utc_now()
                if notification_template is not None:
                    notification = notification_template.model_copy(deep=True)
                    notification.id = _state_next_id(state, "notif", rng=_rng, fallback_seed=118)
                    notification.type = spec.get("type", notification.type)
                    notification.title = spec.get("title", notification.title)
                    notification.body = spec.get("body", notification.body)
                    notification.created_at = created_at
                    notification.is_read = bool(spec.get("is_read", notification.is_read))
                    notification.related_post_id = spec.get("related_post_id", notification.related_post_id)
                    notification.related_comment_id = spec.get("related_comment_id", notification.related_comment_id)
                    notification.subreddit_name = spec.get("subreddit_name", notification.subreddit_name)
                    notification.from_user = spec.get("from_user", notification.from_user)
                else:
                    notification = Notification(
                        id=_state_next_id(state, "notif", rng=_rng, fallback_seed=118),
                        type=spec.get("type", "mention"),
                        title=spec.get("title", "Notification"),
                        body=spec.get("body", ""),
                        created_at=created_at,
                        is_read=bool(spec.get("is_read", False)),
                        related_post_id=spec.get("related_post_id"),
                        related_comment_id=spec.get("related_comment_id"),
                        subreddit_name=spec.get("subreddit_name"),
                        from_user=spec.get("from_user"),
                    )
                state.notifications.insert(0, notification)
        if hasattr(state, "touch"):
            state.touch()


def _split_information(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Split key information across multiple emails to stress State Tracking.

    Instead of one email containing all requirements, the agent must
    read and aggregate from N separate sources.
    """
    # This is task-specific. The params should specify:
    # - source_email_id: which email to split
    # - split_count: how many emails to create
    # - split_senders: list of (name, addr) for each fragment
    source_id = params.get("source_email_id")
    if not source_id or not hasattr(state, "emails"):
        return

    source = next((e for e in state.emails if e.id == source_id), None)
    if source is None:
        return

    split_count = params.get("split_count", 3)
    fragments = params.get("fragments", [])

    from webagentbench.backend.models.gmail import Email

    import random as _random
    _rng = rng or _random.Random(88)
    _COLLEAGUE_NAMES = [
        ("Priya Sharma", "priya.sharma@thornton.com"),
        ("Daniel Osei", "daniel.osei@thornton.com"),
        ("Lena Kowalski", "lena.kowalski@thornton.com"),
        ("Marcus Tan", "marcus.tan@thornton.com"),
        ("Sofia Bergström", "sofia.bergstrom@thornton.com"),
    ]
    for i, fragment in enumerate(fragments[:split_count]):
        fallback_name, fallback_addr = _COLLEAGUE_NAMES[i % len(_COLLEAGUE_NAMES)]
        email = Email(
            id=f"email_{_rng.randint(10000, 99999)}",
            thread_id=f"thread_{_rng.randint(10000, 99999)}",
            from_name=fragment.get("from_name", fallback_name),
            from_addr=fragment.get("from", fallback_addr),
            to=source.to,
            subject=fragment.get("subject", f"Re: {source.subject} (part {i+1})"),
            body=fragment.get("body", ""),
            timestamp=source.timestamp,
            labels=["inbox"],
            is_read=False,
        )
        state.emails.append(email)


def _add_contradictory_update(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add a newer email that contradicts the original to stress Backtracking/Verification.

    The agent finds info in email A, then later encounters email B
    (newer, from same sender) that says "correction: ..." — the agent
    must recognize A is outdated and use B's data.
    """
    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    import random as _random
    _rng = rng or _random.Random(77)
    fallback_timestamp = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    timestamp = params.get("timestamp")
    if timestamp is None:
        timestamp = _latest_state_timestamp(state, fallback_timestamp) + timedelta(minutes=30)
    email = Email(
        id=params.get("email_id", f"email_{_rng.randint(10000, 99999)}"),
        thread_id=params.get("thread_id", f"thread_{_rng.randint(10000, 99999)}"),
        from_name=params.get("from_name", ""),
        from_addr=params.get("from", "update@thornton.com"),
        to=params.get("to", ["me@thornton.com"]),
        subject=params.get("subject", "CORRECTION: Previous email had errors"),
        body=params.get("body", "Please disregard my previous email. The correct information is..."),
        timestamp=timestamp,
        labels=params.get("labels", ["inbox"]),
        is_read=False,
    )
    # Insert at top (most recent)
    state.emails.insert(0, email)


def _plant_wrong_answer(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Plant a prominent email with a plausible but wrong answer to stress Backtracking.

    The agent will naturally find this first (it's starred, recent, prominent).
    The correct answer is in a less obvious email. The agent must realize
    the first answer is wrong and look harder.
    """
    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    import random as _random
    _rng = rng or _random.Random(66)
    fallback_timestamp = datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc)
    timestamp = params.get("timestamp")
    if timestamp is None:
        timestamp = _latest_state_timestamp(state, fallback_timestamp) + timedelta(minutes=15)
    email = Email(
        id=params.get("email_id", f"email_{_rng.randint(10000, 99999)}"),
        thread_id=params.get("thread_id", f"thread_{_rng.randint(10000, 99999)}"),
        from_name=params.get("from_name", "Helpful Colleague"),
        from_addr=params.get("from", "helpful@thornton.com"),
        to=params.get("to", ["me@thornton.com"]),
        subject=params.get("subject", ""),
        body=params.get("body", ""),
        timestamp=timestamp,
        labels=params.get("labels", ["inbox"]),
        is_read=False,
        is_starred=params.get("starred", True),
    )
    state.emails.insert(0, email)


def _increase_distractors(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add more distractor emails to increase noise for State Tracking.

    Some distractors are on the same topic as the task (topical noise)
    rather than unrelated (random noise). Topical noise is much harder.
    """
    import random as _random

    count = params.get("count", 20)
    topical_count = params.get("topical_count", 5)
    topical_subjects = params.get("topical_subjects", [])

    if not hasattr(state, "emails"):
        return

    from webagentbench.backend.models.gmail import Email

    _rng = rng or _random.Random(42)

    _GENERIC_SUBJECTS = [
        "Weekly status update", "Budget review notes", "Team meeting recap",
        "Project timeline update", "Vendor contract follow-up",
        "HR policy change notification", "Office supply request",
        "Quarterly review preparation", "Travel reimbursement update",
        "New process rollout — please read", "Infrastructure migration update",
        "Client feedback summary", "Training session registration",
        "Benefits enrollment reminder", "Security awareness update",
        "End-of-quarter checklist", "Workspace reorganization plan",
        "Cross-team collaboration proposal", "Performance review schedule",
        "Holiday calendar finalized",
    ]
    _NAMES = [
        ("Priya Sharma", "priya.sharma@thornton.com"),
        ("Daniel Osei", "daniel.osei@thornton.com"),
        ("Lena Kowalski", "lena.kowalski@thornton.com"),
        ("Marcus Tan", "marcus.tan@thornton.com"),
        ("Sofia Bergström", "sofia.bergstrom@thornton.com"),
        ("Yuki Tanaka", "yuki.tanaka@thornton.com"),
        ("Carlos Mendez", "carlos.mendez@thornton.com"),
        ("Aisha Hassan", "aisha.hassan@thornton.com"),
        ("Nikolai Petrov", "nikolai.petrov@thornton.com"),
        ("Elena Vasquez", "elena.vasquez@thornton.com"),
        ("Tomás Ferreira", "tomas.ferreira@thornton.com"),
        ("Mei-Lin Wu", "meiling.wu@thornton.com"),
        ("David Okonkwo", "david.okonkwo@thornton.com"),
        ("Rachel Andersen", "rachel.andersen@thornton.com"),
        ("Omar Farid", "omar.farid@thornton.com"),
        ("Ingrid Larsson", "ingrid.larsson@thornton.com"),
        ("James Whitfield", "james.whitfield@thornton.com"),
        ("Fatima Al-Rashid", "fatima.alrashid@thornton.com"),
        ("Patrick O'Brien", "patrick.obrien@thornton.com"),
        ("Hannah Müller", "hannah.mueller@thornton.com"),
    ]
    _BODIES = [
        "Hi team, sharing a quick update. Please review and let me know if anything needs adjustment.",
        "Just wanted to flag this for your attention. Happy to discuss in our next sync.",
        "Passing this along for visibility. No immediate action required from your side.",
        "Following up on our earlier conversation. The attached notes have the latest details.",
        "Please take a look when you get a chance. I'll follow up next week if needed.",
    ]

    fallback_timestamp = datetime(2026, 1, 14, 10, 0, tzinfo=timezone.utc)
    base_dt = _latest_state_timestamp(state, fallback_timestamp)

    for i in range(count):
        if i < topical_count and i < len(topical_subjects):
            subject = topical_subjects[i]
        else:
            subject = _rng.choice(_GENERIC_SUBJECTS)

        name, addr = _NAMES[i % len(_NAMES)]
        body = _rng.choice(_BODIES)
        offset_secs = _rng.randint(-86400 * 7, 86400 * 2)

        email = Email(
            id=f"email_{_rng.randint(10000, 99999)}",
            thread_id=f"thread_{_rng.randint(10000, 99999)}",
            from_name=name,
            from_addr=addr,
            to=["me@thornton.com"],
            subject=subject,
            body=body,
            timestamp=base_dt + timedelta(seconds=offset_secs),
            labels=["inbox"],
            is_read=_rng.random() > 0.35,
        )
        state.emails.append(email)


def _alias_entities(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add contacts/emails with confusingly similar names to stress Grounding.

    E.g., "Alex Chen (Engineering)" vs "Alex Chen (Marketing)" vs "Alexandra Chen"
    """
    aliases = params.get("aliases", [])
    entities = params.get("entities", [])

    if hasattr(state, "contacts"):
        from webagentbench.backend.models.gmail import Contact
        _rng = _entity_rng(rng, 55)

        for alias in aliases:
            contact = Contact(
                id=f"contact_{_rng.randint(10000, 99999)}",
                name=alias.get("name", ""),
                email=alias.get("email", ""),
                note=alias.get("note", ""),
            )
            state.contacts.append(contact)
        return

    if hasattr(state, "user_profiles"):
        from webagentbench.backend.models.base import utc_now
        from webagentbench.backend.models.reddit import Message, UserProfile

        _rng = _entity_rng(rng, 56)
        template_profile = state.user_profiles[0] if state.user_profiles else None
        template_message = state.messages[0] if getattr(state, "messages", None) else None

        for entity in entities:
            if not isinstance(entity, dict) or entity.get("type") != "user":
                continue
            alias_name = entity.get("alias_name")
            if not alias_name:
                continue
            original_name = entity.get("original_name", alias_name)
            profile_template = next(
                (profile for profile in state.user_profiles if profile.username == original_name),
                template_profile,
            )
            if profile_template is not None:
                profile = profile_template.model_copy(deep=True)
                profile.id = _state_next_id(state, "user", rng=_rng, fallback_seed=108)
                profile.username = alias_name
                profile.display_name = entity.get("display_name", alias_name)
                profile.about = entity.get("about", profile.about)
            else:
                profile = UserProfile(
                    id=_state_next_id(state, "user", rng=_rng, fallback_seed=108),
                    username=alias_name,
                    display_name=entity.get("display_name", alias_name),
                    about=entity.get("about", ""),
                )
            state.user_profiles.append(profile)

            subject = entity.get("message_subject")
            body = entity.get("message_body")
            if subject and body:
                created_at = _coerce_timestamp(entity.get("sent_at")) or utc_now()
                if template_message is not None:
                    message = template_message.model_copy(deep=True)
                    message.id = _state_next_id(state, "msg", rng=_rng, fallback_seed=109)
                    message.from_user = alias_name
                    message.to_user = state.owner_username
                    message.subject = subject
                    message.body = body
                    message.created_at = created_at
                    message.is_read = bool(entity.get("is_read", False))
                else:
                    message = Message(
                        id=_state_next_id(state, "msg", rng=_rng, fallback_seed=109),
                        from_user=alias_name,
                        to_user=state.owner_username,
                        subject=subject,
                        body=body,
                        created_at=created_at,
                        is_read=bool(entity.get("is_read", False)),
                    )
                state.messages.insert(0, message)
        if hasattr(state, "touch"):
            state.touch()


def _hide_in_non_obvious_location(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Move task-relevant info to a non-obvious location to stress Exploration.

    E.g., move an email to a custom label instead of inbox, or put key
    info in a contact note instead of an email body.
    """
    email_id = params.get("email_id")
    email_ids = params.get("email_ids")
    subject_contains = str(params.get("subject_contains", "")).strip().lower()
    move_to_label = params.get("move_to_label")

    target_ids: set[str] = set()
    if isinstance(email_ids, list):
        target_ids.update(str(email_id) for email_id in email_ids)
    elif isinstance(email_ids, str):
        target_ids.add(email_ids)
    if email_id:
        target_ids.add(str(email_id))
    if subject_contains and hasattr(state, "emails"):
        target_ids.update(
            str(email.id)
            for email in state.emails
            if subject_contains in getattr(email, "subject", "").lower()
        )

    if target_ids and move_to_label and hasattr(state, "emails"):
        for email in state.emails:
            if email.id in target_ids:
                email.labels = [move_to_label]


# ---------------------------------------------------------------------------
# Robinhood seed actions
# ---------------------------------------------------------------------------

def _rh_notification_specs(params: dict[str, Any]) -> list[dict[str, Any]]:
    specs = params.get("decoys") or params.get("notifications") or []
    if not specs and params.get("messages"):
        specs = [
            {"title": "Notification", "message": message}
            for message in params.get("messages", [])
        ]
    if not specs and params.get("count"):
        symbols = params.get("symbols") or ["AAPL", "MSFT", "TSLA"]
        theme = params.get("theme", "market")
        count = int(params.get("count", 0))
        specs = [
            {
                "type": theme,
                "title": f"{symbols[i % len(symbols)]} update",
                "message": f"{symbols[i % len(symbols)]} triggered a {theme} notification.",
            }
            for i in range(count)
        ]
    return [spec if isinstance(spec, dict) else {"title": "Account Update", "message": str(spec)} for spec in specs]


def _rh_normalize_notification_type(raw_type: Any) -> str:
    if not raw_type:
        return "security_alert"
    notification_type = str(raw_type)
    if notification_type in {
        "order_fill",
        "price_alert",
        "dividend",
        "earnings",
        "transfer_complete",
        "security_alert",
        "recurring_investment",
        "tax_document",
        "margin_call",
        "corporate_action",
    }:
        return notification_type
    return {
        "account": "security_alert",
        "alert": "price_alert",
        "alerts": "price_alert",
        "market": "price_alert",
        "order": "order_fill",
        "orders": "order_fill",
        "price": "price_alert",
        "recurring": "recurring_investment",
        "system": "security_alert",
        "tax": "tax_document",
        "transfer": "transfer_complete",
        "watchlist": "price_alert",
        "dividend_notice": "dividend",
        "earnings_alert": "earnings",
        "margin": "margin_call",
        "corporate": "corporate_action",
    }.get(notification_type, "security_alert")


def _rh_add_decoy_notifications(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add misleading notifications to stress Grounding / State Tracking."""
    if not hasattr(state, "notifications"):
        return
    from webagentbench.backend.models.robinhood import Notification
    from webagentbench.backend.models.base import utc_now
    import random as _random
    _rng = rng or _random.Random(42)

    for decoy in _rh_notification_specs(params):
        state.notifications.append(Notification(
            id=f"notif_decoy_{_rng.randint(10000, 99999)}",
            type=_rh_normalize_notification_type(decoy.get("type", decoy.get("category", "system"))),
            title=decoy.get("title", "Notification"),
            message=decoy.get("message", decoy.get("body", "")),
            timestamp=utc_now(),
            is_read=decoy.get("is_read", False),
        ))


def _rh_add_noise_orders(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add distractor pending orders to stress State Tracking."""
    if not hasattr(state, "orders"):
        return
    from webagentbench.backend.models.robinhood import Order
    from webagentbench.backend.models.base import utc_now
    from decimal import Decimal
    import random as _random
    _rng = rng or _random.Random(42)

    noise_orders = list(params.get("orders", []))
    if not noise_orders and params.get("symbols"):
        symbols = params.get("symbols", [])
        count = int(params.get("count", len(symbols)))
        for i in range(count):
            symbol = symbols[i % len(symbols)]
            stock = state.get_stock(symbol) if hasattr(state, "get_stock") else None
            base_price = Decimal(str(getattr(stock, "price", "100.00")))
            noise_orders.append({
                "symbol": symbol,
                "side": params.get("side", "buy" if i % 2 == 0 else "sell"),
                "order_type": params.get("order_type", "limit"),
                "quantity": params.get("quantity", (i % 4) + 1),
                "limit_price": params.get("limit_price", str(base_price)),
            })
    for spec in noise_orders:
        symbol = spec.get("symbol")
        if not symbol:
            continue
        stock = state.get_stock(symbol) if hasattr(state, "get_stock") else None
        base_price = Decimal(str(getattr(stock, "price", "100.00")))
        raw_limit_price = spec.get("limit_price", base_price)
        order_type = spec.get("order_type", "limit")
        if raw_limit_price in (None, ""):
            price = None if order_type == "market" else base_price
        else:
            try:
                price = Decimal(str(raw_limit_price))
            except (TypeError, ValueError, ArithmeticError):
                price = None if order_type == "market" else base_price
        status = spec.get("status", "pending")
        state.orders.append(Order(
            id=f"ord_decoy_{_rng.randint(10000, 99999)}",
            symbol=symbol,
            side=spec.get("side", "buy"),
            order_type=order_type,
            quantity=Decimal(str(spec.get("quantity", 1))),
            filled_quantity=Decimal(str(spec.get("quantity", 1))) if status == "filled" else Decimal("0"),
            limit_price=price,
            time_in_force="gtc",
            status=status,
            created_at=utc_now(),
        ))


def _rh_add_misleading_alert(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add a price alert that could mislead the agent (Backtracking)."""
    if not hasattr(state, "price_alerts"):
        return
    from webagentbench.backend.models.robinhood import PriceAlert
    from webagentbench.backend.models.base import utc_now
    from decimal import Decimal
    import random as _random
    _rng = rng or _random.Random(42)

    alert_specs = params.get("alerts") or params.get("alert") or [params]
    if isinstance(alert_specs, dict):
        alert_specs = [alert_specs]

    for alert_spec in alert_specs:
        state.price_alerts.append(PriceAlert(
            id=f"alert_decoy_{_rng.randint(10000, 99999)}",
            symbol=alert_spec.get("symbol", "AAPL"),
            condition=alert_spec.get("condition", "above"),
            target_price=Decimal(str(alert_spec.get("target_price", "999.99"))),
            status=alert_spec.get("status", "triggered"),
            created_at=utc_now(),
            triggered_at=utc_now() if alert_spec.get("status") == "triggered" else None,
        ))


def _rh_add_confusing_positions(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add positions in confusingly similar stocks to stress Grounding."""
    if not hasattr(state, "positions"):
        return
    from webagentbench.backend.models.robinhood import Position, TaxLot
    from webagentbench.backend.models.base import utc_now
    from decimal import Decimal
    import random as _random
    _rng = rng or _random.Random(42)

    positions = list(params.get("positions", []))
    if not positions and params.get("symbols"):
        quantities = params.get("quantities", [])
        for i, symbol in enumerate(params.get("symbols", [])):
            positions.append({
                "symbol": symbol,
                "quantity": quantities[i] if i < len(quantities) else 10,
            })
    for spec in positions:
        symbol = spec.get("symbol")
        if not symbol:
            continue
        stock = state.get_stock(symbol) if hasattr(state, "get_stock") else None
        price = Decimal(str(spec.get("price", getattr(stock, "price", "100.00"))))
        qty = Decimal(str(spec.get("quantity", 10)))
        cost = Decimal(str(spec.get("cost_basis", str(price))))
        state.positions.append(Position(
            id=f"pos_decoy_{_rng.randint(10000, 99999)}",
            symbol=symbol,
            name=spec.get("name", getattr(stock, "name", symbol)),
            asset_type="stock",
            quantity=qty,
            avg_cost_basis=cost,
            current_price=price,
            day_change_pct=Decimal("0"),
            total_return=(price - cost) * qty,
            total_return_pct=((price - cost) / cost * 100) if cost else Decimal("0"),
            lots=[TaxLot(shares=qty, cost_per_share=cost, acquired_date=utc_now().date())],
        ))


def _rh_add_confusing_stocks(state: Any, params: dict[str, Any], *, rng=None) -> None:
    """Add search-result decoy stocks with similar symbols / names."""
    if not hasattr(state, "stocks"):
        return
    from webagentbench.backend.models.robinhood import HistoricalPrice, Stock
    from decimal import Decimal

    _rng = _entity_rng(rng, 57)
    template = state.stocks[0] if state.stocks else None
    if template is None:
        return

    stock_specs = list(params.get("stocks") or params.get("decoys") or [])
    if not stock_specs and params.get("symbols"):
        for symbol in params.get("symbols", []):
            stock_specs.append({"symbol": symbol})

    for spec in stock_specs:
        if not isinstance(spec, dict):
            continue
        symbol = spec.get("symbol")
        if not symbol:
            continue
        if state.get_stock(symbol) is not None:
            continue
        stock = template.model_copy(deep=True)
        stock.symbol = symbol
        stock.name = spec.get("name", symbol)
        stock.asset_type = spec.get("asset_type", stock.asset_type)
        stock.price = Decimal(str(spec.get("price", stock.price)))
        stock.previous_close = Decimal(str(spec.get("previous_close", stock.previous_close)))
        stock.day_change = Decimal(str(spec.get("day_change", stock.day_change)))
        stock.day_change_pct = Decimal(str(spec.get("day_change_pct", stock.day_change_pct)))
        stock.bid = Decimal(str(spec.get("bid", stock.bid)))
        stock.ask = Decimal(str(spec.get("ask", stock.ask)))
        stock.bid_size = int(spec.get("bid_size", stock.bid_size))
        stock.ask_size = int(spec.get("ask_size", stock.ask_size))
        stock.volume = int(spec.get("volume", stock.volume))
        stock.avg_volume = int(spec.get("avg_volume", stock.avg_volume))
        stock.market_cap = Decimal(str(spec["market_cap"])) if spec.get("market_cap") is not None else stock.market_cap
        stock.pe_ratio = Decimal(str(spec["pe_ratio"])) if spec.get("pe_ratio") is not None else stock.pe_ratio
        stock.eps = Decimal(str(spec["eps"])) if spec.get("eps") is not None else stock.eps
        stock.dividend_yield = (
            Decimal(str(spec["dividend_yield"]))
            if spec.get("dividend_yield") is not None
            else stock.dividend_yield
        )
        stock.fifty_two_week_high = Decimal(str(spec.get("fifty_two_week_high", stock.fifty_two_week_high)))
        stock.fifty_two_week_low = Decimal(str(spec.get("fifty_two_week_low", stock.fifty_two_week_low)))
        stock.sector = spec.get("sector", stock.sector)
        stock.industry = spec.get("industry", stock.industry)
        stock.about = spec.get("description", spec.get("about", stock.about))
        if spec.get("historical_prices"):
            stock.historical_prices = [
                HistoricalPrice(**hp) if isinstance(hp, dict) else hp
                for hp in spec.get("historical_prices", [])
            ]
        state.stocks.insert(0, stock)
    if hasattr(state, "touch"):
        state.touch()
