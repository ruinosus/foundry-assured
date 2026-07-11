import { redirect } from "next/navigation";

// The concierge moved into the unified Assurance Console (/d/<domain>). Keep the old
// path working.
export default function ChatRedirect() {
  redirect("/d/helpdesk");
}
