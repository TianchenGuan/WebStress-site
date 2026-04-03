import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@webagentbench/shared";

import { useRobinhoodLayout } from "../context";
import type { OptionsContract } from "../types";

const STRATEGIES = [
  { value: "single", label: "Single" },
  { value: "vertical", label: "Vertical Spread" },
  { value: "iron_condor", label: "Iron Condor" },
  { value: "straddle", label: "Straddle" },
  { value: "strangle", label: "Strangle" },
  { value: "covered_call", label: "Covered Call" },
  { value: "protective_put", label: "Protective Put" },
] as const;

type StrategyValue = (typeof STRATEGIES)[number]["value"];

interface DraftLeg {
  contractId: string;
  side: "buy" | "sell";
  quantity: string;
}

function byStrikeAscending(a: OptionsContract, b: OptionsContract) {
  return Number.parseFloat(a.strike) - Number.parseFloat(b.strike);
}

function nearestIndex(contracts: OptionsContract[], targetStrike: number) {
  if (contracts.length === 0) return 0;
  let winner = 0;
  let bestDistance = Math.abs(Number.parseFloat(contracts[0].strike) - targetStrike);
  for (let i = 1; i < contracts.length; i += 1) {
    const nextDistance = Math.abs(Number.parseFloat(contracts[i].strike) - targetStrike);
    if (nextDistance < bestDistance) {
      winner = i;
      bestDistance = nextDistance;
    }
  }
  return winner;
}

function clampIndex(index: number, length: number) {
  if (length <= 0) return 0;
  return Math.min(Math.max(index, 0), length - 1);
}

function contractLabel(contract: OptionsContract) {
  return `${contract.option_type.toUpperCase()} $${Number.parseFloat(contract.strike).toFixed(2)} exp ${contract.expiration}`;
}

function buildStrategyLegs(
  strategy: StrategyValue,
  contracts: OptionsContract[],
  anchorContractId?: string | null,
): DraftLeg[] {
  if (contracts.length === 0) return [];

  const anchor = contracts.find((contract) => contract.contract_id === anchorContractId) ?? contracts[0];
  const expiration = anchor.expiration;
  const calls = contracts
    .filter((contract) => contract.expiration === expiration && contract.option_type === "call")
    .sort(byStrikeAscending);
  const puts = contracts
    .filter((contract) => contract.expiration === expiration && contract.option_type === "put")
    .sort(byStrikeAscending);

  const fallbackCall = calls[Math.floor(calls.length / 2)] ?? contracts[0];
  const fallbackPut = puts[Math.floor(puts.length / 2)] ?? contracts[0];
  const referenceCall = anchor.option_type === "call" ? anchor : fallbackCall;
  const referencePut = anchor.option_type === "put" ? anchor : fallbackPut;
  const callIndex = nearestIndex(calls, Number.parseFloat(referenceCall.strike));
  const putIndex = nearestIndex(puts, Number.parseFloat(referencePut.strike));

  const fromCall = (index: number, side: "buy" | "sell"): DraftLeg => ({
    contractId: (calls[clampIndex(index, calls.length)] ?? referenceCall).contract_id,
    side,
    quantity: "1",
  });
  const fromPut = (index: number, side: "buy" | "sell"): DraftLeg => ({
    contractId: (puts[clampIndex(index, puts.length)] ?? referencePut).contract_id,
    side,
    quantity: "1",
  });

  switch (strategy) {
    case "covered_call":
      return [fromCall(callIndex, "sell")];
    case "protective_put":
      return [fromPut(putIndex, "buy")];
    case "vertical":
      return [fromCall(callIndex, "buy"), fromCall(callIndex + 1, "sell")];
    case "straddle":
      return [fromCall(callIndex, "buy"), fromPut(nearestIndex(puts, Number.parseFloat(referenceCall.strike)), "buy")];
    case "strangle":
      return [fromPut(putIndex - 1, "buy"), fromCall(callIndex + 1, "buy")];
    case "iron_condor":
      return [
        fromPut(putIndex - 1, "buy"),
        fromPut(putIndex, "sell"),
        fromCall(callIndex, "sell"),
        fromCall(callIndex + 1, "buy"),
      ];
    case "single":
    default:
      return [{
        contractId: anchor.contract_id,
        side: "buy",
        quantity: "1",
      }];
  }
}

