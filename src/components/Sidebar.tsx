import {
  BarChart3,
  Camera,
  ChevronLeft,
  ChevronRight,
  FileText,
  Gauge,
  Search,
  Settings,
} from "lucide-react";

export type ViewKey =
  | "live"
  | "inspector"
  | "trends"
  | "explanation"
  | "configuration";

const items: Array<{ key: ViewKey; label: string; icon: typeof Gauge }> = [
  { key: "live", label: "Live Monitor", icon: Gauge },
  { key: "inspector", label: "Signal Inspector", icon: Search },
  { key: "trends", label: "Risk Trends", icon: BarChart3 },
  { key: "explanation", label: "Explanation", icon: FileText },
  { key: "configuration", label: "Configuration", icon: Settings },
];

interface SidebarProps {
  activeView: ViewKey;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onViewChange: (view: ViewKey) => void;
}

export function Sidebar({
  activeView,
  collapsed,
  onToggleCollapsed,
  onViewChange,
}: SidebarProps) {
  const ToggleIcon = collapsed ? ChevronRight : ChevronLeft;

  return (
    <aside className={`sidebar ${collapsed ? "sidebar--collapsed" : ""}`}>
      <div className="sidebar-header">
        <div className="brand-block">
          <Camera size={24} />
          <div className="brand-copy">
            <strong>Driver Risk</strong>
            <span>MVP Dashboard</span>
          </div>
        </div>
        <button
          type="button"
          className="sidebar-toggle"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          onClick={onToggleCollapsed}
        >
          <ToggleIcon size={18} />
        </button>
      </div>

      <nav className="nav-list" aria-label="Dashboard views">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              type="button"
              key={item.key}
              className={activeView === item.key ? "is-active" : undefined}
              aria-label={item.label}
              title={collapsed ? item.label : undefined}
              onClick={() => onViewChange(item.key)}
            >
              <Icon size={18} />
              <span className="nav-label">{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
