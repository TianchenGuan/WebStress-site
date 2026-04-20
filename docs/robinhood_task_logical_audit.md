# Robinhood Task Logical Audit

This is a per-task logical audit of the Robinhood suite after the latest hardening pass.

Legend:
- `tight`: the evaluator covers the task's main clauses with solid positive and negative checks.
- `adequate`: logically acceptable for its scope, but still lighter than the Gmail benchmark bar.
- `watch`: currently functional and monitored, but thinner or more branch-sensitive than ideal.

## Tight

- `rh_complete_account_audit`: audit discrepancies, stale alerts, overdue recurring investments, pending transfers, and report content are all scored.
- `rh_complex_transfer_reconciliation`: report content and reconciliation concepts are scored across the cash-flow categories named in the prompt.
- `rh_consolidate_recurring`: duplicate recurring investments, monthly consolidation, and exact combined amounts are scored directly.
- `rh_cost_basis_reconciliation`: both cost-basis sources and discrepancy language are scored in the report.
- `rh_covered_call_strategy`: underlying, option side/type, strike range, expiration window, and premium reporting are all checked.
- `rh_cross_reference_1099`: seeded discrepancy symbols and both reported figures are required in the report.
- `rh_dividend_income_report`: the lowest-income holding must be fully exited and proceeds must rotate into the highest-yield watchlist name.
- `rh_earnings_play_setup`: stop-loss, alert, exposure reporting, and protection-plan content are all explicitly scored on the seeded symbol.
- `rh_full_portfolio_rebalance_with_tax`: target-fund buys, wash-sale avoidance, tax reporting, and projected allocation improvement are all scored.
- `rh_multi_leg_options`: structure, wing ordering, underlying isolation, and max profit/loss reporting are all checked.
- `rh_multi_strategy_execution`: harvesting, collar construction, watchlist recurring buys, and the no-sell-on-protected-name constraint are all represented.
- `rh_notification_triage`: read-state, slippage naming, threshold language, and no-cancel behavior are all covered.
- `rh_options_chain_analysis`: the correct TSLA contract and all requested reported values are scored.
- `rh_options_expiration_management`: every action/no-action bucket is represented and the report must mention the resulting P/L.
- `rh_options_income_portfolio`: covered-call vs cash-secured-put routing plus premium and assignment-risk reporting are both scored.
- `rh_options_roll_strategy`: buyback, later-dated resell, strike band, report content, and underlying isolation are all covered.
- `rh_portfolio_rebalance`: the evaluator now scores projected end-state allocation improvement and bounded total allocation error, not just trade existence.
- `rh_portfolio_risk_assessment`: concentration, expiring options, margin utilization, and report content are all checked.
- `rh_portfolio_transition`: low-yield exits, destination buys, and projected dividend-income change reporting are all scored.
- `rh_quarterly_performance_review`: best/worst names, fees, quarter-over-quarter dividends, sector mentions, and corporate actions all appear in the report checks.
- `rh_suspicious_activity_investigation`: suspicious-order cancellation, authenticator 2FA, flagged location, and report content are all scored.
- `rh_tax_optimization`: loss-symbol constraint, wash-sale avoidance, and harvested-loss coverage against realized gains are all checked.
- `rh_transfer_history_audit`: both totals and the consistency conclusion are scored in the report.
- `rh_watchlist_screening`: post-screen watchlist membership and the exact set of limit buys for passing symbols are checked directly.
- `rh_year_end_tax_planning`: harvest sells, wash-sale avoidance, re-entry recurring investments, and gains-offset logic are all represented.

## Adequate

