// 使用全局 PIXI.live2d 提供的 Live2DModel
const { Live2DModel } = PIXI.live2d;

// DOM元素和PIXI应用初始化
const canvas = document.getElementById('canvas');
const subtitleEl = document.getElementById('subtitle');
const app = new PIXI.Application({
  view: canvas,
  width: window.innerWidth,
  height: window.innerHeight,
  transparent: true,
  autoStart: true
});

// 窗口大小调整处理
window.addEventListener('resize', () => {
  app.renderer.resize(window.innerWidth, window.innerHeight);
});

// 模型与交互状态
let model, isDragging = false;
let dragOffset = { x: 0, y: 0 };
let currentAnimationId = null;

// 加载模型
const modelUrl = 'model/whitecatfree_vts/sdwhite cat free.model3.json';
Live2DModel.from(encodeURI(modelUrl))
  .then(loadedModel => {
    model = loadedModel;
    
    // 设置模型位置和缩放
    model.scale.set(0.3);
    model.position.set(window.innerWidth / 2, window.innerHeight / 2);
    
    // 可拖动和交互
    model.interactive = true;
    model.buttonMode = true;
    model.on('pointerdown', onDragStart);
    model.on('pointermove', onDragMove);
    model.on('pointerup', onDragEnd);
    model.on('pointerupoutside', onDragEnd);
    
    // 添加到舞台
    app.stage.addChild(model);
    
    // 可以设置默认动画
    if (model.internalModel.motionManager.definitions.idle) {
      model.internalModel.motionManager.startMotion('idle');
    }
  })
  .catch(err => console.error('模型加载失败:', err));

// 拖拽处理函数
function onDragStart(event) {
  isDragging = true;
  dragOffset.x = event.data.global.x - model.position.x;
  dragOffset.y = event.data.global.y - model.position.y;
}

function onDragMove(event) {
  if (isDragging) {
    model.position.x = event.data.global.x - dragOffset.x;
    model.position.y = event.data.global.y - dragOffset.y;
  }
}

function onDragEnd() {
  isDragging = false;
}

// 鼠标滚轮缩放
window.addEventListener('wheel', e => {
  if (model) {
    e.preventDefault();
    const scale = model.scale.x;
    const newScale = scale + (e.deltaY < 0 ? 0.05 : -0.05);
    
    // 限制缩放范围
    if (newScale >= 0.1 && newScale <= 1.0) {
      model.scale.set(newScale);
    }
  }
}, { passive: false });

// 字幕相关状态
let aiMessageBuffer = '';
let userTyping = false;
let typingSpeed = 100; // 打字效果速度（毫秒/字符）
let typingIndex = 0;
let typingText = '';
let typingInterval = null;

// 更新字幕显示
function updateSubtitle(text, type = 'normal') {
  // 清除任何正在进行的打字动画
  clearInterval(typingInterval);
  typingIndex = 0;
  
  // 根据消息类型设置字幕样式
  if (type === 'user') {
    subtitleEl.style.color = '#3498db'; // 用户消息为蓝色
    startTypingEffect(text);
  } else if (type === 'ai') {
    subtitleEl.style.color = '#2ecc71'; // AI消息为绿色
    startTypingEffect(text);
  } else if (type === 'system') {
    subtitleEl.style.color = '#f39c12'; // 系统消息为橙色
    subtitleEl.textContent = text;
    
    // 系统消息3秒后自动消失
    clearTimeout(subtitleEl._clear);
    subtitleEl._clear = setTimeout(() => {
      fadeOutSubtitle();
    }, 3000);
  } else {
    // 其他普通消息
    subtitleEl.style.color = '#ffffff';
    subtitleEl.textContent = text;
  }
}

// 字幕打字效果
function startTypingEffect(text) {
  typingText = text;
  typingIndex = 0;
  
  // 清除之前的打字间隔
  clearInterval(typingInterval);
  
  // 开始新的打字效果
  typingInterval = setInterval(() => {
    if (typingIndex <= typingText.length) {
      subtitleEl.textContent = typingText.substring(0, typingIndex);
      typingIndex++;
    } else {
      clearInterval(typingInterval);
      
      // 用户消息打完5秒后自动消失
      if (subtitleEl.style.color === '#3498db') {
        clearTimeout(subtitleEl._clear);
        subtitleEl._clear = setTimeout(() => {
          fadeOutSubtitle();
        }, 5000);
      }
    }
  }, typingSpeed);
}

// 字幕淡出效果
function fadeOutSubtitle() {
  let opacity = 1.0;
  const fadeInterval = setInterval(() => {
    if (opacity > 0) {
      opacity -= 0.1;
      subtitleEl.style.opacity = opacity;
    } else {
      clearInterval(fadeInterval);
      subtitleEl.textContent = '';
      subtitleEl.style.opacity = 1.0;
    }
  }, 50);
}

