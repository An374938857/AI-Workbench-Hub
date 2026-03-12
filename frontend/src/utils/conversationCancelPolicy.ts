export function shouldRequestRemoteCancelOnRouteSwitch(isStreamOwnedByView: boolean): boolean {
  void isStreamOwnedByView
  // 路由切换不应触发服务端取消，避免“未手动停止却被取消”。
  return false
}