export function OptionsTradePage() {
  const { symbol } = useParams<{ symbol: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { api, notify } = useRobinhoodLayout();
  const [contracts, setContracts] = useState<OptionsContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [strategy, setStrategy] = useState<StrategyValue>("single");
  const [draftLegs, setDraftLegs] = useState<DraftLeg[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    api.getOptionsChain(symbol)
      .then((nextContracts) => {
        if (cancelled) return;
        setContracts(nextContracts);
        setDraftLegs(buildStrategyLegs("single", nextContracts));
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, symbol]);

  const contractsById = useMemo(
    () => Object.fromEntries(contracts.map((contract) => [contract.contract_id, contract])),
    [contracts],
  );

  const netPremium = draftLegs.reduce((total, leg) => {
    const contract = contractsById[leg.contractId];
    if (!contract) return total;
    const quantity = Number.parseInt(leg.quantity || "1", 10) || 1;
    const quote = Number.parseFloat(leg.side === "buy" ? contract.ask : contract.bid);
    return total + (leg.side === "buy" ? 1 : -1) * quote * quantity * 100;
  }, 0);

  const resetForStrategy = (nextStrategy: StrategyValue) => {
    const anchorContractId = draftLegs[0]?.contractId ?? contracts[0]?.contract_id;
    setStrategy(nextStrategy);
    setDraftLegs(buildStrategyLegs(nextStrategy, contracts, anchorContractId));
  };

  const handleLegChange = (index: number, updates: Partial<DraftLeg>) => {
    setDraftLegs((current) => current.map((leg, legIndex) => (
      legIndex === index ? { ...leg, ...updates } : leg
    )));
  };

  const handleAddLeg = () => {
    const fallbackContractId = draftLegs[draftLegs.length - 1]?.contractId ?? contracts[0]?.contract_id;
    if (!fallbackContractId || draftLegs.length >= 4) return;
    setDraftLegs((current) => [
      ...current,
      {
        contractId: fallbackContractId,
        side: "buy",
        quantity: "1",
      },
    ]);
  };

  const handleRemoveLeg = (index: number) => {
    setDraftLegs((current) => current.filter((_, legIndex) => legIndex !== index));
  };

  const handleSubmit = async () => {
    if (!symbol || draftLegs.length === 0) return;
    const legs = draftLegs
      .map((leg) => {
        const contract = contractsById[leg.contractId];
        if (!contract) return null;
        return {
          underlying_symbol: symbol,
          side: leg.side,
          option_type: contract.option_type,
          strike: contract.strike,
          expiration: contract.expiration,
          quantity: Number.parseInt(leg.quantity || "1", 10) || 1,
          premium: leg.side === "buy" ? contract.ask : contract.bid,
        };
      })
      .filter((leg): leg is NonNullable<typeof leg> => leg !== null);

    if (legs.length === 0) return;

    setIsSubmitting(true);
    try {
      await api.placeOptionsOrder({ strategy, legs });
      notify("Options Order Placed", `${strategy.replace(/_/g, " ")} on ${symbol}`);
      navigate(preserveQueryParams("/options/positions", location.search));
    } catch (err) {
      notify("Order Failed", err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-options-trade" aria-label={`Trade ${symbol} options`}>
      <div className="rh-options-trade__header">
        <button
          className="rh-back-btn"
          onClick={() => navigate(preserveQueryParams(`/stocks/${symbol}/options`, location.search))}
          aria-label="Back to options chain"
        >
          ← {symbol} Options
        </button>
        <h1>Trade {symbol} Options</h1>
      </div>

      <div className="rh-order-form__field">
        <label htmlFor="opt-strategy">Strategy</label>
        <select
          id="opt-strategy"
          value={strategy}
          onChange={(e) => resetForStrategy(e.target.value as StrategyValue)}
        >
          {STRATEGIES.map((entry) => (
            <option key={entry.value} value={entry.value}>{entry.label}</option>
          ))}
        </select>
      </div>

      <div className="rh-options-trade__helper">
        Strategy presets populate a real leg editor. You can adjust contracts, sides, and quantities before submitting.
      </div>

      <div className="rh-options-trade__legs">
        {draftLegs.map((leg, index) => {
          const contract = contractsById[leg.contractId];
          return (
            <div key={`${leg.contractId}-${index}`} className="rh-options-trade__leg-card">
              <div className="rh-options-trade__leg-header">
                <strong>Leg {index + 1}</strong>
                {draftLegs.length > 1 ? (
                  <button
                    type="button"
                    className="rh-options-trade__remove-leg"
                    onClick={() => handleRemoveLeg(index)}
                    aria-label={`Remove leg ${index + 1}`}
                  >
                    Remove
                  </button>
                ) : null}
              </div>
              <div className="rh-options-trade__leg-fields">
                <div className="rh-order-form__field">
                  <label htmlFor={`opt-leg-side-${index}`}>Side</label>
                  <select
                    id={`opt-leg-side-${index}`}
                    value={leg.side}
                    onChange={(e) => handleLegChange(index, { side: e.target.value as "buy" | "sell" })}
                  >
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                  </select>
                </div>
                <div className="rh-order-form__field">
                  <label htmlFor={`opt-leg-contract-${index}`}>Contract</label>
                  <select
                    id={`opt-leg-contract-${index}`}
                    value={leg.contractId}
                    onChange={(e) => handleLegChange(index, { contractId: e.target.value })}
                  >
                    {contracts.map((entry) => (
                      <option key={entry.contract_id} value={entry.contract_id}>
                        {contractLabel(entry)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="rh-order-form__field">
                  <label htmlFor={`opt-leg-quantity-${index}`}>Contracts</label>
                  <input
                    id={`opt-leg-quantity-${index}`}
                    type="number"
                    min="1"
                    value={leg.quantity}
                    onChange={(e) => handleLegChange(index, { quantity: e.target.value })}
                  />
                </div>
              </div>
              {contract ? (
                <div className="rh-options-trade__leg-summary">
                  <span>{contract.option_type.toUpperCase()}</span>
                  <span>${Number.parseFloat(contract.strike).toFixed(2)}</span>
                  <span>exp {contract.expiration}</span>
                  <span>Bid ${Number.parseFloat(contract.bid).toFixed(2)}</span>
                  <span>Ask ${Number.parseFloat(contract.ask).toFixed(2)}</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="rh-options-trade__actions">
        <Button variant="secondary" disabled={draftLegs.length >= 4} onClick={handleAddLeg}>
          Add Leg
        </Button>
        <Button variant="secondary" onClick={() => resetForStrategy(strategy)}>
          Reset Preset
        </Button>
      </div>

      <div className="rh-order-form__summary">
        <div className="rh-order-form__row">
          <span>Leg Count</span>
          <span>{draftLegs.length}</span>
        </div>
        <div className="rh-order-form__row">
          <span>Estimated Net {netPremium >= 0 ? "Debit" : "Credit"}</span>
          <span>${Math.abs(netPremium).toFixed(2)}</span>
        </div>
      </div>

      <Button
        variant="primary"
        disabled={draftLegs.length === 0 || isSubmitting}
        onClick={handleSubmit}
        aria-label="Submit options order"
      >
        {isSubmitting ? "Submitting..." : `Submit ${strategy.replace(/_/g, " ")} Order`}
      </Button>
    </div>
  );
}
