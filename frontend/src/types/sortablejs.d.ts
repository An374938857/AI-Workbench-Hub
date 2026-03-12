declare module 'sortablejs' {
  export interface SortableEvent {
    oldIndex?: number
    newIndex?: number
  }

  export interface SortableOptions {
    animation?: number
    handle?: string
    ghostClass?: string
    chosenClass?: string
    dragClass?: string
    onEnd?: (event: SortableEvent) => void | Promise<void>
  }

  export default class Sortable {
    static create(element: HTMLElement, options?: SortableOptions): Sortable
    destroy(): void
  }
}
