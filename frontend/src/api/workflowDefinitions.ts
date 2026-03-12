import request from './request'

export function listPublishedWorkflowDefinitions(scope: 'PROJECT' | 'REQUIREMENT') {
  return request.get('/v1/workflow-definitions', { params: { scope } })
}
