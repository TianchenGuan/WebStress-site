"""Verify the new cancellation fee flow.

- Seed a reservation with three different policies.
- Compute preview fee.
- Cancel with correct vs. wrong fee_accepted.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webagentbench.backend.models.booking import (
    BookingState,
    CancellationPolicy,
    Reservation,
    ReservationGuest,
    BookingSettings,
)


def _fresh_state() -> BookingState:
    return BookingState(
        env_id="booking",
        task_id="test",
        owner_name="Test User",
        owner_email="test@example.com",
        settings=BookingSettings(id="settings_1"),
    )


def _mk_reservation(policy: CancellationPolicy, check_in_days_out: int, total_price: float = 400.0) -> Reservation:
    check_in = (datetime.now(timezone.utc) + timedelta(days=check_in_days_out)).strftime("%Y-%m-%d")
    check_out = (datetime.now(timezone.utc) + timedelta(days=check_in_days_out + 3)).strftime("%Y-%m-%d")
    return Reservation(
        id=f"res_{check_in_days_out}_{policy.type}",
        property_id="prop_1",
        property_name="Test Hotel",
        room_type_id="room_1",
        room_type_name="Test Room",
        check_in=check_in,
        check_out=check_out,
        nights=3,
        guests=2,
        rooms=1,
        price_per_night=round(total_price / 3, 2),
        total_price=total_price,
        status="confirmed",
        booked_at=datetime.now(timezone.utc),
        guest_info=ReservationGuest(full_name="Test User", email="t@e.com"),
        payment_method_id="pm_1",
        cancellation_policy=policy,
        confirmation_number="TEST-0001",
    )


def _run_case(label: str, policy: CancellationPolicy, check_in_days_out: int, expected_fee: float):
    st = _fresh_state()
    st.reservations.append(_mk_reservation(policy, check_in_days_out))
    rid = st.reservations[0].id
    preview = st.compute_cancel_fee(rid)
    got = preview["fee_amount"]
    ok = abs(got - expected_fee) < 0.01
    print(f"[{label:25s}] days_until={preview['days_until_checkin']:>3}  expected_fee={expected_fee:>7.2f}  got={got:>7.2f}  {'PASS' if ok else 'FAIL'}")

    # Try cancel with correct fee
    try:
        st.cancel_reservation(rid, fee_accepted=got)
        print(f"    cancel(fee_accepted=correct): OK, status={st.reservations[0].status}")
    except Exception as e:
        print(f"    cancel(fee_accepted=correct): UNEXPECTED FAIL: {e}")

    # Try cancel on fresh state with wrong fee
    st2 = _fresh_state()
    st2.reservations.append(_mk_reservation(policy, check_in_days_out))
    try:
        st2.cancel_reservation(rid, fee_accepted=got + 10.0)
        print(f"    cancel(fee_accepted=wrong): UNEXPECTED SUCCESS — rejection failed")
    except ValueError as e:
        print(f"    cancel(fee_accepted=wrong): correctly rejected: {str(e)[:60]}...")


# Case 1: free_cancellation, 30 days out → fee=0
_run_case("free 30d out", CancellationPolicy(type="free_cancellation", free_cancel_before_days=7, penalty_percentage=100.0, description="Free until 7 days before"), 30, 0.0)

# Case 2: free_cancellation, 3 days out (<7 days threshold) → fee=100% of 400 = 400
_run_case("free 3d out (within)", CancellationPolicy(type="free_cancellation", free_cancel_before_days=7, penalty_percentage=100.0, description="Free until 7 days before"), 3, 400.0)

# Case 3: partial_refund (50% fee always) → fee=200
_run_case("partial 50% always", CancellationPolicy(type="partial_refund", penalty_percentage=50.0, description="50% fee always"), 30, 200.0)

# Case 4: non_refundable → fee=400 (full)
_run_case("non_refundable", CancellationPolicy(type="non_refundable", penalty_percentage=100.0, description="Non-refundable"), 30, 400.0)
