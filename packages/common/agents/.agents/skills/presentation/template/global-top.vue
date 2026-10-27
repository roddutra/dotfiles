<!-- Logo and slide number on content slides. Drawn above the slide, because global-bottom.vue sits behind its opaque background. -->
<template>
  <footer
    v-if="!['cover', 'section', 'end', 'full', 'image'].includes($nav.currentLayout)"
    class="brand-footer"
    :class="`brand-footer--${$nav.currentLayout}`"
  >
    <img src="/brand/logo.svg" alt="" class="brand-footer__logo">
    <span>{{ $nav.currentPage }} / {{ $nav.total }}</span>
  </footer>
</template>

<style scoped>
.brand-footer {
  position: absolute;
  inset: auto 3.5rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font: 500 0.8rem/1 var(--brand-font-body);
  color: var(--brand-muted);
  font-variant-numeric: tabular-nums;
}
.brand-footer__logo { height: 1.25rem; }
/* Keep the footer on the text half of image layouts, off the picture. */
.brand-footer--image-right { right: calc(50% + 3.5rem); }
.brand-footer--image-left { left: calc(50% + 3.5rem); }
</style>
