import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@webagentbench/shared";

import { useRobinhoodLayout } from "../context";
import type { Position, PortfolioData } from "../types";
import { PositionRow } from "../components/PositionRow";
import { StockChart } from "../components/StockChart";
import { CategoryChips, getDiscoverChips } from "../components/CategoryChips";
import { NewsCard } from "../components/NewsCard";

export function PortfolioPage() {
  const { api, account, liveTick } = useRobinhoodLayout();
  const location = useLocation();
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, pos] = await Promise.all([api.getPortfolio(), api.listPositions()]);
        if (!cancelled) {
          setPortfolio(p);
          setPositions(pos);
        }
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api, liveTick]);

  if (loading) return <div className="rh-loading">Loading...</div>;

  const portfolioValue = portfolio ? parseFloat(portfolio.portfolio_value) : 0;
  const dayChange = portfolio ? parseFloat(portfolio.day_change ?? "0") : 0;
  const dayChangePct = portfolio ? parseFloat(portfolio.day_change_pct ?? "0") : 0;
  const isPositive = dayChange >= 0;

  // Create fake chart data for portfolio
  const chartData = Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.now() - (29 - i) * 86400000).toISOString().slice(0, 10),
    close: String(portfolioValue * (1 + Math.sin(i * 0.3) * 0.03)),
  }));

  return (
    <div className="rh-portfolio" aria-label="Portfolio overview">
      <div className="rh-portfolio__header">
        <h1 className="rh-portfolio__value">${portfolioValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</h1>
        <span className={`rh-portfolio__change ${isPositive ? "rh-gain" : "rh-loss"}`}>
          {isPositive ? "+" : ""}${dayChange.toFixed(2)} ({isPositive ? "+" : ""}{dayChangePct.toFixed(2)}%) Today
        </span>
      </div>

      <StockChart data={chartData} positive={isPositive} />

      <div className="rh-portfolio__buying-power">
        <span>Buying Power</span>
        <span>${account ? parseFloat(account.buying_power).toLocaleString("en-US", { minimumFractionDigits: 2 }) : "0.00"}</span>
      </div>

      <section className="rh-portfolio__positions" aria-label="Positions">
        <div className="rh-portfolio__positions-header">
          <h2>Stocks</h2>
          <Link to={preserveQueryParams("/orders", location.search)} className="rh-link">
            Show More
          </Link>
        </div>
        {positions.length === 0 ? (
          <div className="rh-empty">No positions yet</div>
        ) : (
          positions.map((p) => <PositionRow key={p.id} position={p} />)
        )}
      </section>

      {/* Discover Investments */}
      <section className="rh-section" aria-label="Discover investments">
        <h2>Discover Investments</h2>
        <CategoryChips chips={getDiscoverChips()} />
      </section>

      {/* Market News */}
      <section className="rh-section" aria-label="News">
        <h2>News</h2>
        <NewsCard
          headline="Markets rally as Fed signals potential rate pause"
          source="Reuters"
          timestamp="1h ago"
          snippet="Major indices closed higher on Wednesday as investors digested the latest Federal Reserve meeting minutes suggesting a potential pause in rate hikes."
          tickers={["SPY", "QQQ"]}
          imageColor="#2d4a7a"
        />
        <NewsCard
          headline="Tech sector leads gains amid strong earnings season"
          source="Bloomberg"
          timestamp="3h ago"
          snippet="Technology stocks outperformed the broader market as several major companies reported better-than-expected quarterly results."
          tickers={["AAPL", "MSFT", "GOOGL"]}
          imageColor="#4a2d7a"
        />
        <NewsCard
          headline="Energy prices stabilize as OPEC+ maintains production targets"
          source="CNBC"
          timestamp="5h ago"
          snippet="Crude oil prices held steady after OPEC+ members confirmed they would maintain current production levels through the next quarter."
          tickers={["XLE", "CVX"]}
          imageColor="#7a4a2d"
        />
      </section>
    </div>
  );
}
