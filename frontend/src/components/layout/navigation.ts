import { FileUp, ImageUp, LayoutDashboard, MessagesSquare, UserRound, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Page title and breadcrumb line shown in the top bar. */
  title: string;
  crumb: string;
  /**
   * The permission the server requires for this page. The entry is shown to every signed-in account;
   * accounts without it see a lock and a locked page (the server still enforces the permission).
   */
  requires?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard, title: "Dashboard", crumb: "Overview of what you can access" },
  { to: "/app/chat", label: "Assistant", icon: MessagesSquare, title: "Assistant", crumb: "Secure knowledge workspace" },
  {
    to: "/app/upload",
    label: "Upload",
    icon: FileUp,
    title: "Upload Documents",
    crumb: "Add PDFs to the knowledge base",
    requires: "documents:write",
  },
  {
    to: "/app/upload-image",
    label: "Upload images",
    icon: ImageUp,
    title: "Upload Images",
    crumb: "Read text from scanned images (OCR)",
    requires: "documents:write",
  },
  { to: "/app/profile", label: "Profile", icon: UserRound, title: "Profile & session", crumb: "Account and access" },
];

/** The nav entry for the current URL; unknown app paths fall back to the assistant. */
export function navItemForPath(pathname: string): NavItem {
  return NAV_ITEMS.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`)) ?? NAV_ITEMS[0];
}
