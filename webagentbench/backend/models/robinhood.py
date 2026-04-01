from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseEntity, BaseEnvState, utc_now


# ---------------------------------------------------------------------------
# 1. HistoricalPrice
# ---------------------------------------------------------------------------

class HistoricalPrice(BaseModel):
    date: date
    close: Decimal

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 2. TaxLot
# ---------------------------------------------------------------------------

class TaxLot(BaseModel):
    shares: Decimal
    cost_per_share: Decimal
    acquired_date: date

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 3. Position
# ---------------------------------------------------------------------------

class Position(BaseEntity):
    symbol: str
    name: str
    asset_type: Literal["stock", "etf", "crypto", "option"]
    quantity: Decimal
    avg_cost_basis: Decimal
    current_price: Decimal
    day_change_pct: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    lots: list[TaxLot] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Order
# ---------------------------------------------------------------------------

class Order(BaseEntity):
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"]
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    trail_amount: Decimal | None = None
    trail_pct: Decimal | None = None
    time_in_force: Literal["gfd", "gtc", "ioc", "opg"] = "gfd"
    status: Literal["pending", "partially_filled", "filled", "cancelled", "rejected"]
    extended_hours: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None


# ---------------------------------------------------------------------------
# 5. Stock
# ---------------------------------------------------------------------------

class Stock(BaseModel):
    symbol: str
    name: str
    asset_type: Literal["stock", "etf"]
    price: Decimal
    previous_close: Decimal
    day_change: Decimal
    day_change_pct: Decimal
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    volume: int
    avg_volume: int
    market_cap: Decimal | None = None
    pe_ratio: Decimal | None = None
    eps: Decimal | None = None
    dividend_yield: Decimal | None = None
    fifty_two_week_high: Decimal
    fifty_two_week_low: Decimal
    sector: str
    industry: str
    about: str
    historical_prices: list[HistoricalPrice] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 6. Greeks
# ---------------------------------------------------------------------------

class Greeks(BaseModel):
    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 7. OptionsContract
# ---------------------------------------------------------------------------

class OptionsContract(BaseModel):
    contract_id: str
    underlying: str
    option_type: Literal["call", "put"]
    strike: Decimal
    expiration: date
    bid: Decimal
    ask: Decimal
    last_price: Decimal
    volume: int
    open_interest: int
    implied_volatility: Decimal
    greeks: Greeks = Field(default_factory=Greeks)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 8. OptionsPosition
# ---------------------------------------------------------------------------

class OptionsPosition(BaseEntity):
    contract_id: str
    underlying_symbol: str
    option_type: Literal["call", "put"]
    strike_price: Decimal
    expiration_date: date
    quantity: int
    avg_cost: Decimal
    current_premium: Decimal
    greeks: Greeks = Field(default_factory=Greeks)
    status: Literal["open", "closed", "exercised", "expired"] = "open"


# ---------------------------------------------------------------------------
# 9. OptionsLeg
# ---------------------------------------------------------------------------

class OptionsLeg(BaseModel):
    side: Literal["buy", "sell"]
    option_type: Literal["call", "put"]
    strike: Decimal
    expiration: date
    quantity: int
    premium: Decimal

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 10. OptionsOrder
# ---------------------------------------------------------------------------

class OptionsOrder(BaseEntity):
    strategy: Literal[
        "single", "vertical", "iron_condor", "straddle", "strangle",
        "covered_call", "protective_put",
    ]
    legs: list[OptionsLeg] = Field(default_factory=list)
    status: Literal["pending", "filled", "cancelled", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)
    filled_at: datetime | None = None


# ---------------------------------------------------------------------------
# 11. Watchlist
# ---------------------------------------------------------------------------

class Watchlist(BaseEntity):
    name: str
    symbols: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# 12. Transfer
# ---------------------------------------------------------------------------

class Transfer(BaseEntity):
    direction: Literal["deposit", "withdrawal"]
    amount: Decimal
    status: Literal["pending", "completed", "failed", "reversed"] = "pending"
    bank_account_id: str
    initiated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    expected_date: date | None = None


# ---------------------------------------------------------------------------
# 13. LinkedBank
# ---------------------------------------------------------------------------

class LinkedBank(BaseEntity):
    bank_name: str
    account_type: Literal["checking", "savings"]
    last_four: str
    status: Literal["verified", "pending"] = "verified"
    is_default: bool = False


# ---------------------------------------------------------------------------
# 14. RecurringExecution
# ---------------------------------------------------------------------------

