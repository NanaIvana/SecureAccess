// Routage : une seule page de connexion, puis l'espace client (/espace) ou la console (/console) selon le rôle.
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { Loader } from "./components/ui";
import { useAuth } from "./context/AuthContext";
import { homeFor } from "./lib/space";
import AlertDetail from "./pages/AlertDetail";
import Alerts from "./pages/Alerts";
import Audit from "./pages/Audit";
import Dashboard from "./pages/Dashboard";
import Detection from "./pages/Detection";
import EspaceHome from "./pages/EspaceHome";
import EventDetail from "./pages/EventDetail";
import Events from "./pages/Events";
import Login from "./pages/Login";
import MyAccount from "./pages/MyAccount";
import MyEvents from "./pages/MyEvents";
import NotFound from "./pages/NotFound";
import Notifications from "./pages/Notifications";
import { ForgotPassword, ResetPassword } from "./pages/PasswordReset";
import Protection from "./pages/Protection";
import Report from "./pages/Report";
import Simulator from "./pages/Simulator";
import UserDetail from "./pages/UserDetail";
import Users from "./pages/Users";

/** Garde de route : sans session, retour à /connexion ; avec le mauvais rôle, retour à son espace. */
function Guard({ space, admin, children }) {
  const { user, ready, isAdmin } = useAuth();
  const location = useLocation();
  if (!ready) return <Loader />;
  if (!user) return <Navigate to="/connexion" state={{ from: location }} replace />;
  const isClient = user.role === "UTILISATEUR";
  if (space === "console" && isClient) return <Navigate to="/espace" replace />;
  if (space === "espace" && !isClient) return <Navigate to="/console" replace />;
  if (admin && !isAdmin) return <Navigate to="/console" replace />;
  return children;
}

function Home() {
  const { user, ready } = useAuth();
  if (!ready) return <Loader />;
  return <Navigate to={homeFor(user)} replace />;
}

/** Lien des e-mails (/notifications?id=…) : renvoie vers les notifications de son espace. */
function NotificationsRedirect() {
  const { user, ready } = useAuth();
  const { search } = useLocation();
  if (!ready) return <Loader />;
  if (!user) return <Navigate to="/connexion" replace />;
  return <Navigate to={`${homeFor(user)}/notifications${search}`} replace />;
}

const A = ({ children }) => <Guard space="console" admin>{children}</Guard>;

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/connexion" element={<Login />} />
      <Route path="/mot-de-passe-oublie" element={<ForgotPassword />} />
      <Route path="/reinitialiser" element={<ResetPassword />} />

      <Route path="/espace" element={<Guard space="espace"><Layout space="espace" /></Guard>}>
        <Route index element={<EspaceHome />} />
        <Route path="connexions-perso" element={<MyEvents />} />
        <Route path="connexions/:id" element={<EventDetail />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="compte" element={<MyAccount />} />
        <Route path="*" element={<NotFound />} />
      </Route>

      <Route path="/console" element={<Guard space="console"><Layout space="console" /></Guard>}>
        <Route index element={<Dashboard />} />
        <Route path="alertes" element={<A><Alerts /></A>} />
        <Route path="alertes/:id" element={<A><AlertDetail /></A>} />
        <Route path="connexions" element={<A><Events /></A>} />
        <Route path="connexions/:id" element={<EventDetail />} />
        <Route path="utilisateurs" element={<A><Users /></A>} />
        <Route path="utilisateurs/:id" element={<A><UserDetail /></A>} />
        <Route path="rapport" element={<Report />} />
        <Route path="detection" element={<A><Detection /></A>} />
        <Route path="simulateur" element={<A><Simulator /></A>} />
        <Route path="protection" element={<Protection />} />
        <Route path="audit" element={<A><Audit /></A>} />
        <Route path="connexions-perso" element={<MyEvents />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="compte" element={<MyAccount />} />
        <Route path="*" element={<NotFound />} />
      </Route>

      {/* Anciennes adresses */}
      <Route path="/tableau-de-bord" element={<Navigate to="/console" replace />} />
      <Route path="/mes-connexions" element={<Navigate to="/espace/connexions-perso" replace />} />
      <Route path="/notifications" element={<NotificationsRedirect />} />
      <Route path="*" element={<Home />} />
    </Routes>
  );
}
