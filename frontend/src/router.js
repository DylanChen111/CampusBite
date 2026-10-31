import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Explore from './views/Explore.vue'
import Detail from './views/Detail.vue'
import Recommend from './views/Recommend.vue'
import NotFound from './views/NotFound.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/explore', component: Explore },
    { path: '/dishes/:id', component: Detail },
    { path: '/recommend', component: Recommend },
    { path: '/:pathMatch(.*)*', component: NotFound },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
