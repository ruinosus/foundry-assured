"use client";

// Client-only: the app uses MSAL + the v2 useAgent subscription, neither of
// which can run during SSR.
import dynamic from "next/dynamic";

const HelpdeskApp = dynamic(() => import("./HelpdeskApp"), { ssr: false });

export default function Page() {
  return <HelpdeskApp />;
}
