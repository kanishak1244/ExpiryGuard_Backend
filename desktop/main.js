const { app, BrowserWindow, shell, ipcMain, systemPreferences } = require('electron');
const path = require('path');
const url = require('url');

// Determine production web URL from environment or official default
const PRODUCTION_WEB_URL = process.env.DAWAIFLOW_WEB_URL || 'https://app.dawaiflow.com';
const ALLOWED_DOMAINS = ['app.dawaiflow.com', 'api.dawaiflow.com', 'dawaiflow.com', 'localhost', '127.0.0.1'];

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    title: 'DawaiFlow',
    width: 1366,
    height: 850,
    minWidth: 1024,
    minHeight: 700,
    icon: path.join(__dirname, 'assets', 'icon.ico'),
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // Remove default menu bar for clean desktop app UI
  mainWindow.setMenu(null);

  // Load production web application
  loadAppURL();

  // Show window when ready to prevent visual flickering
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Offline / Network Error Handling
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.warn(`[DawaiFlow Desktop] Failed to load URL '${validatedURL}': ${errorDescription} (${errorCode})`);
    // Only show offline screen if it's a network/connectivity failure (not a subframe error)
    if (errorCode <= -100 && errorCode >= -110 || errorCode === -21 || errorCode === -105 || errorCode === -106) {
      mainWindow.loadFile(path.join(__dirname, 'offline.html'));
    }
  });

  // Grant camera/media permissions for barcode scanning
  mainWindow.webContents.session.setPermissionRequestHandler((webContents, permission, callback) => {
    const pageUrl = webContents.getURL();
    if (permission === 'media' || permission === 'camera') {
      try {
        const parsedUrl = new URL(pageUrl);
        if (ALLOWED_DOMAINS.some(d => parsedUrl.hostname.includes(d))) {
          return callback(true);
        }
      } catch (_) {}
    }
    callback(false);
  });

  // Safe Navigation & External Link Routing
  mainWindow.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
    try {
      const parsed = new URL(targetUrl);
      // External communication (WhatsApp, Email, Support) opens in system browser
      if (parsed.hostname.includes('wa.me') || targetUrl.startsWith('mailto:') || targetUrl.startsWith('tel:') || !ALLOWED_DOMAINS.some(d => parsed.hostname.includes(d))) {
        shell.openExternal(targetUrl);
        return { action: 'deny' };
      }
    } catch (_) {}
    return { action: 'allow' };
  });

  mainWindow.webContents.on('will-navigate', (event, targetUrl) => {
    try {
      const parsed = new URL(targetUrl);
      if (!ALLOWED_DOMAINS.some(d => parsed.hostname.includes(d)) && !targetUrl.startsWith('file://')) {
        event.preventDefault();
        shell.openExternal(targetUrl);
      }
    } catch (_) {}
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function loadAppURL() {
  if (mainWindow) {
    mainWindow.loadURL(PRODUCTION_WEB_URL).catch(err => {
      console.warn('[DawaiFlow Desktop] Load URL error:', err);
      mainWindow.loadFile(path.join(__dirname, 'offline.html'));
    });
  }
}

// IPC Handlers
ipcMain.on('app-reload', () => {
  loadAppURL();
});

ipcMain.on('app-print', (event, options) => {
  if (mainWindow) {
    mainWindow.webContents.print(options || { silent: false, printBackground: true });
  }
});

// App Lifecycle
app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
