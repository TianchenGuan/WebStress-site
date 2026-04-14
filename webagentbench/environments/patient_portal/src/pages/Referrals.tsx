import { useCallback, useEffect, useState } from "react";

import { usePatientPortal } from "../context";
import type { Referral } from "../types";

export function ReferralsPage() {
  const { api, providers } = usePatientPortal();
  const [referrals, setReferrals] = useState<Referral[]>([]);

  const providerName = (id: string | null) => {
    if (!id) return "Unassigned";
    return providers.find((p) => p.id === id)?.name ?? id;
  };

  const loadReferrals = useCallback(async () => {
    try {
      const items = await api.listReferrals();
      setReferrals(items.sort((a, b) => new Date(b.expires_at).getTime() - new Date(a.expires_at).getTime()));
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => { void loadReferrals(); }, [loadReferrals]);

  return (
    <div aria-label="Referrals Page">
      <h2>Referrals</h2>

      <section aria-label="Active Referrals" className="pp-section">
        <h3>Referral List</h3>
        {referrals.length === 0 ? (
          <p>No referrals on file.</p>
        ) : (
          <table aria-label="Referral table">
            <thead>
              <tr>
                <th>Referral ID</th>
                <th>Specialty</th>
                <th>Provider</th>
                <th>Status</th>
                <th>Prior Auth</th>
                <th>Linked Appointment</th>
                <th>Expires</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {referrals.map((referral) => (
                <tr key={referral.id}>
                  <td>{referral.id}</td>
                  <td>{referral.to_specialty}</td>
                  <td>{providerName(referral.to_provider_id)}</td>
                  <td><span className={`pp-status-badge pp-status-badge--${referral.status}`}>{referral.status}</span></td>
                  <td>{referral.prior_auth_required ? referral.prior_auth_status : "Not required"}</td>
                  <td>{referral.linked_appointment_id ?? "None"}</td>
                  <td>{new Date(referral.expires_at).toLocaleDateString()}</td>
                  <td>{referral.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
