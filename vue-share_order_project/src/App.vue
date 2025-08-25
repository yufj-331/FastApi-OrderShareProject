<template>
  <h1>欢迎欢迎！热烈欢迎</h1>
  <Person />
</template>

<script setup lang="ts">
import Person from './components/person.vue'
</script>

<style>
/* 1. 页面背景与字体样式 */
#app {
  background-color: #f0f0f0;
  /* 背景色 */
  font-family: 'Arial', sans-serif;
  /* 字体 */
  padding: 20px;
  /* 页面内边距 */
  text-align: center;
  /* 居中对齐文本 */
  min-height: 100vh;
  /* 最小高度 100vh，确保页面始终填满屏幕 */
}

/* 2. h1 样式 */
h1 {
  color: #4CAF50;
  /* 绿色 */
  font-size: 2.5rem;
  /* 字体大小 */
  margin-bottom: 20px;
  /* 下边距 */
  text-shadow: 2px 2px 5px rgba(0, 0, 0, 0.1);
  /* 添加阴影 */
}

/* 3. Person 组件周围的样式 */
.person {
  background-color: #f0f8ff;
  /* 背景色：浅蓝色 */
  color: #333;
  /* 字体颜色：深灰色 */
  padding: 20px;
  /* 内边距 */
  border: 2px solid #4CAF50;
  /* 边框：绿色 */
  border-radius: 10px;
  /* 圆角 */
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  /* 阴影效果 */
  max-width: 80%;
  /* 最大宽度：80% */
  margin: 20px auto;
  /* 垂直外边距 20px，水平居中 */
  text-align: center;
  /* 文本居中 */
}

/* 4. 添加一些内边距和边框 */
div#app {
  border: 2px solid #ddd;
  /* 边框 */
  border-radius: 10px;
  /* 圆角 */
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  /* 阴影 */
}

/* 5. 响应式：调整屏幕较小的设备上的样式 */
@media (max-width: 600px) {
  h1 {
    font-size: 1.5rem;
  }

  div#app {
    padding: 10px;
  }
}
</style>