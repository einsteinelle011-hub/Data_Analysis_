<template>
  <div class="message" :class="{ 'user-message': isUser }">
    <div class="message-avatar">
      <div :class="isUser ? 'user-avatar' : 'bot-avatar'">
        {{ isUser ? '用户' : 'AI' }}
      </div>
    </div>
    <div class="message-content">
      <div class="message-text" v-html="renderedHtml"></div>
      <div class="message-time">
        {{ formatTime(timestamp) }}
      </div>
    </div>
  </div>
</template>

<script setup>
// import 三个包
import { defineProps, computed } from 'vue';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';

const props = defineProps({
  isUser: {
    type: Boolean,
    required: true
  },
  content: {
    type: String,
    required: true
  },
  timestamp: {
    type: Date,
    required: true
  }
});

// Initialize markdown-it with common useful options
const md = new MarkdownIt({
  html: false, // disallow raw HTML
  linkify: true,
  typographer: true
});

// Render markdown and sanitize the HTML for safe insertion
const renderedHtml = computed(() => {
  const raw = props.content || '';  // origin md content
  // Convert new Date objects to string if needed
  const markdown = typeof raw === 'string' ? raw : String(raw);
  const html = md.render(markdown);
  // DOMPurify handles XSS protection, ensure the safety
  return DOMPurify.sanitize(html);
});



const formatTime = (date) => {
  return new Date(date).toLocaleTimeString();
};
</script>

<style scoped>
.message {
  display: flex;
  margin-bottom: 1rem;
  max-width: 80%;
}

.message.user-message {
  margin-left: auto;
  flex-direction: row-reverse;
}

.message-avatar {
  margin-right: 0.5rem;
}

.user-message .message-avatar {
  margin-right: 0;
  margin-left: 0.5rem;
}

.user-avatar, .bot-avatar {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-weight: bold;
  font-size: 0.875rem;
}

.user-avatar {
  background-color: var(--primary-color);
  color: white;
}

.bot-avatar {
  background-color: var(--secondary-color);
  color: white;
}

.message-content {
  padding: 0.75rem 1rem;
  border-radius: var(--radius);
  position: relative;
}

.message:not(.user-message) .message-content {
  background-color: var(--bot-message);
}

.user-message .message-content {
  background-color: var(--user-message);
}

.message-text {
  margin-bottom: 0.25rem;
  line-height: 1.5;
}

.message-time {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-align: right;
}


/* Markdown content styling */
.message-text img {
  max-width: 100%;
  height: auto;
}

.message-text pre {
  background: #0b1220;
  color: #e6eef8;
  padding: 0.75rem;
  border-radius: 8px;
  overflow: auto;
}

.message-text code {
  background: rgba(0,0,0,0.06);
  padding: 0.15rem 0.3rem;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, 'Roboto Mono', 'Courier New', monospace;
}

.message-text blockquote {
  border-left: 4px solid rgba(0,0,0,0.1);
  padding-left: 0.75rem;
  color: var(--text-secondary);
}

.message-text a {
  color: var(--primary-color);
  text-decoration: underline;
}
</style>
