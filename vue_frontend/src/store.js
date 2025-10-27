import { defineStore } from 'pinia';

export const useStore = defineStore('main', {
  state: () => ({
    apiKey: localStorage.getItem('apiKey') || null,
    currentSession: localStorage.getItem('currentSession') || 'default_session',
    sessions: JSON.parse(localStorage.getItem('sessions') || '["default_session"]'),
    messages: {},
    loading: false,
    error: null
  }),
  
  actions: {
    // 保存API Key
    setApiKey(key) {
      this.apiKey = key;
      localStorage.setItem('apiKey', key);
    },
    
    // 清除API Key（退出登录）
    clearApiKey() {
      this.apiKey = null;
      localStorage.removeItem('apiKey');
    },
    
    // 添加新会话
    addSession(sessionId) {
      if (!this.sessions.includes(sessionId)) {
        this.sessions.push(sessionId);
        localStorage.setItem('sessions', JSON.stringify(this.sessions));
      }
      this.setCurrentSession(sessionId);
    },
    
    // 设置当前会话
    setCurrentSession(sessionId) {
      this.currentSession = sessionId;
      localStorage.setItem('currentSession', sessionId);
    },
    
    // 删除会话
    removeSession(sessionId) {
      this.sessions = this.sessions.filter(id => id !== sessionId);
      localStorage.setItem('sessions', JSON.stringify(this.sessions));
      
      // 如果删除的是当前会话，切换到默认会话
      if (sessionId === this.currentSession) {
        const newSession = this.sessions.length > 0 ? this.sessions[0] : 'default_session';
        this.setCurrentSession(newSession);
      }
    },
    
    // 保存消息到状态
    addMessage(sessionId, isUser, content) {
      if (!this.messages[sessionId]) {
        this.messages[sessionId] = [];
      }
      
      this.messages[sessionId].push({
        id: Date.now(),
        isUser,
        content,
        timestamp: new Date()
      });
    },
    
    // 从历史记录加载消息
    loadHistory(sessionId, historyPayload) {
      this.messages[sessionId] = [];
            if (!historyPayload) return;

      // 支持三种入参情况：
      // 1) 后端返回的对象，包含 messages 数组（推荐，新结构化）
      // 2) 后端返回的对象，仅包含 history 字符串（legacy）
      // 3) 直接传入的字符串（老前端调用方式）

      // 如果传入的是后端整块响应对象
      if (typeof historyPayload === 'object') {
        // 优先处理结构化 messages 数组
        if (Array.isArray(historyPayload.messages)) {
          const msgs = historyPayload.messages;
          msgs.forEach(m => {
            // m: { is_user: bool, content: string, timestamp: string }
            this.addMessage(sessionId, !!m.is_user, m.content);
          });
          return;
        }

        // 回退：处理 legacy 字符串字段 history
        if (typeof historyPayload.history === 'string') {
          const lines = historyPayload.history.split('\n');
          let currentMessage = null;

          lines.forEach(line => {
            if (line.startsWith('用户：')) {
              if (currentMessage) {
                this.addMessage(sessionId, currentMessage.isUser, currentMessage.content);
              }
              currentMessage = {
                isUser: true,
                content: line.replace('用户：', '').trim()
              };
            } else if (line.startsWith('回复：')) {
              if (currentMessage) {
                this.addMessage(sessionId, currentMessage.isUser, currentMessage.content);
              }
              currentMessage = {
                isUser: false,
                content: line.replace('回复：', '').trim()
              };
            }
          });

          if (currentMessage) {
            this.addMessage(sessionId, currentMessage.isUser, currentMessage.content);
          }
          return;
        }

        // 如果对象既没有 messages 也没有 history，则无操作
        return;
      }

      // 兼容：如果传入的是字符串（老调用方式）
      if (typeof historyPayload === 'string') {
        const lines = historyPayload.split('\n');
        let currentMessage = null;

        lines.forEach(line => {
          if (line.startsWith('用户：')) {
            if (currentMessage) {
              this.addMessage(sessionId, currentMessage.isUser, currentMessage.content);
            }
            currentMessage = {
              isUser: true,
              content: line.replace('用户：', '').trim()
            };
          } else if (line.startsWith('回复：')) {
            if (currentMessage) {
              this.addMessage(sessionId, currentMessage.isUser, currentMessage.content);
            }
            currentMessage = {
              isUser: false,
              content: line.replace('回复：', '').trim()
            };
          }
        });

        if (currentMessage) {
          this.addMessage(sessionId, currentMessage.isUser, currentMessage.content);
        }
      }
    },
    
    // 清空会话消息
    clearSessionMessages(sessionId) {
      this.messages[sessionId] = [];
    },
    
    // 设置加载状态
    setLoading(state) {
      this.loading = state;
    },
    
    // 设置错误信息
    setError(message) {
      this.error = message;
      // 3秒后自动清除错误信息
      setTimeout(() => {
        this.error = null;
      }, 3000);
    }
  }
});