class RecurringExecution(BaseModel):
    date: date
    amount: Decimal
    shares_bought: Decimal
    price: Decimal

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 15. RecurringInvestment
# ---------------------------------------------------------------------------

class RecurringInvestment(BaseEntity):
    symbol: str
    amount: Decimal
    frequency: Literal["daily", "weekly", "biweekly", "monthly"]
    next_execution_date: date
    status: Literal["active", "paused"] = "active"
    history: list[RecurringExecution] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 16. Transaction
# ---------------------------------------------------------------------------

class Transaction(BaseEntity):
    type: Literal[
        "buy", "sell", "dividend", "interest", "deposit", "withdrawal",
        "split", "merger", "fee", "referral_bonus", "option_exercise",
        "option_assignment", "option_expiration",
    ]
    symbol: str | None = None
    quantity: Decimal | None = None
    amount: Decimal
    description: str
    timestamp: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# 17. RealizedGainLoss
# ---------------------------------------------------------------------------

class RealizedGainLoss(BaseModel):
    symbol: str
    buy_date: date
    sell_date: date
    proceeds: Decimal
    cost_basis: Decimal
    gain_loss: Decimal
    wash_sale: bool = False
    holding_period: Literal["short", "long"]

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 18. TaxDocument
# ---------------------------------------------------------------------------

class TaxDocument(BaseEntity):
    type: Literal["1099_B", "1099_DIV", "1099_INT", "1099_CONSOLIDATED"]
    tax_year: int
    available_date: date
    realized_gains: list[RealizedGainLoss] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 19. PriceAlert
# ---------------------------------------------------------------------------

