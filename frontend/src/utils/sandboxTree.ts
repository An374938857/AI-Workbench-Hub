export interface SandboxTreeNodeLike<T = unknown> {
  kind: string
  children?: T[]
}

function pruneNode<T extends SandboxTreeNodeLike<T>>(node: T): T | null {
  const children = (node.children || [])
    .map((child) => pruneNode(child))
    .filter((child): child is T => Boolean(child))

  if (node.kind === 'file' || node.kind === 'asset') {
    return {
      ...node,
      children,
    }
  }

  if (children.length === 0) return null

  return {
    ...node,
    children,
  }
}

export function pruneEmptySandboxTree<T extends SandboxTreeNodeLike<T>>(nodes: T[]): T[] {
  return nodes
    .map((node) => pruneNode(node))
    .filter((node): node is T => Boolean(node))
}

export function collectSandboxDirectoryCount<T extends SandboxTreeNodeLike<T>>(nodes: T[]): number {
  let count = 0
  const visit = (items: T[]) => {
    for (const item of items) {
      if ((item.children || []).length > 0) count += 1
      if (item.children?.length) visit(item.children)
    }
  }
  visit(nodes)
  return count
}

export function collectSandboxFileCount<T extends SandboxTreeNodeLike<T>>(nodes: T[]): number {
  let count = 0
  const visit = (items: T[]) => {
    for (const item of items) {
      if (item.kind === 'file' || item.kind === 'asset') count += 1
      if (item.children?.length) visit(item.children)
    }
  }
  visit(nodes)
  return count
}

export function collectSandboxDirectoryKeys<T extends SandboxTreeNodeLike<T> & { key: string }>(nodes: T[]): string[] {
  const keys: string[] = []
  const visit = (items: T[]) => {
    for (const item of items) {
      if ((item.children || []).length > 0) {
        keys.push(item.key)
        visit(item.children || [])
      }
    }
  }
  visit(nodes)
  return keys
}