- `rh_add_to_watchlist`: correct watchlist, correct symbol, exact size, and wrong-watchlist drift are covered.
- `rh_buy_market_order`: exact filled market buy, resulting position quantity, and wrong-symbol drift are covered.
- `rh_cancel_pending_order`: correct-symbol cancellation and no collateral cancellation are covered, though one positive check is still seed-oriented.
- `rh_check_buying_power`: the exact amount must be reported and no trading/transfer side effects are allowed.
- `rh_compare_dividend_yields`: highest-yield selection into the named watchlist is scored and extra candidates are constrained.
- `rh_create_watchlist`: exact name, exact membership, and no unrelated account actions are enforced.
- `rh_deposit_funds`: correct direction, amount, default bank, and resulting balances are scored.
- `rh_deposit_then_buy`: deposit bank, deposit amount, buy symbol, and resulting position are all checked.
- `rh_dividend_reinvestment_analysis`: the low-yield-on-cost branch, dividend-reinvestment toggle, and recurring target selection are covered.
- `rh_enable_extended_hours`: settings-only behavior is enforced with no unrelated state changes.
- `rh_find_earnings_and_alert`: every owned symbol with near-term earnings must get the correct alert and no extra owned-name alerts are allowed.
- `rh_live_alert_and_buy`: triggered alert, exact filled market buy, and no wrong order type are all covered.
- `rh_live_alert_and_sell`: triggered alert, exact sell branch, zero remaining TSLA exposure, and no accidental buy are all covered.
- `rh_live_bracket_order`: buy fill plus both protective exit orders are checked on the intended underlying.
- `rh_live_comparative_watch`: the seeded AAPL-outperformance branch now scores full MSFT exit, AAPL rotation, and timing.
- `rh_live_cross_stock_alert`: both alerts and both sides of the pairs trade are scored with price-band confirmation.
- `rh_live_dual_alert_decision`: the seeded bearish branch is covered with both alerts present and the correct sell behavior.
- `rh_live_intraday_reversal`: order count, timing, price band, and no-limit-order behavior are covered.
- `rh_live_multi_stock_limits`: each named limit order now scores its own price threshold and expected fill/pending status.
- `rh_live_stop_loss_execution`: correct order type, symbol, quantity, and stop band are covered.
- `rh_live_take_profit`: correct limit sell, quantity, target price threshold, and no wrong-side action are covered.
- `rh_live_watch_and_buy`: exact filled market buy, timing, and no-limit-order behavior are enforced.
- `rh_live_watch_spread`: reversal buy timing, price band, and no-limit-order behavior are covered.
- `rh_margin_call_resolution`: correct sell symbol, deposit buffer, and no unrelated trade/withdrawal behavior are all checked.
- `rh_recurring_optimization`: risky recurring ids must be paused and non-risky recurring plans must stay active.
- `rh_review_and_cancel_orders`: stale deep-below-market limit buys must be cancelled and in-range limit buys must remain pending.
- `rh_sector_concentration`: correct sell symbol, correct destination buy, and resulting sector percentage are scored.
- `rh_sell_loser_buy_winner`: the worst symbol must be sold, the best symbol must be bought, and drift to other symbols is blocked.
- `rh_sell_shares`: exact sell quantity, zero remaining exposure, and no wrong-side/wrong-symbol trade are covered.
- `rh_setup_recurring_investment`: correct symbol, amount, frequency, Monday start, and uniqueness are all scored.
- `rh_transfer_and_withdraw`: the correct withdrawal target and the resulting balances are both checked.
- `rh_wash_sale_avoidance`: loss harvesting is constrained to eligible symbols and recent-buy wash-sale names are blocked.

## Watch

- `rh_limit_order_with_check`: correct limit-order shape and price band are covered, but it is still a compact two-check task.
- `rh_live_alert_chain`: the seeded branch is scored, but the prompt is conditional and still deserves richer branch-specific monitoring later.
- `rh_live_buy_the_dip`: the core buy/fill behavior is covered, but the task is still quite thin for a live waiting workflow.
- `rh_live_watch_portfolio`: correct sell symbol and timing are covered, but the evaluator still does not score sell sizing or proceeds usage.
- `rh_mark_notifications_read`: acceptable for a simple task, but it is intentionally very light.
- `rh_options_buy_call`: the contract-selection logic is correct, but the evaluator is still very compact for an options task.
- `rh_security_audit`: foreign-login detection and authenticator enablement are covered, but the task remains intentionally narrow.
- `rh_set_price_alert`: exact alert symbol/condition/price are checked, but it is still a minimal single-action task.
