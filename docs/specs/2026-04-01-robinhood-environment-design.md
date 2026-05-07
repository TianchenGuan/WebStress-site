# Robinhood Environment Design Spec

**Date**: 2026-04-01
**Status**: Approved
**Scope**: New WebStress environment simulating Robinhood brokerage — full data model, 50 tasks across 5 difficulty levels, 16-page React frontend, 45 API endpoints.

---

## 1. Overview

A faithful Robinhood web clone as a new WebStress environment (`env_id: robinhood`). The environment simulates a full brokerage platform: portfolio management, stock/options trading, order management, transfers, tax documents, recurring investments, watchlists, notifications, and account settings.

**Goals:**
- 50 high-quality tasks across 5 difficulty levels (easy/medium/hard/expert/frontier, 10 each)
- Clean, reusable architecture following established Gmail environment patterns
- Automatic demo site integration via the AdapterProvider pattern
- Faithful Robinhood web desktop visual design (light theme, top nav, right sidebar watchlists)

**Non-goals:**
- Degradation variants (deferred to a follow-up)
- Crypto wallet / IPO access / news feed (out of scope)
- Real market data or live price feeds

---

## 2. Visual Design

Faithful clone of Robinhood's desktop web interface:

- **Light theme**: white background (#fff), minimal borders (#e8e8e8)
- **Top navigation bar**: feather logo, search bar, horizontal nav links (Investing, Notifications, Account)
- **Right sidebar**: watchlists with mini sparkline SVG charts
- **Portfolio as home page**: total value, interactive line chart, buying power, positions list
- **Colors**: green #00C805 for gains, red #FF5000 for losses
- **Typography**: system font stack (-apple-system, BlinkMacSystemFont, Segoe UI, Roboto)
- **Position rows**: symbol, shares count, sparkline, current price, % change

---

## 3. Data Model

All entities are Pydantic models. `RobinhoodState` extends `BaseEnvState`.

### 3.1 Core Account

```python
class RobinhoodState(BaseEnvState):
    env_id: str = "robinhood"
    owner_name: str
    owner_email: str
    account_type: Literal["individual", "margin"]
    cash_balance: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    gold_subscription: bool
    instant_deposits_limit: Decimal
    day_trade_count: int
    margin_maintenance: Decimal
    account_created_at: datetime
```

### 3.2 Positions

```python
class TaxLot(BaseModel):
    shares: Decimal
    cost_per_share: Decimal
    acquired_date: date

class Position(BaseEntity):
    symbol: str
    name: str
    asset_type: Literal["stock", "etf", "crypto", "option"]
    quantity: Decimal           # supports fractional shares
    avg_cost_basis: Decimal
    current_price: Decimal
    day_change_pct: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    lots: list[TaxLot]
```

### 3.3 Orders

```python
class Order(BaseEntity):
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"]
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    trail_amount: Decimal | None
    trail_pct: Decimal | None
    time_in_force: Literal["gfd", "gtc", "ioc", "opg"]
    status: Literal["pending", "partially_filled", "filled", "cancelled", "rejected"]
    extended_hours: bool
    created_at: datetime
    filled_at: datetime | None
    cancelled_at: datetime | None
```

### 3.4 Stocks (Universe)

```python
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
    market_cap: Decimal
    pe_ratio: Decimal | None
    eps: Decimal | None
    dividend_yield: Decimal | None
    fifty_two_week_high: Decimal
    fifty_two_week_low: Decimal
    sector: str
    industry: str
    about: str
    historical_prices: list[HistoricalPrice]  # {date, close}
```

### 3.5 Options

```python
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
    greeks: Greeks  # {delta, gamma, theta, vega}

class OptionsPosition(BaseEntity):
    contract_id: str
    underlying_symbol: str
    option_type: Literal["call", "put"]
    strike_price: Decimal
    expiration_date: date
    quantity: int
    avg_cost: Decimal
    current_premium: Decimal
    greeks: Greeks
    status: Literal["open", "closed", "exercised", "expired"]

class OptionsLeg(BaseModel):
    side: Literal["buy", "sell"]
    option_type: Literal["call", "put"]
    strike: Decimal
    expiration: date
    quantity: int
    premium: Decimal

class OptionsOrder(BaseEntity):
    strategy: Literal["single", "vertical", "iron_condor", "straddle",
                       "strangle", "covered_call", "protective_put"]
    legs: list[OptionsLeg]
    status: Literal["pending", "filled", "cancelled", "rejected"]
    created_at: datetime
    filled_at: datetime | None
```

### 3.6 Watchlists

```python
class Watchlist(BaseEntity):
    name: str
    symbols: list[str]
    created_at: datetime
```

### 3.7 Money Movement

```python
class Transfer(BaseEntity):
    direction: Literal["deposit", "withdrawal"]
    amount: Decimal
    status: Literal["pending", "completed", "failed", "reversed"]
    bank_account_id: str
    initiated_at: datetime
    completed_at: datetime | None
    expected_date: date

class LinkedBank(BaseEntity):
    bank_name: str
    account_type: Literal["checking", "savings"]
    last_four: str
    status: Literal["verified", "pending"]
    is_default: bool

class RecurringInvestment(BaseEntity):
    symbol: str
    amount: Decimal
    frequency: Literal["daily", "weekly", "biweekly", "monthly"]
    next_execution_date: date
    status: Literal["active", "paused"]
    history: list[RecurringExecution]  # {date, amount, shares_bought, price}
```

### 3.8 Transaction Ledger

```python
class Transaction(BaseEntity):
    type: Literal["buy", "sell", "dividend", "interest", "deposit", "withdrawal",
                  "split", "merger", "fee", "referral_bonus",
                  "option_exercise", "option_assignment", "option_expiration"]
    symbol: str | None
    quantity: Decimal | None
    amount: Decimal
    description: str
    timestamp: datetime
```

### 3.9 Tax

```python
class RealizedGainLoss(BaseModel):
    symbol: str
    buy_date: date
    sell_date: date
    proceeds: Decimal
    cost_basis: Decimal
    gain_loss: Decimal
    wash_sale: bool
    holding_period: Literal["short", "long"]

class TaxDocument(BaseEntity):
    type: Literal["1099_B", "1099_DIV", "1099_INT", "1099_CONSOLIDATED"]
    tax_year: int
    available_date: date
    realized_gains: list[RealizedGainLoss]
```

### 3.10 Alerts & Notifications

```python
class PriceAlert(BaseEntity):
    symbol: str
    condition: Literal["above", "below"]
    target_price: Decimal
    status: Literal["active", "triggered"]
    created_at: datetime
    triggered_at: datetime | None

class Notification(BaseEntity):
    type: Literal["order_fill", "price_alert", "dividend", "earnings",
                  "transfer_complete", "security_alert", "recurring_investment",
                  "tax_document", "margin_call", "corporate_action"]
    title: str
    message: str
    timestamp: datetime
    is_read: bool
    action_url: str | None
```

### 3.11 Market Events

```python
class EarningsEvent(BaseModel):
    symbol: str
    date: date
    time: Literal["before_market", "after_market"]
    eps_estimate: Decimal | None
    eps_actual: Decimal | None
    revenue_estimate: Decimal | None
    revenue_actual: Decimal | None

class DividendEntry(BaseModel):
    symbol: str
    ex_date: date
    pay_date: date
    amount_per_share: Decimal
    estimated_total: Decimal
    status: Literal["upcoming", "paid"]
```

### 3.12 Account Settings & Security

```python
class AccountSettings(BaseModel):
    display_theme: Literal["light", "dark"]
    default_order_type: Literal["market", "limit"]
    reinvest_dividends: bool
    extended_hours_enabled: bool
    biometric_login: bool
    two_factor_method: Literal["sms", "authenticator", "none"]
    notification_prefs: dict[str, bool]

class SecurityEntry(BaseModel):
    event: Literal["login", "password_change", "2fa_change", "device_added"]
    device: str
    ip_address: str
    location: str
    timestamp: datetime

class Referral(BaseModel):
    referred_name: str
    status: Literal["pending", "completed"]
    reward_stock: str
    reward_value: Decimal
    date: date
```

---

## 4. API Routes

All routes under `/api/env/robinhood/`. Session ID passed via query param or request body (same as Gmail).

### Session Management
| Method | Path | Description |
|--------|------|-------------|
| POST | `/session` | Create session (task_id, seed) |
| GET | `/session/{id}` | Session metadata |
| DELETE | `/session/{id}` | Destroy session |
| POST | `/evaluate` | Run eval checks |

### Account
| Method | Path | Description |
|--------|------|-------------|
| GET | `/account` | Account summary (balances, tier, PDT count) |
| GET | `/account/portfolio` | Portfolio value + day change + chart data |

### Positions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/positions` | All positions with current prices |
| GET | `/positions/{symbol}` | Single position detail with lots |

### Stocks
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stocks/{symbol}` | Stock detail (price, stats, about) |
| GET | `/stocks/{symbol}/chart` | Historical prices by period |
| GET | `/stocks/{symbol}/options` | Options chain |
| GET | `/stocks/{symbol}/earnings` | Earnings history + upcoming |
| GET | `/stocks/{symbol}/dividends` | Dividend history |
| GET | `/search` | Search stocks by name/symbol (`?q=`) |

### Orders
| Method | Path | Description |
|--------|------|-------------|
| POST | `/orders` | Place order |
| GET | `/orders` | List orders (`?status=`) |
| GET | `/orders/{id}` | Order detail |
| POST | `/orders/{id}/cancel` | Cancel pending order |

### Options
| Method | Path | Description |
|--------|------|-------------|
| POST | `/options/orders` | Place options order |
| GET | `/options/orders` | List options orders |
| GET | `/options/orders/{id}` | Options order detail |
| GET | `/options/positions` | Open options positions |

### Watchlists
| Method | Path | Description |
|--------|------|-------------|
| GET | `/watchlists` | All watchlists |
| POST | `/watchlists` | Create watchlist |
| PUT | `/watchlists/{id}` | Rename / reorder |
| DELETE | `/watchlists/{id}` | Delete watchlist |
| POST | `/watchlists/{id}/symbols` | Add symbol |
| DELETE | `/watchlists/{id}/symbols/{s}` | Remove symbol |

### Transfers
| Method | Path | Description |
|--------|------|-------------|
| GET | `/transfers` | List transfers |
| POST | `/transfers` | Initiate deposit/withdrawal |
| GET | `/banks` | Linked bank accounts |
| POST | `/banks` | Link new bank |
| DELETE | `/banks/{id}` | Unlink bank |

### Recurring Investments
| Method | Path | Description |
|--------|------|-------------|
| GET | `/recurring` | List recurring investments |
| POST | `/recurring` | Create recurring investment |
| PUT | `/recurring/{id}` | Update (amount, frequency, pause/resume) |
| DELETE | `/recurring/{id}` | Cancel recurring investment |

### Transactions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/transactions` | Full ledger (`?type=`, `?symbol=`, `?from=`, `?to=`) |

### Tax Center
| Method | Path | Description |
|--------|------|-------------|
| GET | `/tax/documents` | List documents by year |
| GET | `/tax/documents/{id}` | Document detail |
| GET | `/tax/gains` | Realized gains/losses (`?year=`, `?symbol=`) |

### Notifications
| Method | Path | Description |
|--------|------|-------------|
| GET | `/notifications` | List all (`?type=`, `?unread=`) |
| POST | `/notifications/{id}/read` | Mark as read |
| POST | `/notifications/read-all` | Mark all as read |

### Price Alerts
| Method | Path | Description |
|--------|------|-------------|
| GET | `/alerts` | List price alerts |
| POST | `/alerts` | Create alert |
| DELETE | `/alerts/{id}` | Delete alert |

### Dividends
| Method | Path | Description |
|--------|------|-------------|
| GET | `/dividends` | Upcoming + history |

### Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings` | All settings |
| PUT | `/settings` | Update settings |

### Security
| Method | Path | Description |
|--------|------|-------------|
| GET | `/security/log` | Login history |
| PUT | `/security/2fa` | Update 2FA method |

### Referrals
| Method | Path | Description |
|--------|------|-------------|
| GET | `/referrals` | Referral history |

**Total: ~45 endpoints**

---

## 5. Pages & Navigation

16 pages following real Robinhood desktop web layout.

### Top Navigation Bar
- Feather logo (links to home/portfolio)
- Search bar (centered, routes to `/search`)
- Nav links: Investing, Notifications, Account

### Page Structure

| Page | Route | Description |
|------|-------|-------------|
| Portfolio (Home) | `/` | Total value, line chart with time range (1D/1W/1M/3M/1Y/ALL), buying power, positions list with sparklines |
| Stock Detail | `/stocks/:symbol` | Price chart, key stats (market cap, P/E, EPS, dividend yield, 52w range), about section, earnings, buy/sell button |
| Options Chain | `/stocks/:symbol/options` | Expiration date picker, calls/puts table with greeks, strike selection |
| Buy/Sell | `/stocks/:symbol/trade` | Order type selector, quantity/dollar input, limit/stop price fields, time-in-force, review screen |
| Options Order | `/stocks/:symbol/options/trade` | Strategy selector, leg builder, premium calculator, review |
| Search/Explore | `/search` | Search input, trending stocks, sector category chips |
| Watchlists | `/lists` | All watchlists overview, create new |
| Watchlist Detail | `/lists/:id` | Symbols with prices and sparklines, add/remove |
| Order History | `/orders` | Tabs: pending / filled / cancelled, filters |
| Transaction History | `/history` | Full ledger, filter by type/symbol/date |
| Recurring Investments | `/recurring` | Active/paused list, create new, execution history |
| Transfers | `/transfers` | Deposit/withdraw forms, pending transfers, linked banks |
| Tax Center | `/tax` | Documents by year, realized gains/losses summary |
| Dividends | `/dividends` | Upcoming schedule, payment history |
| Notifications | `/notifications` | Grouped by type, read/unread indicators |
| Account/Settings | `/account` | Settings, security log, 2FA, linked banks, referrals |

### Right Sidebar (persistent on Portfolio + Stock Detail pages)
- **Lists** header with + button
- Collapsible watchlists with symbol → sparkline → price → % change rows

---

## 6. Seed Builders

~20 builder functions registered via `@_register("builder_name")`. Each receives `SeedContext` and `params`, returns output dict.

| Builder | Purpose | Params |
|---------|---------|--------|
| `portfolio_basic` | 3-5 positions, simple single-lot cost basis | `{stocks: [symbols], quantities: [...], cost_bases: [...]}` |
| `portfolio_diverse` | 8-15 positions across sectors, multi-lot | `{count, sectors, include_etfs, include_losers}` |
| `pending_orders` | N pending orders of various types | `{count, order_types, symbols}` |
| `filled_orders` | Historical filled orders | `{count, age_range_days, symbols}` |
| `watchlist` | Named watchlist with symbols | `{name, symbols}` |
| `stock_universe` | Populates stock universe with realistic data | `{count, must_include: [symbols], sectors}` |
| `options_chain` | Full options chain for a symbol | `{symbol, expirations_count, strikes_per_expiration}` |
| `options_positions` | Open options positions | `{count, strategies, symbols}` |
| `recurring_investments` | Active recurring investments with history | `{count, symbols, frequencies}` |
| `transfers_history` | Deposit/withdrawal history | `{count, age_range_days, include_pending}` |
| `linked_banks` | Bank accounts | `{banks: [{name, type, last_four}]}` |
| `transaction_ledger` | Full buy/sell/dividend ledger | `{months, symbols, include_dividends}` |
| `tax_documents` | 1099s with realized gains | `{year, include_wash_sales, gains_count}` |
| `price_alerts` | Active/triggered alerts | `{count, include_triggered}` |
| `notifications` | Mixed notification types | `{count, types, unread_ratio}` |
| `earnings_calendar` | Upcoming earnings for symbols | `{symbols, days_ahead}` |
| `dividend_schedule` | Upcoming/past dividends | `{symbols, include_history}` |
| `security_log` | Login history | `{count, include_suspicious}` |
| `margin_account` | Margin state with maintenance | `{margin_used, maintenance_pct}` |
| `complex_options_book` | Multi-leg positions near expiration | `{positions_count, days_to_expiry}` |

### Builder Execution Flow

Same pattern as Gmail:
1. `RobinhoodSeedRunner.run(task, seed, fake, rng)` creates base skeleton
2. Resolve actors (not heavily used — Robinhood is single-user, but "stocks" serve a similar named-entity role)
3. Execute builder steps from task YAML in order
4. Add generic distractors (filler positions, extra notifications, noise orders)
5. Resolve target templates
6. Return `(base_dict, targets)`

---

## 7. Tasks (50 total)

### 7.1 Easy (10 tasks)

#### `rh_buy_market_order`
- **Instruction**: Buy 3 shares of {target.symbol} at market price.
- **Difficulty**: easy | **Steps**: 5 | **Time**: 90s
- **Primitives**: grounding, planning
- **Seed**: `stock_universe` (must include target), `portfolio_basic`, `linked_banks`
- **Eval**: `any(o.symbol == '{target.symbol}' and o.side == 'buy' and o.order_type == 'market' and o.quantity == 3 and o.status == 'filled' for o in state.orders)`

#### `rh_sell_shares`
- **Instruction**: Sell all of your {target.symbol} shares.
- **Difficulty**: easy | **Steps**: 5 | **Time**: 90s
- **Primitives**: grounding, planning
- **Seed**: `portfolio_basic` (must include target with known quantity), `stock_universe`
- **Eval**: `any(o.symbol == '{target.symbol}' and o.side == 'sell' and o.quantity == {target.quantity} and o.status == 'filled' for o in state.orders)`

#### `rh_add_to_watchlist`
- **Instruction**: Add {target.symbol} to your "{target.watchlist_name}" watchlist.
- **Difficulty**: easy | **Steps**: 3 | **Time**: 60s
- **Primitives**: grounding, exploration
- **Seed**: `watchlist` (named list without target symbol), `stock_universe`
- **Eval**: `any('{target.symbol}' in w.symbols and w.name == '{target.watchlist_name}' for w in state.watchlists)`

#### `rh_cancel_pending_order`
- **Instruction**: Cancel the pending limit order for {target.symbol}.
- **Difficulty**: easy | **Steps**: 4 | **Time**: 90s
- **Primitives**: grounding, state_tracking
- **Seed**: `pending_orders` (includes one for target symbol), `stock_universe`
- **Eval**: `any(o.id == '{target.order_id}' and o.status == 'cancelled' for o in state.orders)`

#### `rh_create_watchlist`
- **Instruction**: Create a new watchlist called "{target.list_name}" and add {target.symbols_csv} to it.
- **Difficulty**: easy | **Steps**: 5 | **Time**: 90s
- **Primitives**: planning, exploration
- **Seed**: `stock_universe`, `watchlist` (existing lists as context)
- **Eval**: `any(w.name == '{target.list_name}' and all(s in w.symbols for s in {target.symbols_list}) for w in state.watchlists)`

#### `rh_set_price_alert`
- **Instruction**: Set a price alert for {target.symbol} when it goes above ${target.price}.
- **Difficulty**: easy | **Steps**: 4 | **Time**: 60s
- **Primitives**: grounding, planning
- **Seed**: `stock_universe`, `price_alerts` (some existing)
- **Eval**: `any(a.symbol == '{target.symbol}' and a.condition == 'above' and a.target_price == {target.price} for a in state.price_alerts)`

#### `rh_mark_notifications_read`
- **Instruction**: Mark all unread notifications as read.
- **Difficulty**: easy | **Steps**: 2 | **Time**: 60s
- **Primitives**: grounding
- **Seed**: `notifications` (mix of read/unread)
- **Eval**: `all(n.is_read for n in state.notifications)`

#### `rh_check_buying_power`
- **Instruction**: What is your current buying power? Report the amount.
- **Difficulty**: easy | **Steps**: 2 | **Time**: 60s
- **Primitives**: grounding
- **Seed**: `portfolio_basic`, `linked_banks`
- **Eval**: Check `send_msg_to_user` contains `'{target.buying_power}'`

#### `rh_enable_extended_hours`
- **Instruction**: Enable extended hours trading in your account settings.
- **Difficulty**: easy | **Steps**: 3 | **Time**: 60s
- **Primitives**: exploration, planning
- **Seed**: `AccountSettings` with extended_hours_enabled=False
- **Eval**: `state.settings.extended_hours_enabled == True`

#### `rh_deposit_funds`
- **Instruction**: Deposit ${target.amount} from your default bank account.
- **Difficulty**: easy | **Steps**: 4 | **Time**: 90s
- **Primitives**: grounding, planning
- **Seed**: `linked_banks` (one default)
- **Eval**: `any(t.direction == 'deposit' and t.amount == {target.amount} and t.status in ('pending', 'completed') for t in state.transfers)`

### 7.2 Medium (10 tasks)

#### `rh_limit_order_with_check`
- **Instruction**: Check {target.symbol}'s current price, then place a limit buy order for 10 shares at 5% below current price, good-till-cancelled.
- **Primitives**: grounding, planning, state_tracking
- **Seed**: `stock_universe`, `portfolio_basic`, `linked_banks`
- **Eval**: Limit order exists with price within 1% of (current_price * 0.95), quantity=10, time_in_force='gtc'

#### `rh_deposit_then_buy`
- **Instruction**: Deposit ${target.deposit_amount} from {target.bank_name} checking, then buy ${target.buy_amount} worth of {target.symbol} at market.
- **Primitives**: planning, state_tracking
- **Seed**: `linked_banks`, `stock_universe`
- **Eval**: Transfer exists for deposit amount AND order exists for correct dollar amount of symbol

#### `rh_compare_dividend_yields`
- **Instruction**: Compare the dividend yields of {target.symbols_csv}. Add the one with the highest yield to your "{target.list_name}" watchlist.
- **Primitives**: grounding, state_tracking, exploration
- **Seed**: `stock_universe` (3 stocks with different yields), `watchlist`
- **Eval**: Highest-yielding symbol is in the target watchlist

#### `rh_setup_recurring_investment`
- **Instruction**: Set up a {target.frequency} ${target.amount} recurring investment into {target.symbol} starting {target.start_date}.
- **Primitives**: planning, exploration
- **Seed**: `stock_universe`, `linked_banks`
- **Eval**: RecurringInvestment exists with matching symbol, amount, frequency

#### `rh_review_and_cancel_orders`
- **Instruction**: Find all pending limit buy orders with prices more than 10% below current market price and cancel them.
- **Primitives**: state_tracking, grounding, planning
- **Seed**: `pending_orders` (mix of close-to-market and far-below), `stock_universe`
- **Eval**: All matching orders cancelled, non-matching orders untouched

#### `rh_transfer_and_withdraw`
- **Instruction**: Check your cash balance, then withdraw half of it to your {target.bank_name} savings account.
- **Primitives**: state_tracking, planning
- **Seed**: `linked_banks` (includes savings), `portfolio_basic`
- **Eval**: Withdrawal exists for exactly half of cash_balance to correct bank

#### `rh_find_earnings_and_alert`
- **Instruction**: Find which stocks in your portfolio have earnings in the next 7 days. Create a price alert for each, set 5% below their current price.
- **Primitives**: exploration, state_tracking, planning
- **Seed**: `portfolio_diverse`, `earnings_calendar`, `stock_universe`
- **Eval**: Price alert exists for each portfolio stock with upcoming earnings, target_price = 0.95 * current_price

#### `rh_sell_loser_buy_winner`
- **Instruction**: Find the worst-performing stock in your portfolio by total return %. Sell all of it, then buy more of your best-performing stock with the proceeds.
- **Primitives**: state_tracking, planning, grounding
- **Seed**: `portfolio_diverse` (clear worst and best), `stock_universe`
- **Eval**: Sell order for worst performer's full quantity AND buy order for best performer

#### `rh_options_buy_call`
- **Instruction**: Buy 1 call option on {target.symbol} with the nearest expiration, at the strike price closest to current price.
- **Primitives**: grounding, exploration, planning
- **Seed**: `stock_universe`, `options_chain` (for target symbol)
- **Eval**: Options order exists for 1 call, correct strike (ATM), correct expiration

#### `rh_security_audit`
- **Instruction**: Check your security log for any logins from outside the United States. If found, enable two-factor authentication via authenticator app.
- **Primitives**: exploration, state_tracking, planning
- **Seed**: `security_log` (includes foreign login), `AccountSettings` (2fa=none)
- **Eval**: `state.settings.two_factor_method == 'authenticator'`

### 7.3 Hard (10 tasks)

#### `rh_portfolio_rebalance`
- **Instruction**: Rebalance your portfolio to: {target.allocation_description}. Calculate the trades needed and execute them.
- **Primitives**: state_tracking, planning, grounding
- **Seed**: `portfolio_diverse` (off-target allocation), `stock_universe`
- **Eval**: Each position's % of portfolio within 2% of target allocation

#### `rh_covered_call_strategy`
- **Instruction**: You own {target.shares} shares of {target.symbol}. Sell a covered call with expiration ~30 days out, strike 10% above current price. Report the premium collected.
- **Primitives**: state_tracking, exploration, planning, grounding
- **Seed**: `portfolio_basic` (100+ shares of target), `options_chain`
- **Eval**: Options order for covered call with correct strike range, `send_msg_to_user` contains premium amount

#### `rh_dividend_income_report`
- **Instruction**: Calculate your total expected annual dividend income. Find the stock contributing least and replace it with the highest-yielding stock from your "{target.watchlist}" watchlist.
- **Primitives**: state_tracking, planning, exploration
- **Seed**: `portfolio_diverse`, `dividend_schedule`, `watchlist` (with high-yield stocks), `stock_universe`
- **Eval**: Sell order for lowest-dividend stock AND buy order for highest-yield from watchlist

#### `rh_wash_sale_avoidance`
- **Instruction**: Tax-loss harvest: sell positions with unrealized losses, but skip any where you bought the same stock in the last 30 days (wash sale risk).
- **Primitives**: state_tracking, planning, backtracking, verification
- **Seed**: `portfolio_diverse` (some losers), `transaction_ledger` (recent buys for some losers), `stock_universe`
- **Eval**: Sell orders exist for loss positions without recent buys, no sell orders for wash-sale-risk positions

#### `rh_cost_basis_reconciliation`
- **Instruction**: Compare {target.symbol}'s lot-level cost basis against your transaction history. Identify and report any discrepancy.
- **Primitives**: state_tracking, verification, grounding
- **Seed**: `portfolio_basic` (with lots), `transaction_ledger` (with deliberate small discrepancy)
- **Eval**: `send_msg_to_user` contains the discrepancy amount

#### `rh_options_chain_analysis`
- **Instruction**: For {target.symbol}, find the put option with the highest open interest expiring within 2 weeks. Report its strike, premium, and implied volatility.
- **Primitives**: exploration, state_tracking, grounding
- **Seed**: `options_chain` (multiple expirations), `stock_universe`
- **Eval**: `send_msg_to_user` contains correct strike, premium, and IV values

#### `rh_consolidate_recurring`
- **Instruction**: Find recurring investments for the same stock with different amounts/frequencies. Consolidate each into a single monthly investment with the combined amount.
- **Primitives**: state_tracking, planning, exploration
- **Seed**: `recurring_investments` (duplicates for some symbols)
- **Eval**: No duplicate symbols in recurring, consolidated amounts correct

#### `rh_notification_triage`
- **Instruction**: Process unread order fill notifications. For each, verify the fill price was within 2% of the limit price. Report any discrepancy.
- **Primitives**: state_tracking, verification, grounding
- **Seed**: `notifications` (order_fill type), `filled_orders` (some with price slippage), `stock_universe`
- **Eval**: All order_fill notifications marked read, `send_msg_to_user` contains discrepancies

#### `rh_sector_concentration`
- **Instruction**: Calculate your Technology sector exposure. If it exceeds 50%, sell enough of the most overweight tech stock to bring it to 50%, then buy {target.etf} with the proceeds.
- **Primitives**: state_tracking, planning, grounding
- **Seed**: `portfolio_diverse` (tech-heavy >50%), `stock_universe`
- **Eval**: Tech sector % of portfolio within 2% of 50%, buy order for ETF exists

#### `rh_transfer_history_audit`
- **Instruction**: Review all transfers from the past 6 months. Calculate total deposited vs withdrawn. Verify consistency with your current cash balance considering all trading activity. Report any discrepancy.
- **Primitives**: state_tracking, verification, planning
- **Seed**: `transfers_history`, `transaction_ledger`, `portfolio_diverse`
- **Eval**: `send_msg_to_user` contains correct deposit total, withdrawal total, and discrepancy (or confirms match)

### 7.4 Expert (10 tasks)

#### `rh_multi_leg_options`
- **Instruction**: Execute an iron condor on {target.symbol}: sell call and put at strikes 5% above/below current price, buy protective legs 2% further out, all expiring in ~45 days. Calculate and report max profit and max loss.
- **Primitives**: planning, state_tracking, exploration, grounding
- **Seed**: `options_chain` (wide strike range, 45-day expiration), `stock_universe`
- **Eval**: Options order with strategy='iron_condor', 4 legs with correct strikes, `send_msg_to_user` contains max profit/loss

#### `rh_tax_optimization`
- **Instruction**: You have ${target.short_term_gains} in short-term gains this year. Find positions with unrealized losses (avoiding wash sales from purchases in the last 30 days) and sell enough to offset those gains. Report final tax impact.
- **Primitives**: state_tracking, planning, backtracking, verification
- **Seed**: `portfolio_diverse` (positions with losses), `tax_documents`, `transaction_ledger`
- **Eval**: Sell orders for loss positions totaling >= target gains, no wash sale violations

#### `rh_portfolio_risk_assessment`
- **Instruction**: Analyze portfolio risk: (1) % in each sector, (2) any single stock >25% of total, (3) options expiring within 5 days, (4) margin utilization. Report all risk flags.
- **Primitives**: state_tracking, exploration, verification, planning
- **Seed**: `portfolio_diverse`, `options_positions`, `margin_account`, `stock_universe`
- **Eval**: `send_msg_to_user` contains all risk flags (verified against state)

#### `rh_earnings_play_setup`
- **Instruction**: {target.symbol} reports earnings tomorrow after close. Set up protection: (1) stop-loss at 8% below current, (2) price alert at 5% above, (3) check buying power for doubling position, (4) report exposure.
- **Primitives**: planning, state_tracking, exploration, grounding
- **Seed**: `portfolio_basic` (holding target), `earnings_calendar`, `stock_universe`
- **Eval**: Stop order exists at ~0.92*price, alert at ~1.05*price, `send_msg_to_user` contains exposure + buying power assessment

#### `rh_dividend_reinvestment_analysis`
- **Instruction**: Calculate yield-on-cost for each stock (dividends / your cost basis). For any with yield-on-cost <1% that have reinvestment enabled, disable reinvestment. Set up a recurring investment in the highest yield-on-cost stock with the redirected amount.
- **Primitives**: state_tracking, planning, exploration, verification
- **Seed**: `portfolio_diverse`, `dividend_schedule`, `AccountSettings`
- **Eval**: Reinvestment disabled for low-YOC stocks, new recurring investment for highest-YOC stock

#### `rh_margin_call_resolution`
- **Instruction**: Your account has a margin maintenance warning. Calculate the shortfall. Sell the position with smallest total-return impact to cover it, then deposit $500 as buffer.
- **Primitives**: state_tracking, planning, grounding, backtracking
- **Seed**: `margin_account` (near/at maintenance), `portfolio_diverse`, `linked_banks`
- **Eval**: Sell order for correct stock, amount covers shortfall, deposit of $500

#### `rh_watchlist_screening`
- **Instruction**: Screen your "{target.watchlist}" watchlist. Keep only stocks with P/E < 25, dividend yield > 2%, and price within 10% of 52-week high. Remove the rest. For stocks that pass all 3, place limit buys for $500 worth at 3% below current price.
- **Primitives**: state_tracking, exploration, planning, grounding
- **Seed**: `watchlist` (8-10 stocks, some pass, some fail), `stock_universe`
- **Eval**: Failing stocks removed from watchlist, limit orders for passing stocks at correct prices

#### `rh_recurring_optimization`
- **Instruction**: Analyze active recurring investments. Pause any where average purchase price is >5% above current price. Also pause any with earnings in next 3 days. Report changes.
- **Primitives**: state_tracking, planning, verification, backtracking
- **Seed**: `recurring_investments` (with history), `earnings_calendar`, `stock_universe`
- **Eval**: Correct recurring investments paused, others untouched

#### `rh_cross_reference_1099`
- **Instruction**: Cross-reference your 1099-B against transaction history. Find any sale where reported cost basis differs from transaction records. Report each discrepancy.
- **Primitives**: state_tracking, verification, grounding, exploration
- **Seed**: `tax_documents` (with deliberate discrepancies), `transaction_ledger`
- **Eval**: `send_msg_to_user` contains all discrepancies with correct figures

#### `rh_options_roll_strategy`
- **Instruction**: You have a covered call on {target.symbol} expiring this week that's in-the-money. Roll it: buy back the current call, sell a new call at next monthly expiration with strike 5% above current price. Report net credit/debit.
- **Primitives**: state_tracking, planning, grounding, exploration
- **Seed**: `options_positions` (ITM covered call), `options_chain`, `stock_universe`
- **Eval**: Buy-to-close order for old call, sell-to-open for new call, `send_msg_to_user` contains net credit/debit

### 7.5 Frontier (10 tasks)

#### `rh_full_portfolio_rebalance_with_tax`
- **Instruction**: Rebalance to {target.allocation}. Minimize tax: sell loss lots first (harvest), avoid wash sales, prefer long-term lots when selling gains. Execute all trades. Report expected tax impact.
- **Primitives**: state_tracking, planning, backtracking, verification, grounding
- **Seed**: `portfolio_diverse` (multi-lot), `transaction_ledger`, `tax_documents`, `stock_universe`
- **Eval**: Allocation within 2% of targets, no wash sale violations, loss lots sold before gain lots

#### `rh_options_income_portfolio`
- **Instruction**: Build monthly income: for each stock with >=100 shares, sell covered call at delta ~0.30. For others, sell cash-secured put at delta ~-0.30. Calculate total premium and max assignment risk.
- **Primitives**: state_tracking, planning, exploration, grounding, verification
- **Seed**: `portfolio_diverse`, `options_chain` (for all portfolio symbols), `stock_universe`
- **Eval**: Covered calls for 100+ share positions, CSPs for others, `send_msg_to_user` contains total premium

#### `rh_year_end_tax_planning`
- **Instruction**: Calculate realized gains from 1099 preview. Find unrealized losses to harvest (no wash sales). Execute sells. Set up recurring investments to re-enter after 31 days. Report tax savings (24% short-term, 15% long-term bracket).
- **Primitives**: state_tracking, planning, backtracking, verification, patience
- **Seed**: `tax_documents`, `portfolio_diverse`, `transaction_ledger`, `stock_universe`
- **Eval**: Sell orders for harvested losses, recurring investments set 31+ days out for same symbols, `send_msg_to_user` contains tax savings estimate

#### `rh_suspicious_activity_investigation`
- **Instruction**: Investigate the security alert about an unrecognized login. Check security log, check for orders placed during that session's time window, check for settings changes. Cancel any unauthorized orders, enable authenticator 2FA. Report findings.
- **Primitives**: exploration, state_tracking, verification, planning, backtracking
- **Seed**: `security_log` (suspicious entry), `filled_orders` (some in suspicious window), `notifications` (security_alert), `AccountSettings`
- **Eval**: Suspicious-window orders cancelled, 2FA enabled, `send_msg_to_user` contains findings

#### `rh_complex_transfer_reconciliation`
- **Instruction**: Your cash balance seems wrong. Reconcile from scratch: opening deposit + all deposits - all withdrawals + all sell proceeds - all buy costs + dividends + interest - fees. Find the missing or duplicated transaction.
- **Primitives**: state_tracking, verification, grounding, patience, exploration
- **Seed**: `transfers_history`, `transaction_ledger` (with one duplicate or missing entry), `portfolio_diverse`
- **Eval**: `send_msg_to_user` identifies the specific problematic transaction

#### `rh_portfolio_transition`
- **Instruction**: Switch from growth to income: sell all positions with dividend yield <1% (limit orders at bid price). Allocate proceeds: 50% to top 3 dividend yields from "{target.watchlist}", 30% to BND, 20% to SCHD. Report estimated annual dividend income change.
- **Primitives**: planning, state_tracking, exploration, grounding, verification
- **Seed**: `portfolio_diverse` (growth-heavy), `watchlist` (income stocks), `stock_universe`, `dividend_schedule`
- **Eval**: Sell orders for low-yield stocks, buy orders with correct allocation, `send_msg_to_user` contains income change

#### `rh_options_expiration_management`
- **Instruction**: Manage 8 options expiring Friday: profitable longs (>20% gain) → sell to close, losing longs → let expire, ITM shorts → buy to close, OTM shorts → let expire. Execute all and report net P/L.
- **Primitives**: state_tracking, planning, grounding, verification, backtracking
- **Seed**: `complex_options_book` (8 positions, mix of scenarios), `options_chain`, `stock_universe`
- **Eval**: Correct action for each position type, `send_msg_to_user` contains net P/L

#### `rh_complete_account_audit`
- **Instruction**: Full audit: (1) verify position quantities match transaction buy/sell totals, (2) verify cash balance reconciles, (3) check recurring investments execute on schedule, (4) verify alerts are for owned stocks, (5) no transfers pending >5 business days. Report all discrepancies.
- **Primitives**: state_tracking, verification, exploration, patience, grounding
- **Seed**: `portfolio_diverse`, `transaction_ledger`, `recurring_investments`, `price_alerts`, `transfers_history` (with deliberate issues)
- **Eval**: `send_msg_to_user` contains all discrepancies found

#### `rh_multi_strategy_execution`
- **Instruction**: Execute three strategies: (a) harvest losses >$500 (check wash sales), (b) collar your largest position (buy put + sell call), (c) start $100/week DCA into 3 stocks from watchlist. Strategies must be consistent — don't sell in (a) what you collar in (b).
- **Primitives**: planning, state_tracking, backtracking, verification, grounding, exploration
- **Seed**: `portfolio_diverse`, `options_chain`, `watchlist`, `transaction_ledger`, `stock_universe`
- **Eval**: Loss sells don't include collared stock, collar orders correct, 3 recurring investments created

#### `rh_quarterly_performance_review`
- **Instruction**: Generate quarterly review: portfolio return vs SPY, sector breakdown, best/worst positions, largest single-day loss, total fees, dividend income vs last quarter, pending corporate actions. Compile comprehensive report.
- **Primitives**: state_tracking, exploration, grounding, verification, patience
- **Seed**: `portfolio_diverse`, `transaction_ledger`, `dividend_schedule`, `stock_universe` (includes SPY), `notifications` (corporate actions)
- **Eval**: `send_msg_to_user` contains all required metrics (portfolio return, sector %, best/worst, fees, dividend comparison)

---

## 8. Frontend Architecture

### Build Setup
- **Framework**: React 18 + React Router v6
- **Bundler**: Vite
- **Output**: `static/envs/robinhood/`
- **Workspace**: `@webagentbench/robinhood` in pnpm monorepo

### Component Structure
```
environments/robinhood/src/
├── App.tsx                    # Task launcher + Shell router
├── Shell.tsx                  # Top nav + right sidebar + <Outlet/>
├── context.ts                 # RobinhoodLayoutContext (session, api, account summary)
├── api.ts                     # createRobinhoodApi() factory
├── mutator.ts                 # Static adapter mutations (demo mode)
├── types.ts                   # TypeScript interfaces for all entities
├── robinhood.css              # Faithful Robinhood styling
├── icons.tsx                  # Feather logo, chart icons
│
├── pages/
│   ├── Portfolio.tsx           # Home page — chart, positions, buying power
│   ├── StockDetail.tsx         # Individual stock page
│   ├── OptionsChain.tsx        # Options chain table
│   ├── Trade.tsx               # Buy/sell order form
│   ├── OptionsTrade.tsx        # Options order builder
│   ├── Search.tsx              # Search + explore
│   ├── Watchlists.tsx          # All watchlists
│   ├── WatchlistDetail.tsx     # Single watchlist
│   ├── Orders.tsx              # Order history
│   ├── Transactions.tsx        # Transaction ledger
│   ├── Recurring.tsx           # Recurring investments
│   ├── Transfers.tsx           # Deposit/withdraw
│   ├── TaxCenter.tsx           # Tax documents + gains
│   ├── Dividends.tsx           # Dividend schedule
│   ├── Notifications.tsx       # Notification center
│   └── Account.tsx             # Settings + security
│
└── components/
    ├── PositionRow.tsx          # Position in portfolio list
    ├── StockChart.tsx           # SVG line chart with time range
    ├── Sparkline.tsx            # Mini SVG sparkline
    ├── OrderForm.tsx            # Reusable order entry
    ├── OptionsTable.tsx         # Calls/puts grid
    ├── WatchlistItem.tsx        # Symbol row in watchlist
    ├── TransactionRow.tsx       # Ledger entry
    ├── NotificationItem.tsx     # Notification row
    ├── StatsGrid.tsx            # Key stats (P/E, market cap, etc.)
    └── SearchBar.tsx            # Top nav search
```

### AdapterProvider Integration
- **Live mode**: All API calls go to FastAPI `/api/env/robinhood/*`
- **Static mode**: `robinhoodMutator` handles state transforms in-memory for demo site
- **Demo site**: `RobinhoodWrapper` component (like `GmailWrapper`) embeds the UI with fixture data

---

## 9. Backend Architecture

### File Structure
```
webagentbench/
├── backend/
│   ├── models/
│   │   └── robinhood.py         # All Pydantic models + RobinhoodState
│   ├── seeders/
│   │   └── robinhood.py         # RobinhoodSeedRunner
│   └── routes/
│       └── robinhood.py         # All API endpoints
│
├── tasks/
│   ├── robinhood/               # 50 task YAML files
│   │   ├── rh_buy_market_order.yaml
│   │   ├── ...
│   │   └── rh_quarterly_performance_review.yaml
│   └── _seed_builders_robinhood.py  # ~20 builder functions
│
└── environments/
    └── robinhood/               # React SPA source
```

### Registration
- Add `"robinhood"` to `SEEDER_REGISTRY` in `backend/seeders/__init__.py`
- Add robinhood routes in `backend/routes/__init__.py` via `mount_environment_routes()`
- Task registry auto-discovers `tasks/robinhood/*.yaml`
- BrowserGym auto-registers as `browsergym/webagentbench.rh_*`

---

## 10. Demo Site Integration

- Add `RobinhoodWrapper` to demo-site components
- Generate fixtures for each task: `fixtures/robinhood/{task_id}.json`
- Add Robinhood to environment grid on demo site home page
- Route: `/environment?env=robinhood&task=rh_buy_market_order`

---

## 11. Seven Cognitive Primitives Coverage

| Primitive | Easy | Medium | Hard | Expert | Frontier | Total |
|-----------|------|--------|------|--------|----------|-------|
| grounding | 8 | 7 | 7 | 6 | 6 | 34 |
| planning | 8 | 8 | 7 | 8 | 9 | 40 |
| state_tracking | 1 | 7 | 10 | 10 | 10 | 38 |
| exploration | 3 | 5 | 4 | 5 | 4 | 21 |
| verification | 0 | 0 | 5 | 6 | 8 | 19 |
| backtracking | 0 | 0 | 2 | 3 | 5 | 10 |
| patience | 0 | 0 | 0 | 0 | 4 | 4 |

Every primitive appears in at least 4 tasks. Higher-level primitives (verification, backtracking, patience) concentrate at higher difficulty levels — by design.