class PriceAlert(BaseEntity):
    symbol: str
    condition: Literal["above", "below"]
    target_price: Decimal
    status: Literal["active", "triggered"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    triggered_at: datetime | None = None


# ---------------------------------------------------------------------------
# 20. Notification
# ---------------------------------------------------------------------------

class Notification(BaseEntity):
    type: Literal[
        "order_fill", "price_alert", "dividend", "earnings",
        "transfer_complete", "security_alert", "recurring_investment",
        "tax_document", "margin_call", "corporate_action",
    ]
    title: str
    message: str
    timestamp: datetime = Field(default_factory=utc_now)
    is_read: bool = False
    action_url: str | None = None


# ---------------------------------------------------------------------------
# 21. EarningsEvent
# ---------------------------------------------------------------------------

class EarningsEvent(BaseModel):
    symbol: str
    date: date
    time: Literal["before_market", "after_market"]
    eps_estimate: Decimal | None = None
    eps_actual: Decimal | None = None
    revenue_estimate: Decimal | None = None
    revenue_actual: Decimal | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 22. DividendEntry
# ---------------------------------------------------------------------------

class DividendEntry(BaseModel):
    symbol: str
    ex_date: date
    pay_date: date
    amount_per_share: Decimal
    estimated_total: Decimal
    status: Literal["upcoming", "paid"]

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 23. AccountSettings
# ---------------------------------------------------------------------------

class AccountSettings(BaseEntity):
    display_theme: Literal["light", "dark"] = "light"
    default_order_type: Literal["market", "limit"] = "market"
    reinvest_dividends: bool = True
    extended_hours_enabled: bool = False
    biometric_login: bool = False
    two_factor_method: Literal["sms", "authenticator", "none"] = "none"
    notification_prefs: dict[str, bool] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 24. SecurityEntry
# ---------------------------------------------------------------------------

class SecurityEntry(BaseModel):
    event: Literal["login", "password_change", "2fa_change", "device_added"]
    device: str
    ip_address: str
    location: str
    timestamp: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 25. Referral
# ---------------------------------------------------------------------------

class Referral(BaseModel):
    referred_name: str
    status: Literal["pending", "completed"]
    reward_stock: str
    reward_value: Decimal
    date: date

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 26. RobinhoodState
# ---------------------------------------------------------------------------

class RobinhoodState(BaseEnvState):
    # Account info
    owner_name: str
    owner_email: str
    account_type: Literal["individual", "margin"] = "individual"
    cash_balance: Decimal = Decimal("0")
    buying_power: Decimal = Decimal("0")
    portfolio_value: Decimal = Decimal("0")
    instant_deposits_limit: Decimal = Decimal("1000")
    margin_maintenance: Decimal = Decimal("0")
    gold_subscription: bool = False
    day_trade_count: int = 0
    account_created_at: datetime = Field(default_factory=utc_now)

    # Collections
    positions: list[Position] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    options_positions: list[OptionsPosition] = Field(default_factory=list)
    options_orders: list[OptionsOrder] = Field(default_factory=list)
    stocks: list[Stock] = Field(default_factory=list)
    options_chains: dict[str, list[OptionsContract]] = Field(default_factory=dict)
    watchlists: list[Watchlist] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    transfers: list[Transfer] = Field(default_factory=list)
    linked_banks: list[LinkedBank] = Field(default_factory=list)
    recurring_investments: list[RecurringInvestment] = Field(default_factory=list)
    tax_documents: list[TaxDocument] = Field(default_factory=list)
    price_alerts: list[PriceAlert] = Field(default_factory=list)
    notifications: list[Notification] = Field(default_factory=list)
    earnings_events: list[EarningsEvent] = Field(default_factory=list)
    dividend_schedule: list[DividendEntry] = Field(default_factory=list)
    settings: AccountSettings
    security_log: list[SecurityEntry] = Field(default_factory=list)
    referral_history: list[Referral] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    # ---- Query methods ----

    def get_position(self, symbol: str) -> Position | None:
        return next((p for p in self.positions if p.symbol == symbol), None)

    def get_stock(self, symbol: str) -> Stock | None:
        return next((s for s in self.stocks if s.symbol == symbol), None)

    def get_order(self, order_id: str) -> Order | None:
        return next((o for o in self.orders if o.id == order_id), None)

    def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        return next((w for w in self.watchlists if w.id == watchlist_id), None)

    def get_bank(self, bank_id: str) -> LinkedBank | None:
        return next((b for b in self.linked_banks if b.id == bank_id), None)

    def default_bank(self) -> LinkedBank | None:
        return next((b for b in self.linked_banks if b.is_default), None)

    def pending_orders(self) -> list[Order]:
        return [o for o in self.orders if o.status == "pending"]

    def filled_orders(self) -> list[Order]:
        return [o for o in self.orders if o.status == "filled"]

    def unread_notifications(self) -> list[Notification]:
        return [n for n in self.notifications if not n.is_read]

    def search_stocks(self, query: str) -> list[Stock]:
        q = query.lower()
        return [
            s for s in self.stocks
            if q in s.symbol.lower() or q in s.name.lower()
        ]

    def list_transactions(
        self,
        *,
        type: str | None = None,
        symbol: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Transaction]:
        result = list(self.transactions)
        if type is not None:
            result = [t for t in result if t.type == type]
        if symbol is not None:
            result = [t for t in result if t.symbol == symbol]
        if from_date is not None:
            result = [t for t in result if t.timestamp >= from_date]
        if to_date is not None:
            result = [t for t in result if t.timestamp <= to_date]
        return result

    def session_summary(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "task_id": self.task_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "account_type": self.account_type,
            "cash_balance": str(self.cash_balance),
            "buying_power": str(self.buying_power),
            "portfolio_value": str(self.portfolio_value),
            "counts": {
                "positions": len(self.positions),
                "orders": len(self.orders),
                "stocks": len(self.stocks),
                "watchlists": len(self.watchlists),
                "transactions": len(self.transactions),
                "notifications": len(self.notifications),
                "unread_notifications": len(self.unread_notifications()),
                "price_alerts": len(self.price_alerts),
            },
        }

    # ---- Mutation methods ----

    def place_order(
        self,
        *,
        symbol: str,
        side: Literal["buy", "sell"],
        order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"] = "market",
        quantity: Decimal,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        trail_amount: Decimal | None = None,
        trail_pct: Decimal | None = None,
        time_in_force: Literal["gfd", "gtc", "ioc", "opg"] = "gfd",
        extended_hours: bool = False,
    ) -> Order:
        order_id = f"ord_{len(self.orders) + 1}"
        now = utc_now()

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            filled_quantity=Decimal("0"),
            limit_price=limit_price,
            stop_price=stop_price,
            trail_amount=trail_amount,
            trail_pct=trail_pct,
            time_in_force=time_in_force,
            status="pending",
            extended_hours=extended_hours,
            created_at=now,
        )

        # Auto-fill market orders
        if order_type == "market":
            stock = self.get_stock(symbol)
            if stock is None:
                raise ValueError(f"Unknown stock: {symbol}")
            price = stock.price
            total = price * quantity

            if side == "buy":
                if total > self.cash_balance:
                    raise ValueError("Insufficient funds")
                self.cash_balance -= total
                self.buying_power -= total

                # Create or update position
                pos = self.get_position(symbol)
                if pos is None:
                    pos = Position(
                        id=f"pos_{len(self.positions) + 1}",
                        symbol=symbol,
                        name=stock.name,
                        asset_type=stock.asset_type,
                        quantity=quantity,
                        avg_cost_basis=price,
                        current_price=price,
                        day_change_pct=stock.day_change_pct,
                        total_return=Decimal("0"),
                        total_return_pct=Decimal("0"),
                        lots=[TaxLot(shares=quantity, cost_per_share=price, acquired_date=now.date())],
                    )
                    self.positions.append(pos)
                else:
                    new_qty = pos.quantity + quantity
                    pos.avg_cost_basis = (
                        (pos.avg_cost_basis * pos.quantity + price * quantity) / new_qty
                    )
                    pos.quantity = new_qty
                    pos.current_price = price
                    pos.lots.append(TaxLot(shares=quantity, cost_per_share=price, acquired_date=now.date()))
            else:  # sell
                pos = self.get_position(symbol)
                if pos is None or pos.quantity < quantity:
                    raise ValueError("Insufficient shares")
                self.cash_balance += total
                self.buying_power += total
                pos.quantity -= quantity
                if pos.quantity == Decimal("0"):
                    self.positions = [p for p in self.positions if p.symbol != symbol]

            order.status = "filled"
            order.filled_quantity = quantity
            order.filled_at = now

            # Add transaction
            self.transactions.append(
                Transaction(
                    id=f"txn_{len(self.transactions) + 1}",
                    type=side,
                    symbol=symbol,
                    quantity=quantity,
                    amount=total,
                    description=f"Market {side} {quantity} shares of {symbol} @ ${price}",
                    timestamp=now,
                )
            )

            # Add notification
            self.notifications.append(
                Notification(
                    id=f"notif_{len(self.notifications) + 1}",
                    type="order_fill",
                    title=f"Order Filled: {symbol}",
                    message=f"Your market {side} order for {quantity} shares of {symbol} was filled at ${price}.",
                    timestamp=now,
                )
            )

        self.orders.append(order)
        self.touch()
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"Unknown order id: {order_id}")
        if order.status not in ("pending", "partially_filled"):
            raise ValueError(f"Cannot cancel order with status: {order.status}")
        order.status = "cancelled"
        order.cancelled_at = utc_now()
        self.touch()
        return order

    def place_options_order(
        self,
        *,
        strategy: str,
        legs: list[OptionsLeg],
    ) -> OptionsOrder:
        order = OptionsOrder(
            id=f"oord_{len(self.options_orders) + 1}",
            strategy=strategy,
            legs=legs,
            status="pending",
            created_at=utc_now(),
        )
        self.options_orders.append(order)
        self.touch()
        return order

    def create_watchlist(self, name: str, symbols: list[str] | None = None) -> Watchlist:
        wl = Watchlist(
            id=f"wl_{len(self.watchlists) + 1}",
            name=name,
            symbols=list(symbols or []),
            created_at=utc_now(),
        )
        self.watchlists.append(wl)
        self.touch()
        return wl

    def add_to_watchlist(self, watchlist_id: str, symbol: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        if symbol not in wl.symbols:
            wl.symbols.append(symbol)
        self.touch()
        return wl

    def remove_from_watchlist(self, watchlist_id: str, symbol: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        wl.symbols = [s for s in wl.symbols if s != symbol]
        self.touch()
        return wl

    def initiate_transfer(
        self,
        direction: Literal["deposit", "withdrawal"],
        amount: Decimal,
        bank_account_id: str,
    ) -> Transfer:
        bank = self.get_bank(bank_account_id)
        if bank is None:
            raise KeyError(f"Unknown bank account id: {bank_account_id}")

        now = utc_now()
        transfer = Transfer(
            id=f"xfer_{len(self.transfers) + 1}",
            direction=direction,
            amount=amount,
            status="pending",
            bank_account_id=bank_account_id,
            initiated_at=now,
        )

        if direction == "deposit":
            self.cash_balance += amount
            self.buying_power += amount
        else:  # withdrawal
            if amount > self.cash_balance:
                raise ValueError("Insufficient funds for withdrawal")
            self.cash_balance -= amount
            self.buying_power -= amount

        self.transactions.append(
            Transaction(
                id=f"txn_{len(self.transactions) + 1}",
                type=direction,
                symbol=None,
                quantity=None,
                amount=amount,
                description=f"{'Deposit from' if direction == 'deposit' else 'Withdrawal to'} {bank.bank_name} ****{bank.last_four}",
                timestamp=now,
            )
        )

        self.transfers.append(transfer)
        self.touch()
        return transfer

    def create_recurring_investment(
        self,
        symbol: str,
        amount: Decimal,
        frequency: Literal["daily", "weekly", "biweekly", "monthly"],
        next_execution_date: date,
    ) -> RecurringInvestment:
        ri = RecurringInvestment(
            id=f"ri_{len(self.recurring_investments) + 1}",
            symbol=symbol,
            amount=amount,
            frequency=frequency,
            next_execution_date=next_execution_date,
            status="active",
        )
        self.recurring_investments.append(ri)
        self.touch()
        return ri

    def update_recurring_investment(
        self,
        ri_id: str,
        *,
        amount: Decimal | None = None,
        frequency: str | None = None,
        status: str | None = None,
    ) -> RecurringInvestment:
        ri = next((r for r in self.recurring_investments if r.id == ri_id), None)
        if ri is None:
            raise KeyError(f"Unknown recurring investment id: {ri_id}")
        if amount is not None:
            ri.amount = amount
        if frequency is not None:
            ri.frequency = frequency  # type: ignore[assignment]
        if status is not None:
            ri.status = status  # type: ignore[assignment]
        self.touch()
        return ri

    def create_price_alert(
        self,
        symbol: str,
        condition: Literal["above", "below"],
        target_price: Decimal,
    ) -> PriceAlert:
        alert = PriceAlert(
            id=f"alert_{len(self.price_alerts) + 1}",
            symbol=symbol,
            condition=condition,
            target_price=target_price,
            status="active",
            created_at=utc_now(),
        )
        self.price_alerts.append(alert)
        self.touch()
        return alert

    def mark_notification_read(self, notification_id: str) -> Notification:
        notif = next((n for n in self.notifications if n.id == notification_id), None)
        if notif is None:
            raise KeyError(f"Unknown notification id: {notification_id}")
        notif.is_read = True
        self.touch()
        return notif

    def mark_all_notifications_read(self) -> int:
        count = 0
        for n in self.notifications:
            if not n.is_read:
                n.is_read = True
                count += 1
        if count > 0:
            self.touch()
        return count

    def update_settings(self, **kwargs: Any) -> AccountSettings:
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
            else:
                raise ValueError(f"Unknown setting: {key}")
        self.touch()
        return self.settings

    def rename_watchlist(self, watchlist_id: str, name: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        wl.name = name
        self.touch()
        return wl

    def delete_watchlist(self, watchlist_id: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        self.watchlists = [w for w in self.watchlists if w.id != watchlist_id]
        self.touch()
        return wl

    def link_bank(
        self,
        bank_name: str,
        account_type: Literal["checking", "savings"],
        last_four: str,
    ) -> LinkedBank:
        bank = LinkedBank(
            id=f"bank_{len(self.linked_banks) + 1}",
            bank_name=bank_name,
            account_type=account_type,
            last_four=last_four,
            status="verified",
            is_default=len(self.linked_banks) == 0,
        )
        self.linked_banks.append(bank)
        self.touch()
        return bank

    def unlink_bank(self, bank_id: str) -> LinkedBank:
        bank = self.get_bank(bank_id)
        if bank is None:
            raise KeyError(f"Unknown bank account id: {bank_id}")
        self.linked_banks = [b for b in self.linked_banks if b.id != bank_id]
        self.touch()
        return bank

    def delete_recurring_investment(self, ri_id: str) -> RecurringInvestment:
        ri = next((r for r in self.recurring_investments if r.id == ri_id), None)
        if ri is None:
            raise KeyError(f"Unknown recurring investment id: {ri_id}")
        self.recurring_investments = [r for r in self.recurring_investments if r.id != ri_id]
        self.touch()
        return ri

    def delete_price_alert(self, alert_id: str) -> PriceAlert:
        alert = next((a for a in self.price_alerts if a.id == alert_id), None)
        if alert is None:
            raise KeyError(f"Unknown price alert id: {alert_id}")
        self.price_alerts = [a for a in self.price_alerts if a.id != alert_id]
        self.touch()
        return alert

    def update_2fa(self, method: Literal["sms", "authenticator", "none"]) -> AccountSettings:
        self.settings.two_factor_method = method
        self.security_log.append(
            SecurityEntry(
                event="2fa_change",
                device="web",
                ip_address="0.0.0.0",
                location="Unknown",
                timestamp=utc_now(),
            )
        )
        self.touch()
        return self.settings
