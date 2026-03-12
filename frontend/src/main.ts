import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import '@fontsource-variable/noto-sans'
import '@fontsource-variable/noto-sans-sc'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/themes.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)
const pinia = createPinia()

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')

// 入场动画播放完后移除 animation 属性，防止主题切换时重播
document.addEventListener('animationend', (e) => {
  const el = e.target as HTMLElement
  if (el?.style) el.style.animation = 'none'
})
