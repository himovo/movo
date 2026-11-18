<script setup lang="ts">
import type { VisualBlock } from './assistantVisualBlocks'
const props = defineProps<{ block: VisualBlock }>()
</script>

<template>
  <section class="visual-block" :class="[`visual-block--${props.block.kind}`, { 'visual-block--four-metrics': block.kind === 'metrics' && block.items.length === 4 }]">
    <h3 v-if="block.title" class="visual-block__title">{{ block.title }}</h3>
    <div class="visual-block__items">
      <div v-for="(item, index) in block.items" :key="index" class="visual-block__item" :class="[`tone-${item.tone || 'blue'}`, item.checked === true ? 'is-checked' : '']">
        <span v-if="block.kind === 'checklist'" class="visual-block__check" aria-hidden="true"><svg v-if="item.checked" viewBox="0 0 20 20" fill="none"><path d="m4 10 4 4 8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg></span>
        <span v-else-if="block.kind === 'insights'" class="visual-block__index" aria-hidden="true">{{ index + 1 }}</span>
        <div class="visual-block__content">
          <span class="visual-block__label">{{ item.label }}</span>
          <strong v-if="item.value" class="visual-block__value">{{ item.value }}</strong>
          <p v-if="item.detail" class="visual-block__detail">{{ item.detail }}</p>
        </div>
      </div>
    </div>
    <p v-if="block.note" class="visual-block__note">{{ block.note }}</p>
  </section>
</template>

<style scoped>
.visual-block {
  margin:18px 0;
  padding:18px;
  border:1px solid #e2e8f0;
  border-radius:16px;
  background:#fff;
  color:#172033;
  box-shadow:0 2px 8px #17203308;
  max-width:100%;
  overflow:hidden}
.visual-block__title {
  margin:0 0 14px;
  font-size:16px;
  line-height:1.45;
  font-weight:700;
  letter-spacing:-.01em}
.visual-block__items {
  display:grid;
  gap:10px}
.visual-block__item {
  min-width:0;
  padding:14px 16px;
  border-radius:12px;
  background:#eff4ff;
  display:flex;
  align-items:flex-start;
  gap:12px}
.visual-block__content {
  min-width:0}
.visual-block__label {
  display:block;
  font-size:14px;
  line-height:1.5;
  font-weight:650}
.visual-block__value {
  display:block;
  margin-top:6px;
  font-size:26px;
  line-height:1.2;
  letter-spacing:-.03em}
.visual-block__detail {
  margin:6px 0 0;
  color:#596579;
  font-size:13px;
  line-height:1.6}
.visual-block__note {
  margin:12px 0 0;
  color:#64748b;
  font-size:12px;
  line-height:1.55}
.tone-green {
  background:#eef8f2}
.tone-amber {
  background:#fff6e9}
.tone-purple {
  background:#f5f0ff}
.visual-block--metrics .visual-block__items {
  grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr))}
.visual-block--four-metrics .visual-block__items {
  grid-template-columns:repeat(2,minmax(0,1fr))}
.visual-block--priorities .visual-block__item,.visual-block--timeline .visual-block__item {
  background:transparent;
  border-radius:0;
  padding:12px 0;
  border-bottom:1px solid #e9edf2}
.visual-block--priorities .visual-block__item:last-child,.visual-block--timeline .visual-block__item:last-child {
  border-bottom:0}
.visual-block--priorities .visual-block__label,.visual-block--timeline .visual-block__label {
  display:inline-flex;
  padding:3px 9px;
  border-radius:999px;
  background:#eaf1ff;
  color:#2456aa;
  font-size:11px}
.visual-block--priorities .tone-green .visual-block__label,
.visual-block--timeline .tone-green .visual-block__label {
  background:#e4f6eb;
  color:#197448}
.visual-block--priorities .tone-amber .visual-block__label,
.visual-block--timeline .tone-amber .visual-block__label {
  background:#fff0d8;
  color:#985c13}
.visual-block--priorities .tone-purple .visual-block__label,
.visual-block--timeline .tone-purple .visual-block__label {
  background:#efe6ff;
  color:#6842a4}
.visual-block--priorities .visual-block__value,.visual-block--timeline .visual-block__value {
  font-size:15px;
  margin-top:7px}
.visual-block--flow .visual-block__items {
  grid-template-columns:1fr;
  row-gap:26px}
.visual-block--flow .visual-block__item {
  text-align:center;
  justify-content:center;
  background:#eaf0ff;
  position:relative}
.visual-block--flow .visual-block__item::after {
  content:'\2193';
  position:absolute;
  left:50%;
  bottom:-23px;
  transform:translateX(-50%);
  color:#64748b;
  line-height:20px}
.visual-block--flow .visual-block__item:last-child::after {
  content:none}
.visual-block--insights .visual-block__item {
  background:transparent;
  border-bottom:1px solid #e9edf2;
  border-radius:0;
  padding:12px 0}
.visual-block--insights .visual-block__item:last-child {
  border-bottom:0}
.visual-block__index {
  display:grid;
  place-items:center;
  flex:none;
  width:31px;
  height:31px;
  border-radius:9px;
  background:#e8f0ff;
  color:#2456aa;
  font-size:13px;
  font-weight:700}
.visual-block--checklist .visual-block__item {
  background:transparent;
  padding:3px 0}
.visual-block__check {
  flex:none;
  width:20px;
  height:20px;
  border:1.5px solid #aab4c3;
  border-radius:50%;
  text-align:center;
  line-height:17px;
  color:#16804b}
.visual-block__check svg {
  width:100%;
  height:100%}
.is-checked .visual-block__check {
  border-color:#16804b;
  background:#e7f7ee}
@media(max-width:600px) {
  .visual-block {
    padding:14px}
  .visual-block__item {
    padding:12px}
  .visual-block__value {
    font-size:21px}
  .visual-block--four-metrics .visual-block__items {
    grid-template-columns:1fr}
}
:global(html.theme-dark .visual-block) {
  background:#172033;
  border-color:#34445c;
  color:#e2eaf5}
:global(html.theme-dark .visual-block__item) {
  color:#e2eaf5}
:global(html.theme-dark .visual-block__item.tone-blue),
:global(html.theme-dark .visual-block--flow .visual-block__item) {
  background:#20314f}
:global(html.theme-dark .visual-block__item.tone-green) {
  background:#1d3a32}
:global(html.theme-dark .visual-block__item.tone-amber) {
  background:#423521}
:global(html.theme-dark .visual-block__item.tone-purple) {
  background:#342b49}
:global(html.theme-dark .visual-block--priorities .visual-block__item),
:global(html.theme-dark .visual-block--timeline .visual-block__item),
:global(html.theme-dark .visual-block--insights .visual-block__item),
:global(html.theme-dark .visual-block--checklist .visual-block__item) {
  background:transparent;
  border-color:#34445c}
:global(html.theme-dark .visual-block__detail),:global(html.theme-dark .visual-block__note) {
  color:#a4b3c7}
</style>
