<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import LanguageToggle from './components/LanguageToggle.vue'
import { useAuth } from './composables/useAuth'
import logoSrc from './assets/logo.png'

const router = useRouter()
const route = useRoute()
const menuOpen = ref(false)
const { authEnabled, isAuthenticated, user, logout: doLogout, tryRestoreSession } = useAuth()

const appVersion = __APP_VERSION__

onMounted(() => { tryRestoreSession() })

function goHome() {
  router.push('/admin/review')
  menuOpen.value = false
}

function closeMenu() {
  menuOpen.value = false
}

function navigate(path: string) {
  router.push(path)
  menuOpen.value = false
}

function isAdmin(): boolean {
  return route.path.startsWith('/admin')
}

function handleLogout() {
  doLogout()
  menuOpen.value = false
  router.push('/login')
}
</script>

<template>
  <div id="app-root" @click="closeMenu">
    <header class="app-header">
      <div class="app-header__left">
        <img :src="logoSrc" alt="Logo" class="app-header__logo" />
        <a class="app-header__title" href="#" @click.prevent="goHome">
          Greenfield Foundation Community Gift Program
        </a>
      </div>
      <div class="app-header__right">
        <span class="app-header__version">{{ appVersion }}</span>
        <LanguageToggle />
        <template v-if="authEnabled && !isAuthenticated">
          <a class="app-header__login" href="#" @click.prevent="navigate('/login')">Staff Login</a>
        </template>
        <template v-if="authEnabled && isAuthenticated">
          <span class="app-header__user">{{ user?.name }}</span>
        </template>
        <div v-if="isAdmin()" class="app-header__settings" @click.stop>
          <button
            class="app-header__gear"
            :class="{ 'app-header__gear--open': menuOpen }"
            aria-label="Settings"
            @click="menuOpen = !menuOpen"
          >⚙</button>
          <div v-if="menuOpen" class="app-header__dropdown">
            <a class="app-header__dropdown-item" href="#" @click.prevent="navigate('/admin/users')">Users</a>
            <a class="app-header__dropdown-item" href="#" @click.prevent="navigate('/admin/audit')">Audit Log</a>
            <div v-if="authEnabled" class="app-header__dropdown-divider"></div>
            <a v-if="authEnabled" class="app-header__dropdown-item app-header__dropdown-item--logout" href="#" @click.prevent="handleLogout">Sign Out</a>
          </div>
        </div>
      </div>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style>
html, body, #app { margin: 0; padding: 0; background: #f5f0e8; min-height: 100vh; }
</style>

<style scoped>
#app-root { background: #f5f0e8; min-height: 100vh; }
.app-header { background: #e8860c; color: #fff; padding: 10px 20px; font-size: 0.9rem; display: flex; align-items: center; justify-content: space-between; }
.app-header__left { display: flex; align-items: center; gap: 10px; }
.app-header__logo { height: 32px; width: auto; flex-shrink: 0; object-fit: contain; }
.app-header__title { font-weight: 600; color: #fff; text-decoration: none; cursor: pointer; }
.app-header__title:hover { color: #e0e0e0; }
.app-header__right { display: flex; align-items: center; gap: 0.75rem; }
.app-header__version { font-size: 0.65rem; color: rgba(255,255,255,0.4); font-family: monospace; }
.app-header__settings { position: relative; }
.app-header__gear { background: none; border: none; color: rgba(255,255,255,0.7); font-size: 1.3rem; padding: 4px 8px; cursor: pointer; transition: color 0.15s; }
.app-header__gear:hover, .app-header__gear--open { color: #fff; }
.app-header__dropdown { position: absolute; top: 100%; right: 0; background: #faf7f2; border: 1px solid #e6ddd0; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); min-width: 220px; z-index: 100; overflow: hidden; margin-top: 8px; }
.app-header__dropdown-item { display: block; padding: 0.6rem 1rem; color: #333; text-decoration: none; font-size: 0.85rem; transition: background 0.1s; }
.app-header__dropdown-item:hover { background: #f0ebe3; }
.app-header__dropdown-divider { height: 1px; background: #ede6db; margin: 0.25rem 0; }
.app-header__dropdown-item--logout { color: #991b1b; }
.app-header__login { color: #fff; text-decoration: none; font-size: 0.85rem; font-weight: 600; padding: 0.3rem 0.75rem; border: 1px solid rgba(255,255,255,0.4); border-radius: 5px; transition: background 0.15s; }
.app-header__login:hover { background: rgba(255,255,255,0.15); }
.app-header__user { color: rgba(255,255,255,0.85); font-size: 0.8rem; }
</style>
