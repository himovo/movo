import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue';

/** Account for the responsive admin header instead of assuming a fixed height. */
export function useAuditViewport(container: Ref<HTMLElement | null>) {
  const height = ref<number>();
  let observer: ResizeObserver | undefined;
  function measure() {
    if (container.value) height.value = Math.max(0, window.innerHeight - container.value.getBoundingClientRect().top - 16);
  }
  onMounted(() => {
    measure();
    window.addEventListener('resize', measure);
    observer = new ResizeObserver(measure);
    const header = document.querySelector('.shell-header');
    if (header) observer.observe(header);
  });
  onBeforeUnmount(() => { window.removeEventListener('resize', measure); observer?.disconnect(); });
  return height;
}
