import { Link } from "react-router-dom";
import { Empty } from "../components/ui";

export default function NotFound() {
  return (
    <div className="panel">
      <Empty title="Cette page n'existe pas.">
        <p className="mt"><Link to="/">Revenir à l'accueil</Link></p>
      </Empty>
    </div>
  );
}
