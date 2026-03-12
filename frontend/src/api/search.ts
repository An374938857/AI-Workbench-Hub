import request from './request'

export interface SearchParams {
  q: string
  page?: number
  page_size?: number
  skill_id?: number
  skill_name?: string
  tags?: string[]
  date_start?: string
  date_end?: string
}

export interface SearchResult {
  conversation_id: number
  title: string
  skill_name?: string
  active_skills?: Array<{ id: number; name: string }>
  tags?: Array<{ id: number; name: string; color: string }>
  updated_at?: string
  highlights: {
    title?: string[]
    'messages.content'?: string[]
  }
  score: number
}

export interface SearchResponse {
  total: number
  results: SearchResult[]
  page: number
  page_size: number
}

export const searchConversations = (params: SearchParams) => {
  return request.get<SearchResponse>('/search/conversations', { params })
}

export const getSearchHistory = (): string[] => {
  const history = localStorage.getItem('search_history')
  return history ? JSON.parse(history) : []
}

export const saveSearchHistory = (query: string) => {
  const history = getSearchHistory()
  const newHistory = [query, ...history.filter(q => q !== query)].slice(0, 10)
  localStorage.setItem('search_history', JSON.stringify(newHistory))
}

export const clearSearchHistory = () => {
  localStorage.removeItem('search_history')
}
