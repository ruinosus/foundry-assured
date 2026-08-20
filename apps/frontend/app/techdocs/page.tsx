import { redirect } from "next/navigation";

// The TechDocs expert moved into the unified Assurance Console (/d/<domain>).
export default function TechDocsRedirect() {
  redirect("/d/techdocs");
}
