export type ConversationFileTagType = "primary" | "success" | "warning" | "info" | "danger";

export interface ConversationFileTreeItem {
  key: string | number;
  label: string;
  path: string;
  treePath?: string;
  displayPath?: string;
  fileType?: string | null;
  fileSize?: number | null;
  updatedAt?: string | null;
  sourceLabel?: string | null;
  sourceTagType?: ConversationFileTagType;
  summary?: string | null;
  searchableText?: string;
  raw?: unknown;
}

export interface ConversationFileTreeNode {
  key: string;
  label: string;
  path: string;
  type: "directory" | "file";
  searchableText: string;
  children?: ConversationFileTreeNode[];
  item?: ConversationFileTreeItem;
}

export function formatConversationFileSize(bytes?: number | null): string {
  if (typeof bytes !== "number" || Number.isNaN(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function formatConversationFileTime(value?: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN");
}

export function buildConversationFileTree(
  items: ConversationFileTreeItem[],
): ConversationFileTreeNode[] {
  const root: ConversationFileTreeNode[] = [];
  const directoryMap = new Map<string, ConversationFileTreeNode>();

  for (const item of items) {
    const rawPath = item.treePath || item.path || item.label;
    const displayPath = item.displayPath || item.path || item.label;
    const parts = rawPath.split("/").filter(Boolean);
    const displayParts = displayPath.split("/").filter(Boolean);
    let currentChildren = root;
    let currentPath = "";

    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLeaf = index === parts.length - 1;
      const displayPart = displayParts[index] || part;

      if (isLeaf) {
        currentChildren.push({
          key: String(item.key),
          label: item.label || part,
          path: rawPath,
          type: "file",
          searchableText: normalizeSearchText(
            `${item.label} ${rawPath} ${item.searchableText || ""} ${item.summary || ""}`,
          ),
          item,
        });
        return;
      }

      let existing = directoryMap.get(currentPath);
      if (!existing) {
        existing = {
          key: currentPath,
          label: displayPart,
          path: currentPath,
          type: "directory",
          searchableText: normalizeSearchText(currentPath),
          children: [],
        };
        directoryMap.set(currentPath, existing);
        currentChildren.push(existing);
      }
      currentChildren = existing.children || [];
    });
  }

  sortConversationFileTree(root);
  return root;
}

export function collectConversationDirectoryKeys(nodes: ConversationFileTreeNode[]): string[] {
  const keys: string[] = [];
  const visit = (items: ConversationFileTreeNode[]) => {
    items.forEach((item) => {
      if (item.type === "directory") {
        keys.push(item.key);
        if (item.children?.length) visit(item.children);
      }
    });
  };
  visit(nodes);
  return keys;
}

export function countConversationDirectories(nodes: ConversationFileTreeNode[]): number {
  return collectConversationDirectoryKeys(nodes).length;
}

export function countConversationFiles(nodes: ConversationFileTreeNode[]): number {
  let count = 0;
  const visit = (items: ConversationFileTreeNode[]) => {
    items.forEach((item) => {
      if (item.type === "file") {
        count += 1;
        return;
      }
      if (item.children?.length) visit(item.children);
    });
  };
  visit(nodes);
  return count;
}

export function filterConversationFileTree(
  nodes: ConversationFileTreeNode[],
  keyword: string,
): ConversationFileTreeNode[] {
  const normalized = normalizeSearchText(keyword);
  if (!normalized) return nodes;

  const filterNode = (node: ConversationFileTreeNode): ConversationFileTreeNode | null => {
    const children = (node.children || [])
      .map((child) => filterNode(child))
      .filter((child): child is ConversationFileTreeNode => Boolean(child));

    const matched =
      fuzzyMatch(normalizeSearchText(node.label), normalized) ||
      node.searchableText.includes(normalized);

    if (matched || children.length > 0) {
      return {
        ...node,
        children,
      };
    }
    return null;
  };

  return nodes
    .map((node) => filterNode(node))
    .filter((node): node is ConversationFileTreeNode => Boolean(node));
}

function sortConversationFileTree(nodes: ConversationFileTreeNode[]) {
  nodes.sort((left, right) => {
    if (left.type !== right.type) return left.type === "directory" ? -1 : 1;
    return left.label.localeCompare(right.label, "zh-CN");
  });
  nodes.forEach((node) => {
    if (node.children?.length) sortConversationFileTree(node.children);
  });
}

function normalizeSearchText(value: string): string {
  return value.trim().toLowerCase();
}

function fuzzyMatch(source: string, query: string): boolean {
  if (!query) return true;
  if (source.includes(query)) return true;

  let sourceIndex = 0;
  let queryIndex = 0;

  while (sourceIndex < source.length && queryIndex < query.length) {
    if (source[sourceIndex] === query[queryIndex]) {
      queryIndex += 1;
    }
    sourceIndex += 1;
  }

  return queryIndex === query.length;
}