// 清除字幕
function clearSubtitle() {
  subtitleEl.textContent = '';
  clearTimeout(subtitleEl._clear);
  clearInterval(typingInterval);
}

// 初始化播放说话动画
function playTalkingAnimation() {
  if (model && model.internalModel.motionManager.definitions.talk) {
    // 如果有专门的talk动画，播放它
    currentAnimationId = model.internalModel.motionManager.startMotion('talk');
  } else if (model && model.internalModel.motionManager.definitions.tap_body) {
    // 否则尝试播放tap_body作为替代
    currentAnimationId = model.internalModel.motionManager.startMotion('tap_body');
  }
}

// 停止说话动画，恢复到空闲
function stopTalkingAnimation() {
  if (model) {
    if (currentAnimationId !== null) {
      model.internalModel.motionManager.stopMotion(currentAnimationId);
      currentAnimationId = null;
    }
    
    // 恢复到idle动画
    if (model.internalModel.motionManager.definitions.idle) {
      model.internalModel.motionManager.startMotion('idle');
    }
  }
}

// WebSocket客户端初始化
let ws;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectInterval = 2000; // 2秒

function initSubtitleSocket() {
  console.log('尝试连接WebSocket...');
  
  // 如果已有连接，先关闭
  if (ws) {
    ws.close();
  }
  
  // 创建新的WebSocket连接
  ws = new WebSocket('ws://localhost:8000');
  
  // 连接打开事件
  ws.onopen = () => {
    console.log('WebSocket连接成功');
    updateSubtitle('连接成功! 语音助手已准备就绪。', 'system');
    reconnectAttempts = 0; // 重置重连计数
  };
  
  // 接收消息事件
  ws.onmessage = evt => {
    try {
      const msg = JSON.parse(evt.data);
      console.log('收到消息:', msg);
      
      if (msg.type === 'user') {
        // 用户语音识别结果
        updateSubtitle(msg.text, 'user');
      } 
      else if (msg.type === 'ai_start') {
        // AI开始回复
        aiMessageBuffer = msg.text;
        updateSubtitle(aiMessageBuffer, 'ai');
        playTalkingAnimation(); // 播放说话动画
      }
      else if (msg.type === 'ai_stream') {
        // AI流式回复片段
        aiMessageBuffer += msg.text;
        updateSubtitle(aiMessageBuffer, 'ai');
      }
      else if (msg.type === 'ai_complete') {
        // AI完整回复
        updateSubtitle(msg.text, 'ai');
        
        // 回复结束后3秒，停止说话动画
        setTimeout(() => {
          stopTalkingAnimation();
        }, 3000);
      }
      else if (msg.type === 'system') {
        // 系统消息
        updateSubtitle(msg.text, 'system');
      }
    } catch (e) {
      console.error('无效的消息格式:', e);
    }
  };
  
  // 连接关闭事件
  ws.onclose = () => {
    console.log('WebSocket连接关闭');
    
    if (reconnectAttempts < maxReconnectAttempts) {
      console.log(`将在 ${reconnectInterval/1000} 秒后尝试重连...`);
      reconnectAttempts++;
      setTimeout(initSubtitleSocket, reconnectInterval);
    } else {
      console.error('达到最大重连次数，请刷新页面重试');
      updateSubtitle('连接已断开，请刷新页面重试。', 'system');
    }
  };
  
  // 连接错误事件
  ws.onerror = err => {
    console.error('WebSocket连接错误:', err);
  };
}

// 初始化WebSocket连接
initSubtitleSocket();

// 添加键盘快捷键处理
document.addEventListener('keydown', (e) => {
  // 按ESC键清除字幕
  if (e.key === 'Escape') {
    clearSubtitle();
  }
});

// 添加测试按钮（可选，用于调试）
function addTestButtons() {
  const testButtonsDiv = document.createElement('div');
  testButtonsDiv.style.position = 'fixed';
  testButtonsDiv.style.bottom = '10px';
  testButtonsDiv.style.right = '10px';
  testButtonsDiv.style.zIndex = '100';
  
  const testUserBtn = document.createElement('button');
  testUserBtn.textContent = '测试用户字幕';
  testUserBtn.onclick = () => updateSubtitle('这是一条测试用户消息', 'user');
  
  const testAIBtn = document.createElement('button');
  testAIBtn.textContent = '测试AI字幕';
  testAIBtn.onclick = () => updateSubtitle('这是一条测试AI回复消息', 'ai');
  
  testButtonsDiv.appendChild(testUserBtn);
  testButtonsDiv.appendChild(testAIBtn);
  document.body.appendChild(testButtonsDiv);
}

// 如果需要调试，可以取消下面这行的注释
// addTestButtons();
