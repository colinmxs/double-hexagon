<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  imageUrl: string
  keywords: string[]
  altText?: string
}>()

const { t } = useI18n()
</script>

<template>
  <figure class="drawing-viewer">
    <img
      :src="imageUrl"
      :alt="altText ?? t('drawing.noKeywords')"
      class="drawing-viewer__image"
    />
    <figcaption v-if="keywords.length" class="drawing-viewer__keywords">
      <span
        v-for="keyword in keywords"
        :key="keyword"
        class="drawing-viewer__chip"
      >
        {{ keyword }}
      </span>
    </figcaption>
  </figure>
</template>

<style scoped>
.drawing-viewer {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.drawing-viewer__image {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
}

.drawing-viewer__keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.drawing-viewer__chip {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 16px;
  background-color: #e8f0fe;
  color: #1a56db;
  font-size: 0.8rem;
  font-weight: 500;
}
</style>
