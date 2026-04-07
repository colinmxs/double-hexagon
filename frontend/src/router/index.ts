import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationNormalized } from 'vue-router'
import { useAuth } from '../composables/useAuth'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiredRole?: string
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/apply',
    },
    {
      path: '/apply',
      name: 'apply',
      component: () => import('../views/ApplyView.vue'),
    },
    {
      path: '/upload',
      name: 'upload',
      component: () => import('../views/UploadView.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/admin',
      component: () => import('../views/AdminLayout.vue'),
      meta: { requiresAuth: true, requiredRole: 'reporter' },
      children: [
        {
          path: '',
          redirect: '/admin/review',
        },
        {
          path: 'review',
          name: 'admin-review',
          component: () => import('../views/ReviewListView.vue'),
          meta: { requiresAuth: true, requiredRole: 'admin' },
        },
        {
          path: 'review/:applicationId',
          name: 'admin-review-detail',
          component: () => import('../views/ReviewDetailView.vue'),
          meta: { requiresAuth: true, requiredRole: 'admin' },
        },
        {
          path: 'users',
          name: 'admin-users',
          component: () => import('../views/AccessManagementView.vue'),
          meta: { requiresAuth: true, requiredRole: 'admin' },
        },
        {
          path: 'audit',
          name: 'admin-audit',
          component: () => import('../views/AuditLogView.vue'),
          meta: { requiresAuth: true, requiredRole: 'admin' },
        },
      ],
    },
  ],
})

router.beforeEach((to: RouteLocationNormalized) => {
  const { authEnabled, isAuthenticated, hasRole } = useAuth()

  if (!authEnabled) return true

  if (to.meta.requiresAuth && !isAuthenticated.value) {
    return { path: '/login' }
  }

  if (to.meta.requiredRole && !hasRole(to.meta.requiredRole)) {
    return { path: '/login' }
  }

  return true
})

export default router
