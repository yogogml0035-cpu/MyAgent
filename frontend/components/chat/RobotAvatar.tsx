function BotIcon() {
  return (
    <svg
      aria-hidden="true"
      className="robotAvatarIcon"
      fill="none"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
      width="20"
    >
      <path d="M12 8V4H8" />
      <rect height="12" rx="2" width="16" x="4" y="8" />
      <path d="M2 14h2" />
      <path d="M20 14h2" />
      <path d="M15 13v2" />
      <path d="M9 13v2" />
    </svg>
  );
}

export function RobotAvatar() {
  return (
    <div className="agentMarker" aria-hidden="true">
      <BotIcon />
    </div>
  );
}
