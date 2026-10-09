import { MessagesSquare, UserRound, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/app/chat", label: "AI Assistant", icon: MessagesSquare },
  { to: "/app/profile", label: "Profile", icon: UserRound },
];
