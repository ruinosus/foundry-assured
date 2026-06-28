import { redirect } from "next/navigation";

// The Cockpit expert moved into the unified Assurance Console (/d/<domain>). Keep the
// old path working.
export default function CockpitRedirect() {
  redirect("/d/cockpit");
}
