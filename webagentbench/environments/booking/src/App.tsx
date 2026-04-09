import { Routes, Route, Navigate } from "react-router-dom";
import { useSession } from "@webagentbench/shared";
import BookingShell from "./Shell";
import Home from "./pages/Home";
import SearchResults from "./pages/SearchResults";
import PropertyDetail from "./pages/PropertyDetail";
import BookingForm from "./pages/BookingForm";
import BookingConfirmation from "./pages/BookingConfirmation";
import MyTrips from "./pages/MyTrips";
import ReservationDetail from "./pages/ReservationDetail";
import AccountPage from "./pages/Account";
import SavedLists from "./pages/SavedLists";
import Messages from "./pages/Messages";
import Notifications from "./pages/Notifications";
import Settings from "./pages/Settings";
import Reviews from "./pages/Reviews";
import Deals from "./pages/Deals";
import "./booking.css";

function BookingLauncher() {
  return (
    <div style={{ padding: 40, textAlign: "center" }}>
      <h1>Booking Environment</h1>
      <p>Launch a task from the <a href="/launch">WebAgentBench launcher</a>.</p>
    </div>
  );
}

export default function App() {
  const { sessionId } = useSession("booking");

  if (!sessionId) return <BookingLauncher />;

  return (
    <BookingShell>
      <Routes>
        <Route path="/" element={<Navigate to="/home" replace />} />
        <Route path="/home" element={<Home />} />
        <Route path="/search" element={<SearchResults />} />
        <Route path="/property/:id" element={<PropertyDetail />} />
        <Route path="/book/:propertyId/:roomId" element={<BookingForm />} />
        <Route path="/confirmation/:reservationId" element={<BookingConfirmation />} />
        <Route path="/trips" element={<MyTrips />} />
        <Route path="/trips/:id" element={<ReservationDetail />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/saved" element={<SavedLists />} />
        <Route path="/messages" element={<Messages />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/reviews" element={<Reviews />} />
        <Route path="/deals" element={<Deals />} />
        <Route path="*" element={<Navigate to="/home" replace />} />
      </Routes>
    </BookingShell>
  );
}
