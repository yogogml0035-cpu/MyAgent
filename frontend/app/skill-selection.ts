export type SkillOption = {
  name: string;
  description: string;
};

export type ActiveSkillSlashToken = {
  start: number;
  end: number;
  query: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function normalizeSkillQuery(value: string) {
  return value.trim().replace(/^\/+/, "").toLowerCase();
}

function isSlashTokenBoundary(value: string, slashIndex: number) {
  if (slashIndex === 0) {
    return true;
  }
  return /\s/.test(value[slashIndex - 1]);
}

function isSkillQueryChar(value: string) {
  return /^[A-Za-z0-9_-]$/.test(value);
}

export function normalizeSkillOption(value: unknown): SkillOption | null {
  const record = isRecord(value) ? value : {};
  const name = readString(record.name).trim();

  if (!name) {
    return null;
  }

  return {
    name,
    description: readString(record.description).trim(),
  };
}

export function normalizeSkillOptions(value: unknown): SkillOption[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map(normalizeSkillOption)
    .filter((option): option is SkillOption => option !== null);
}

export function filterSkillOptions(options: readonly SkillOption[], query: string): SkillOption[] {
  const normalizedQuery = normalizeSkillQuery(query);
  if (!normalizedQuery) {
    return [...options];
  }

  return options.filter((option) => {
    const marker = `${option.name} ${option.description}`.toLowerCase();
    return marker.includes(normalizedQuery);
  });
}

export function findActiveSkillSlashToken(
  value: string,
  cursorIndex = value.length,
): ActiveSkillSlashToken | null {
  const cursor = Math.max(0, Math.min(cursorIndex, value.length));
  if (cursor === 0) {
    return null;
  }

  const slashIndex = value.lastIndexOf("/", cursor - 1);
  if (slashIndex < 0 || !isSlashTokenBoundary(value, slashIndex)) {
    return null;
  }

  let tokenEnd = slashIndex + 1;
  while (tokenEnd < value.length && isSkillQueryChar(value[tokenEnd])) {
    tokenEnd += 1;
  }

  if (cursor > tokenEnd) {
    return null;
  }

  const cursorQuery = value.slice(slashIndex + 1, cursor);
  if ([...cursorQuery].some((character) => !isSkillQueryChar(character))) {
    return null;
  }

  return {
    start: slashIndex,
    end: tokenEnd,
    query: cursorQuery,
  };
}

export function replaceActiveSkillSlashToken(
  value: string,
  token: ActiveSkillSlashToken | null,
  replacement = "",
): { value: string; cursor: number } {
  if (!token) {
    return { value, cursor: value.length };
  }

  const before = value.slice(0, token.start);
  const after = value.slice(token.end);

  if (!replacement) {
    const normalizedAfter = before.endsWith(" ") ? after.replace(/^[ \t]+/, "") : after;
    const nextValue = before ? `${before}${normalizedAfter}` : normalizedAfter.replace(/^[ \t]+/, "");
    return { value: nextValue, cursor: before.length };
  }

  const needsGap = before && after && !/\s$/.test(before) && !/^\s/.test(after);
  const inserted = needsGap ? `${replacement} ` : replacement;
  return {
    value: `${before}${inserted}${after}`,
    cursor: before.length + inserted.length,
  };
}
