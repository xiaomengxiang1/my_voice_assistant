
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
let modelLoaded = false; // 添加模型加载状态标志

// 使用localStorage保存和读取模型位置和缩放
// 读取保存的模型位置和缩放
function loadModelSettings() {
  try {
    const savedPosition = localStorage.getItem('live2dModelPosition');
    const savedScale = localStorage.getItem('live2dModelScale');
    
    return {
      position: savedPosition ? JSON.parse(savedPosition) : null,
      scale: savedScale ? parseFloat(savedScale) : null
    };
  } catch (e) {
    console.error('加载模型设置失败:', e);
    return { position: null, scale: null };
  }
}

// 保存模型位置到localStorage
function saveModelPosition(x, y) {
  try {
    localStorage.setItem('live2dModelPosition', JSON.stringify({ x, y }));
  } catch (e) {
    console.error('保存模型位置失败:', e);
  }
}

// 保存模型缩放到localStorage
function saveModelScale(scale) {
  try {
    localStorage.setItem('live2dModelScale', scale.toString());
  } catch (e) {
    console.error('保存模型缩放失败:', e);
  }
}

// 修改模型加载部分
const modelUrl = 'model/whitecatfree_vts/sdwhite cat free.model3.json';
// 先加载保存的设置
const savedSettings = loadModelSettings();

Live2DModel.from(encodeURI(modelUrl))
  .then(loadedModel => {
    model = loadedModel;
    
    // 设置模型位置和缩放 - 使用localStorage中保存的值或默认值
    if (savedSettings.scale !== null) {
      model.scale.set(savedSettings.scale);
    } else {
      model.scale.set(0.3);
    }
    
    if (savedSettings.position !== null) {
      model.position.set(savedSettings.position.x, savedSettings.position.y);
    } else {
      model.position.set(window.innerWidth / 2, window.innerHeight / 2);
    }
    
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
    
    modelLoaded = true; // 标记模型已加载完成
  })
  .catch(err => console.error('模型加载失败:', err));

// 修改拖拽处理函数 - 持久化保存位置
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
  if (isDragging && model) {
    // 当拖拽结束时保存位置到localStorage
    saveModelPosition(model.position.x, model.position.y);
    isDragging = false;
  }
}

// 修改鼠标滚轮缩放 - 添加localStorage持久化
window.addEventListener('wheel', e => {
  if (model) {
    e.preventDefault();
    const scale = model.scale.x;
    const newScale = scale + (e.deltaY < 0 ? 0.05 : -0.05);
    
    // 限制缩放范围
    if (newScale >= 0.1 && newScale <= 1.0) {
      model.scale.set(newScale);
      
      // 保存当前缩放到localStorage
      saveModelScale(newScale);
    }
  }
}, { passive: false });

// 字幕相关状态
let aiMessageBuffer = '';
let typingSpeed = 100; // 打字效果速度（毫秒/字符）
let typingIndex = 0;
let typingText = '';
let typingInterval = null;
let currentSubtitleType = null; // 当前字幕类型变量
let isWebSocketInitializing = false; // 新增：标记WebSocket是否正在初始化

// 更新字幕显示 - 确保不会触发WebSocket重连
function updateSubtitle(text, type = 'normal') {
  // 不在字幕改变时刷新动画，除非类型改变
  const typeChanged = currentSubtitleType !== type;
  currentSubtitleType = type;
  
  // 清除任何正在进行的打字动画
  clearInterval(typingInterval);
  typingIndex = 0;
  
  // 根据消息类型设置字幕样式
  if (type === 'user') {
    subtitleEl.style.color = '#3498db'; // 用户消息为蓝色
    startTypingEffect(text);
    
    // 只有在之前不是用户消息的情况下才停止说话动画
    if (typeChanged && currentAnimationId !== null) {
      stopTalkingAnimation();
    }
  } else if (type === 'ai') {
    subtitleEl.style.color = '#2ecc71'; // AI消息为绿色
    startTypingEffect(text);
    
    // 只有在之前不是AI消息时才开始说话动画
    if (typeChanged && modelLoaded) {
      playTalkingAnimation();
    }
  } else if (type === 'system') {
    subtitleEl.style.color = '#f39c12'; // 系统消息为橙色
    subtitleEl.textContent = text;
    
    // 系统消息3秒后自动消失，但不触发WebSocket重连
    clearTimeout(subtitleEl._clear);
    subtitleEl._clear = setTimeout(() => {
      fadeOutSubtitle(false); // 传入false表示不重置WebSocket
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
      
      // 用户消息打完5秒后自动消失，但不重置WebSocket
      if (subtitleEl.style.color === '#3498db') {
        clearTimeout(subtitleEl._clear);
        subtitleEl._clear = setTimeout(() => {
          fadeOutSubtitle(false); // 传入false表示不重置WebSocket
        }, 5000);
      }
    }
  }, typingSpeed);
}

