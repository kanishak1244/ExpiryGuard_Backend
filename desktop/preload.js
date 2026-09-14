const { contextBridge, ipcRenderer } = require('electron');

// Expose safe desktop client bridge to renderer process
contextBridge.exposeInMainWorld('dawaiflowDesktop', {
  isDesktop: true,
  version: '1.0.0',
  platform: process.platform,
  reload: () => ipcRenderer.send('app-reload'),
  print: (options) => ipcRenderer.send('app-print', options)
});
