import { useCallback, useEffect, useState } from "react";

import { usePatientPortal } from "../context";
import type { Appointment, Provider, Referral, SlotInfo } from "../types";

export function AppointmentsPage() {
  const { api, providers, notify } = usePatientPortal();
  const [upcoming, setUpcoming] = useState<Appointment[]>([]);
  const [past, setPast] = useState<Appointment[]>([]);
  const [showPast, setShowPast] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);

  // Schedule form state
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [slots, setSlots] = useState<SlotInfo[]>([]);
  const [selectedSlot, setSelectedSlot] = useState("");
  const [appointmentType, setAppointmentType] = useState("in-person");
  const [reason, setReason] = useState("");
  const [linkedReferralId, setLinkedReferralId] = useState("");
  const [referrals, setReferrals] = useState<Referral[]>([]);

  // Reschedule state
  const [rescheduleId, setRescheduleId] = useState<string | null>(null);
  const [rescheduleSlots, setRescheduleSlots] = useState<SlotInfo[]>([]);
  const [rescheduleSlot, setRescheduleSlot] = useState("");

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;
  const providerSpecialty = (id: string) => providers.find((p) => p.id === id)?.specialty ?? "";

  const loadAppointments = useCallback(async () => {
    try {
      const items = await api.listAppointments();
      const now = new Date();
      setUpcoming(
        items
          .filter((a) => a.status === "scheduled" && new Date(a.datetime) > now)
          .sort((a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime()),
      );
      setPast(
        items
          .filter((a) => a.status !== "scheduled" || new Date(a.datetime) <= now)
          .sort((a, b) => new Date(b.datetime).getTime() - new Date(a.datetime).getTime()),
      );
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => { void loadAppointments(); }, [loadAppointments]);
  useEffect(() => {
    void api.listReferrals().then(setReferrals).catch(() => setReferrals([]));
  }, [api]);

  useEffect(() => {
    if (!selectedProviderId) { setSlots([]); return; }
    void api.getAvailableSlots(selectedProviderId).then(setSlots).catch(() => setSlots([]));
  }, [api, selectedProviderId]);

  const handleCancel = async (aptId: string) => {
    try {
      await api.cancelAppointment(aptId);
      notify("Appointment cancelled");
      void loadAppointments();
    } catch {
      notify("Failed to cancel appointment");
    }
  };

  const handleSchedule = async () => {
    if (!selectedProviderId || !selectedSlot) return;
    try {
      await api.createAppointment({
        provider_id: selectedProviderId,
        slot_datetime: selectedSlot,
        type: appointmentType,
        reason,
        linked_referral_id: linkedReferralId || undefined,
      });
      notify("Appointment scheduled");
      setShowSchedule(false);
      setSelectedProviderId("");
      setSelectedSlot("");
      setReason("");
      setLinkedReferralId("");
      void loadAppointments();
    } catch (err) {
      const detail = (err as { detail?: { detail?: string } })?.detail;
      notify("Failed to schedule", typeof detail === "object" ? detail?.detail : String(detail ?? ""));
    }
  };

  const startReschedule = async (apt: Appointment) => {
    setRescheduleId(apt.id);
    try {
      const s = await api.getAvailableSlots(apt.provider_id);
      setRescheduleSlots(s);
    } catch {
      setRescheduleSlots([]);
    }
  };

  const handleReschedule = async () => {
    if (!rescheduleId || !rescheduleSlot) return;
    try {
      await api.rescheduleAppointment(rescheduleId, { new_slot_datetime: rescheduleSlot });
      notify("Appointment rescheduled");
      setRescheduleId(null);
      setRescheduleSlot("");
      void loadAppointments();
    } catch {
      notify("Failed to reschedule appointment");
    }
  };

  const schedulableProviders = providers.filter((p) => p.available_slots.length > 0);
  const selectedProvider = providers.find((p) => p.id === selectedProviderId);
  const eligibleReferrals = referrals.filter((referral) => {
    if (referral.status !== "approved") return false;
    if (!selectedProvider) return true;
    return referral.to_provider_id === selectedProvider.id || referral.to_specialty === selectedProvider.specialty;
  });

  return (
    <div aria-label="Appointments Page">
      <h2>Appointments</h2>

      <section aria-label="Upcoming Appointments" className="pp-section">
        <h3>Upcoming Appointments</h3>
        {upcoming.length === 0 ? (
          <p>No upcoming appointments.</p>
        ) : (
          <table aria-label="Upcoming appointments table">
            <thead>
              <tr>
                <th>Appointment ID</th>
                <th>Date/Time</th>
                <th>Provider</th>
                <th>Specialty</th>
                <th>Type</th>
                <th>Status</th>
                <th>Reason</th>
                <th>Linked Referral</th>
                <th>Location</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {upcoming.map((apt) => (
                <tr key={apt.id}>
                  <td>{apt.id}</td>
                  <td>{new Date(apt.datetime).toLocaleString()}</td>
                  <td>{providerName(apt.provider_id)}</td>
                  <td>{providerSpecialty(apt.provider_id)}</td>
                  <td>{apt.type}</td>
                  <td><span className={`pp-status-badge pp-status-badge--${apt.status}`}>{apt.status}</span></td>
                  <td>{apt.reason}</td>
                  <td>{apt.linked_referral_id ?? "None"}</td>
                  <td>{apt.location}</td>
                  <td>
                    <button
                      aria-label={`Cancel appointment with ${providerName(apt.provider_id)}`}
                      className="pp-btn pp-btn--danger pp-btn--sm"
                      onClick={() => handleCancel(apt.id)}
                    >
                      Cancel
                    </button>
                    <button
                      aria-label={`Reschedule appointment with ${providerName(apt.provider_id)}`}
                      className="pp-btn pp-btn--secondary pp-btn--sm"
                      onClick={() => startReschedule(apt)}
                    >
                      Reschedule
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {rescheduleId && (
          <div className="pp-form-section" aria-label="Reschedule appointment form">
            <h4>Reschedule Appointment</h4>
            <label htmlFor="reschedule-slot">New Date/Time</label>
            <select
              id="reschedule-slot"
              value={rescheduleSlot}
              onChange={(e) => setRescheduleSlot(e.target.value)}
              aria-label="Select new appointment slot"
            >
              <option value="">Select a slot...</option>
              {rescheduleSlots.map((s) => (
                <option key={s.datetime} value={s.datetime}>
                  {new Date(s.datetime).toLocaleString()} - {s.type} ({s.duration_minutes}min)
                </option>
              ))}
            </select>
            <div className="pp-form-actions">
              <button
                className="pp-btn pp-btn--primary"
                aria-label="Confirm reschedule"
                onClick={handleReschedule}
                disabled={!rescheduleSlot}
              >
                Confirm Reschedule
              </button>
              <button
                className="pp-btn pp-btn--secondary"
                aria-label="Cancel reschedule"
                onClick={() => { setRescheduleId(null); setRescheduleSlot(""); }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>

      <section aria-label="Past Appointments" className="pp-section">
        <button
          className="pp-btn pp-btn--secondary"
          aria-label={showPast ? "Hide past appointments" : "Show past appointments"}
          onClick={() => setShowPast(!showPast)}
        >
          {showPast ? "Hide" : "Show"} Past Appointments ({past.length})
        </button>
        {showPast && past.length > 0 && (
          <table aria-label="Past appointments table">
            <thead>
              <tr>
                <th>Appointment ID</th>
                <th>Date/Time</th>
                <th>Provider</th>
                <th>Specialty</th>
                <th>Type</th>
                <th>Status</th>
                <th>Linked Referral</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {past.map((apt) => (
                <tr key={apt.id}>
                  <td>{apt.id}</td>
                  <td>{new Date(apt.datetime).toLocaleString()}</td>
                  <td>{providerName(apt.provider_id)}</td>
                  <td>{providerSpecialty(apt.provider_id)}</td>
                  <td>{apt.type}</td>
                  <td><span className={`pp-status-badge pp-status-badge--${apt.status}`}>{apt.status}</span></td>
                  <td>{apt.linked_referral_id ?? "None"}</td>
                  <td>{apt.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-label="Schedule New Appointment" className="pp-section">
        <button
          className="pp-btn pp-btn--primary"
          aria-label={showSchedule ? "Hide schedule form" : "Schedule New Appointment"}
          onClick={() => setShowSchedule(!showSchedule)}
        >
          {showSchedule ? "Cancel" : "Schedule New Appointment"}
        </button>
        {showSchedule && (
          <div className="pp-form-section" aria-label="New appointment form">
            <div className="pp-form-field">
              <label htmlFor="apt-provider">Provider</label>
              <select
                id="apt-provider"
                value={selectedProviderId}
                onChange={(e) => { setSelectedProviderId(e.target.value); setSelectedSlot(""); }}
                aria-label="Select provider"
              >
                <option value="">Select a provider...</option>
                {Object.entries(groupBySpecialty(schedulableProviders)).map(([specialty, provs]) => (
                  <optgroup key={specialty} label={specialty}>
                    {provs.map((p) => (
                      <option key={p.id} value={p.id}>{p.name} - {p.department}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>

            {selectedProviderId && (
              <div className="pp-form-field">
                <label htmlFor="apt-slot">Date/Time</label>
                <select
                  id="apt-slot"
                  value={selectedSlot}
                  onChange={(e) => setSelectedSlot(e.target.value)}
                  aria-label="Select appointment slot"
                >
                  <option value="">Select a slot...</option>
                  {slots.map((s) => (
                    <option key={s.datetime} value={s.datetime}>
                      {new Date(s.datetime).toLocaleString()} - {s.type} ({s.duration_minutes}min)
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="pp-form-field">
              <label htmlFor="apt-type">Appointment Type</label>
              <select
                id="apt-type"
                value={appointmentType}
                onChange={(e) => setAppointmentType(e.target.value)}
                aria-label="Select appointment type"
              >
                <option value="in-person">In-Person</option>
                <option value="telehealth">Telehealth</option>
              </select>
            </div>

            <div className="pp-form-field">
              <label htmlFor="apt-reason">Reason for visit</label>
              <input
                id="apt-reason"
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                aria-label="Reason for visit"
                placeholder="Enter reason for visit"
              />
            </div>

            <div className="pp-form-field">
              <label htmlFor="apt-referral">Linked Referral (optional)</label>
              <select
                id="apt-referral"
                value={linkedReferralId}
                onChange={(e) => setLinkedReferralId(e.target.value)}
                aria-label="Select linked referral"
              >
                <option value="">No linked referral</option>
                {eligibleReferrals.map((referral) => (
                  <option key={referral.id} value={referral.id}>
                    {`${referral.id} - ${referral.to_specialty} - ${referral.status} - prior auth ${referral.prior_auth_status}`}
                  </option>
                ))}
              </select>
            </div>

            <button
              className="pp-btn pp-btn--primary"
              aria-label="Submit new appointment"
              onClick={handleSchedule}
              disabled={!selectedProviderId || !selectedSlot}
            >
              Schedule Appointment
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

function groupBySpecialty(providers: Provider[]): Record<string, Provider[]> {
  const groups: Record<string, Provider[]> = {};
  for (const p of providers) {
    if (!groups[p.specialty]) groups[p.specialty] = [];
    groups[p.specialty].push(p);
  }
  return groups;
}
