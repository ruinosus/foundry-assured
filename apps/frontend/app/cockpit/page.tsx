import { redirect } from "next/navigation";

// The Cockpit expert moved into the unified Assurance Console (/d/<domain>). It's TEMP-hidden
// (KB not provisioned in this env — see lib/domains.ts), so send the legacy path home instead of
// to a "domain not found" screen. Restore the /d/cockpit redirect when the domain is re-enabled.
export default function CockpitRedirect() {
  redirect("/");
}