// 字幕淡出效果 - 添加参数控制是否重置WebSocket连接
function fadeOutSubtitle(resetWebSocket = false) {
  let opacity = 1.0;
  const fadeInterval = setInterval(() => {
    if (opacity > 0) {
      opacity -= 0.1;
      subtitleEl.style.opacity = opacity;
    } else {
      clearInterval(fadeInterval);
      subtitleEl.textContent = '';
      subtitleEl.style.opacity = 1.0;
      currentSubtitleType = null; // 重置当前字幕类型
      
      // 只有当明确指定时才重置WebSocket
      if (resetWebSocket) {
        // 避免重复初始化
        if (!isWebSocketInitializing) {
          initWebSocketConnection();
        }
      }
    }
  }, 50);
}

// 清除字幕 - 添加参数控制是否重置WebSocket连接
function clearSubtitle(resetWebSocket = false) {
  subtitleEl.textContent = '';
  clearTimeout(subtitleEl._clear);
  clearInterval(typingInterval);
  currentSubtitleType = null; // 重置当前字幕类型
  
  // 只有当明确指定时才重置WebSocket
  if (resetWebSocket) {
    // 避免重复初始化
    if (!isWebSocketInitializing) {
      initWebSocketConnection();
    }
  }
}

// 将WebSocket初始化分离为独立函数
function initWebSocketConnection() {
  // 避免重复初始化
  if (isWebSocketInitializing) {
    console.log('WebSocket已经在初始化中，跳过');
    return;
  }
  
  isWebSocketInitializing = true;
  console.log('尝试连接WebSocket...');
  
  // 如果已有连接，先关闭
  if (ws) {
    ws.close();
  }
  
  // 创建新的WebSocket连接 - 使用当前域名自动获取主机地址
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = window.location.hostname; // 自动获取当前域名
  const wsPort = '8000'; // WebSocket服务器端口
  const wsUrl = `${wsProtocol}//${wsHost}:${wsPort}`;
  
  console.log(`正在连接到WebSocket服务器: ${wsUrl}`);
  ws = new WebSocket(wsUrl);
  
  // 连接打开事件
  ws.onopen = () => {
    console.log('WebSocket连接成功');
    updateSubtitle('连接成功! 语音助手已准备就绪。', 'system');
    reconnectAttempts = 0; // 重置重连计数
    isWebSocketInitializing = false; // 重置初始化标志
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
      }
      else if (msg.type === 'ai_stream') {
        // AI流式回复片段
        aiMessageBuffer += msg.text;
        updateSubtitle(aiMessageBuffer, 'ai');
      }
      else if (msg.type === 'ai_complete') {
        // AI完整回复
        updateSubtitle(msg.text, 'ai');
        
        // 回复结束后3秒，停止说话动画，但不重置WebSocket
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
    isWebSocketInitializing = false; // 重置初始化标志
    
    if (reconnectAttempts < maxReconnectAttempts) {
      console.log(`将在 ${reconnectInterval/1000} 秒后尝试重连...`);
      reconnectAttempts++;
      setTimeout(initWebSocketConnection, reconnectInterval);
    } else {
      console.error('达到最大重连次数，请刷新页面重试');
      updateSubtitle('连接已断开，请刷新页面重试。', 'system');
    }
  };
  
  // 连接错误事件
  ws.onerror = err => {
    console.error('WebSocket连接错误:', err);
    isWebSocketInitializing = false; // 重置初始化标志
  };
}

// 初始化WebSocket连接 - 使用新的独立函数
function initSubtitleSocket() {
  initWebSocketConnection();
}

// 添加键盘快捷键处理
document.addEventListener('keydown', (e) => {
  // 按ESC键清除字幕，但不重置WebSocket
  if (e.key === 'Escape') {
    clearSubtitle(false);
  }
});