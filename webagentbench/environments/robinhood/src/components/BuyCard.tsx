import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@webagentbench/shared";
import { useRobinhoodLayout } from "../context";

interface BuyCardProps {
  symbol: string;
  price: number;
  name: string;
}

export function BuyCard({ symbol, price, name }: BuyCardProps) {
  const location = useLocation();
  const { api, account } = useRobinhoodLayout();
  const [shares, setShares] = useState("1");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const qty = parseFloat(shares) || 0;
  const estimatedCost = qty * price;
  const buyingPower = account ? parseFloat(account.buying_power) : 0;

  const handleSubmit = async () => {
    if (qty <= 0) return;
    setError("");
    try {
      await api.placeOrder({
        symbol,
        side,
        order_type: "market",
        quantity: qty,
      });
      setSubmitted(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Order failed");
    }
  };

  if (submitted) {
    return (
      <div className="rh-buy-card" aria-label={`${side} ${symbol}`}>
        <div className="rh-buy-card__success">
          <h3>Order Placed</h3>
          <p>
            Your market {side} order for {qty} share{qty !== 1 ? "s" : ""} of {symbol} has been submitted.
          </p>
          <Button variant="primary" className="rh-btn--buy" onClick={() => setSubmitted(false)}>
            Done
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="rh-buy-card" aria-label={`${side} ${symbol}`}>
      <div className="rh-buy-card__tabs">
        <button
          className={`rh-buy-card__tab ${side === "buy" ? "rh-buy-card__tab--active" : ""}`}
          onClick={() => setSide("buy")}
        >
          Buy {symbol}
        </button>
        <button
          className={`rh-buy-card__tab ${side === "sell" ? "rh-buy-card__tab--active rh-buy-card__tab--sell" : ""}`}
          onClick={() => setSide("sell")}
        >
          Sell {symbol}
        </button>
      </div>

      <div className="rh-buy-card__field">
        <label>Shares</label>
        <input
          type="number"
          min="0"
          step="1"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          aria-label="Number of shares"
        />
      </div>

      <div className="rh-buy-card__field">
        <label>Market Price</label>
        <span className="rh-buy-card__price">${price.toFixed(2)}</span>
      </div>

      <div className="rh-buy-card__divider" />

      <div className="rh-buy-card__estimate">
        <span>Estimated {side === "buy" ? "Cost" : "Credit"}</span>
        <span>${estimatedCost.toFixed(2)}</span>
      </div>

      {error && <p className="rh-buy-card__error">{error}</p>}

      <Button
        variant="primary"
        className={`rh-buy-card__submit ${side === "buy" ? "rh-btn--buy" : "rh-order-form__submit--sell"}`}
        onClick={handleSubmit}
        aria-label={`${side === "buy" ? "Buy" : "Sell"} ${symbol}`}
      >
        {side === "buy" ? "Buy" : "Sell"}
      </Button>

      <div className="rh-buy-card__buying-power">
        ${buyingPower.toLocaleString("en-US", { minimumFractionDigits: 2 })} buying power available
      </div>

      <div className="rh-buy-card__actions">
        <Link to={preserveQueryParams(`/stocks/${symbol}/trade`, location.search)}>
          <Button variant="secondary" className="rh-buy-card__advanced" aria-label={`Advanced trade ${symbol}`}>
            More Options
          </Button>
        </Link>
      </div>

      <Button variant="secondary" className="rh-buy-card__add-list" aria-label={`Add ${name} to lists`}>
        Add to Lists
      </Button>
    </div>
  );
}
