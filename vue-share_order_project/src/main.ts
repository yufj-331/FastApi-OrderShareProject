import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

import Person from './components/person.vue'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 将 Person 组件注册到全局
app.component('Person', App)
app.mount('#app')
